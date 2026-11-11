import { newRequestId } from "./requestId";
import { contentDigest } from "./contentDigest";
import React, { useRef, useState } from "react";
import "./ModelEndpointCapacity.css";

type Row = Record<string, any>;
type Props = { request: (path: string, options?: RequestInit) => Promise<Row>; text: (zh: string, en: string) => string; canRecover: boolean; initial?: Row };
const root = "/api/agent-extensions/processing";
async function fingerprint(value: Row) {
  return contentDigest(JSON.stringify(value));
}

export default function ProcessingRecovery({ request, text, canRecover, initial }: Props) {
  const [report, setReport] = useState<Row | null>(initial || null);
  const [chain, setChain] = useState(initial?.continuity_id || "");
  const [selected, setSelected] = useState<Row | null>(null);
  const [receipt, setReceipt] = useState<Row | null>(null);
  const [resolution, setResolution] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(new Map<string, Row>());
  const locked = useRef(false);
  const run = async (operation: () => Promise<void>) => {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError("");
    try { await operation(); } catch (e) { setError(e instanceof Error ? e.message : text("操作失败", "Operation failed")); }
    finally { locked.current = false; setBusy(false); }
  };
  const post = async (path: string, body: Row) => {
    const signature = path + JSON.stringify(body);
    const payload = pending.current.get(signature) || { ...body, idempotency_key: newRequestId() };
    pending.current.set(signature, payload);
    const result = await request(path, { method: "POST", body: JSON.stringify(payload) });
    pending.current.delete(signature); return result;
  };
  const load = async (id: string, after = "") => {
    // Clear previously authorized records before requesting a fresh read.
    const previous = report;
    setReport(null); setSelected(null); setResolution(null); setReceipt(null);
    const result = await request(`${root}/${encodeURIComponent(id)}?limit=100${after ? `&after=${encodeURIComponent(after)}` : ""}`);
    setReport(after ? { ...result, observations: [...(previous?.observations || []), ...result.observations], recoveries: [...(previous?.recoveries || []), ...result.recoveries] } : result);
  };
  const state = (value: string) => ({ BLOCKED: text("受阻", "Blocked"), DEGRADED: text("降级", "Degraded"), UNKNOWN: text("结果未知", "Unknown outcome"), OPEN: text("待处理", "Open"), RECOVERY_ACCEPTED: text("已接纳恢复", "Recovery accepted"), RESOLVED: text("已核对", "Reconciled"), ACCEPTED: text("已接纳，等待显式派发", "Accepted; awaiting explicit dispatch"), QUEUED: text("等待容量", "Waiting for capacity"), DISPATCHED: text("已派发", "Dispatched"), COMPLETED: text("已完成", "Completed"), REJECTED: text("已拒绝", "Rejected"), UNOBSERVED: text("未观测", "Unobserved"), FAILED: text("失败", "Failed"), CANCELLED: text("已取消", "Cancelled"), SUCCEEDED: text("已成功", "Succeeded") }[value] || value);
  const reason = (value: string) => ({ BUDGET_REQUESTS: text("请求预算已用尽", "Request budget exhausted"), BUDGET_STEPS: text("步骤预算已用尽", "Step budget exhausted"), BUDGET_TOKENS: text("Token 预算已用尽", "Token budget exhausted"), REPEATED_ACTION: text("重复动作达到上限", "Repeated action limit reached"), NO_PROGRESS: text("持续未取得进展", "No progress limit reached"), POSSIBLE_SEND: text("可能已发送", "Possible send"), LEASE_EXPIRED: text("执行租约已过期", "Execution lease expired"), CLIENT_CLOSED: text("客户端已关闭", "Client closed"), UNMATCHED: text("没有匹配结果", "No matching result"), SEMANTIC_UNAVAILABLE: text("语义检索不可用", "Semantic retrieval unavailable"), TEXTUAL_FALLBACK: text("使用文本检索", "Textual retrieval used"), WAITING_HUMAN: text("等待人工决定", "Awaiting Human decision"), SOURCE_REVOKED: text("来源权限已撤销", "Source authority revoked") }[value] || value);
  const choose = (block: Row) => { setSelected(block); setResolution(null); setReceipt(null); setError(""); };
  const canRetry = selected?.status === "OPEN" && selected.category !== "DEGRADED" && (selected.category !== "UNKNOWN" || ["FAILED", "CANCELLED"].includes(resolution?.status));
  return <section className="model-runtime-observations" aria-label={text("处理诊断与恢复", "Processing diagnosis and recovery")}>
    <h4>{text("处理诊断与恢复", "Processing diagnosis and recovery")}</h4>
    <p>{text("读取当前任务的受阻原因、已用预算和恢复回执。读取或刷新不会触发生成，也不会重置预算。未知结果须先核对原请求。", "Read the task's blocking reasons, consumed budget and recovery receipts. Reading or refreshing does not generate or reset budgets. Reconcile unknown outcomes against the original request first.")}</p>
    {error && <p role="alert">{error}</p>}
    <form onSubmit={event => { event.preventDefault(); void run(() => load(chain)); }}>
      <label className="workbench-field"><span>{text("任务连续性记录", "Task continuity record")}</span><input value={chain} required maxLength={128} pattern="[A-Za-z0-9][A-Za-z0-9_.:\-]*" disabled={busy} onChange={event => { setChain(event.target.value); setReport(null); setSelected(null); setReceipt(null); setResolution(null); }} /></label>
      <button className="small-button" disabled={busy}>{text("读取处理记录", "Read processing records")}</button>
    </form>
    {report && <>
      <p>{text("原生任务", "Canonical Task")}: <code>{report.canonical_task_id}</code> · {state(report.lifecycle_status)}</p>
      <dl className="detail-grid">{([['requests', '请求', 'Requests'], ['steps', '步骤', 'Steps'], ['tokens', 'Token', 'Tokens']] as const).map(([key, zh, en]) => <React.Fragment key={key}><dt>{text(zh, en)}</dt><dd>{report.consumed?.[key] ?? text("未观测", "Unobserved")} / {report.limits?.[key] ?? text("未观测", "Unobserved")}</dd></React.Fragment>)}</dl>
      <p>{text("Token 用量仅包含实际报告或执行器观测的部分；缺失用量保留为未观测。", "Token usage includes reported or executor-observed counts; missing usage remains unobserved.")}</p>
      {!report.observations?.length && <p>{text("当前没有受阻或降级记录。", "No blocking or degraded observations are recorded.")}</p>}
      {(report.observations || []).map((block: Row) => <article key={block.block_id}>
        <p>{state(block.category)} · {reason(block.reason_code)} · {state(block.status)}</p>
        <p><code>{block.target_id}</code> · {text("修订", "Revision")} {block.target_revision} {block.retrieval_path && `· ${block.retrieval_path}`} {block.match_state && `· ${block.match_state}`}</p>
        <button type="button" className="small-button" disabled={busy} onClick={() => choose(block)}>{text("查看并处理此记录", "Inspect this observation")}</button>
      </article>)}
      {report.next_cursor && <button type="button" className="small-button" disabled={busy} onClick={() => void run(() => load(chain, report.next_cursor))}>{text("加载更多处理记录", "Load more processing records")}</button>}
      {(report.recoveries || []).map((item: Row) => <p key={item.recovery_id}><code>{item.recovery_id}</code> · {state(item.status)} <button type="button" className="small-button" disabled={busy} onClick={() => setReceipt(item)}>{text("查看恢复回执", "Inspect recovery receipt")}</button></p>)}
    </>}
    {selected && <section aria-label={text("选中的处理记录", "Selected processing observation")}>
      <p><code>{selected.block_id}</code> · {reason(selected.reason_code)} · {state(selected.status)}</p>
      {canRecover && selected.category === "UNKNOWN" && <form key={selected.block_id + "-resolution"} onSubmit={event => {
        event.preventDefault(); const data = new FormData(event.currentTarget);
        const mode = String(data.get("mode"));
        if (mode === "OPERATOR_RESOLUTION" && !data.get("confirmed")) { setError(text("请先确认已经核对原请求。", "Confirm that you checked the original request.")); return; }
        void run(async () => setResolution(await post(`${root}/blocks/${encodeURIComponent(selected.block_id)}/reconcile`, {
          expected_version: selected.version, target: selected.target, mode, reason: String(data.get("reason")),
          ...(mode === "OPERATOR_RESOLUTION" ? { outcome: String(data.get("outcome")) } : {}),
        })));
      }}><fieldset className="operation-explainer-form" disabled={busy}><legend>{text("核对原请求", "Reconcile original request")}</legend>
        <label className="workbench-field"><span>{text("核对方式", "Reconciliation method")}</span><select name="mode" aria-label={text("核对方式", "Reconciliation method")}><option value="READ_ORIGINAL">{text("读取原请求证据", "Read original request evidence")}</option><option value="OPERATOR_RESOLUTION">{text("记录人工核对决定", "Record operator resolution")}</option></select></label>
        <label className="workbench-field"><span>{text("人工确认结果", "Operator-confirmed outcome")}</span><select name="outcome" aria-label={text("人工确认结果", "Operator-confirmed outcome")}><option value="FAILED">{text("已结束，执行失败", "Ended with failure")}</option><option value="CANCELLED">{text("已结束，已取消", "Ended with cancellation")}</option><option value="SUCCEEDED">{text("已结束，已成功", "Ended with success")}</option><option value="UNOBSERVED">{text("仍无法确认", "Still unobserved")}</option></select></label>
        <label className="workbench-field"><span>{text("核对说明", "Reconciliation reason")}</span><input name="reason" required maxLength={1000} /></label>
        <label><input name="confirmed" type="checkbox" /> {text("我已核对原请求；若选择结束状态，已确认远端处理结束。人工决定保留为人工证据。", "I checked the original request and confirmed remote termination for an ended outcome. This decision remains operator evidence.")}</label>
        <button className="small-button">{text("提交核对", "Submit reconciliation")}</button>
      </fieldset></form>}
      {resolution && <p role="status">{text("核对结果", "Reconciliation outcome")}: {state(resolution.status)}</p>}
      {canRecover && canRetry && <form key={selected.block_id + "-retry"} onSubmit={event => {
        event.preventDefault(); const data = new FormData(event.currentTarget);
        void run(async () => {
          const body = { block_id: selected.block_id, expected_version: selected.version, target: selected.target, reason_code: selected.reason_code,
            add_requests: Number(data.get("requests")), add_steps: Number(data.get("steps")), add_tokens: Number(data.get("tokens")) };
          const decision_digest = await fingerprint({ ...body, reason: String(data.get("reason")) });
          setReceipt(await post(root + "/retries", { ...body, decision_digest }));
          setSelected({ ...selected, status: "RECOVERY_ACCEPTED" });
        });
      }}><fieldset className="operation-explainer-form" disabled={busy}><legend>{text("批准有限恢复", "Approve bounded recovery")}</legend>
        <p>{text("恢复沿用原任务和已用预算，仅增加本次明确批准的额度。接纳回执后仍需单独派发。", "Recovery retains the original Task and consumed budget, adding only the allowance approved here. An accepted receipt requires a separate dispatch.")}</p>
        {([['requests', '增加请求额度', 'Additional requests', 1, 10000], ['steps', '增加步骤额度', 'Additional steps', 16, 10000], ['tokens', '增加 Token 额度', 'Additional tokens', 8192, 10000000]] as const).map(([name, zh, en, value, max]) => <label className="workbench-field" key={name}><span>{text(zh, en)}</span><input name={name} type="number" required min={1} max={max} defaultValue={value} /></label>)}
        <label className="workbench-field"><span>{text("批准说明", "Approval reason")}</span><input name="reason" required maxLength={1000} /></label>
        <button className="primary-button">{text("接纳有限恢复", "Accept bounded recovery")}</button>
      </fieldset></form>}
    </section>}
    {receipt && <section aria-label={text("恢复回执", "Recovery receipt")}>
      <p role="status"><code>{receipt.recovery_id}</code> · {state(receipt.status)}</p>
      <p>{text("接纳恢复不表示已派发，也不代表输出已通过审核。已完成的任务不会重新生成。", "Acceptance does not imply dispatch or output approval. Completed work is not generated again.")}</p>
      {canRecover && ["ACCEPTED", "QUEUED"].includes(receipt.status) && <button type="button" className="primary-button" disabled={busy} onClick={() => void run(async () => {
        setReceipt(await request(`${root}/recoveries/${encodeURIComponent(receipt.recovery_id)}/dispatch`, { method: "POST", body: "{}" }));
      })}>{text("显式派发此恢复", "Dispatch this recovery")}</button>}
    </section>}
  </section>;
}
