import React, { useEffect, useRef, useState } from "react";
import { statusLabel } from "./statusLabels";

type Row = Record<string, any>;
type Props = { request: (path: string, options?: RequestInit) => Promise<Row>; text: (zh: string, en: string) => string; domain: string };
const ROOT = "/api/agent-extensions";
const CHANNEL = "/app/channels?channel=CH_PLATFORM_ADMINISTRATION&view=manage";
export default function ModelToolWorkflow({ request, text, domain }: Props) {
  const [registrations, setRegistrations] = useState<Row[]>([]);
  const [turns, setTurns] = useState<Row[]>([]);
  const [registration, setRegistration] = useState<Row | null>(null);
  const [turn, setTurn] = useState<Row | null>(null);
  const [nextRegistration, setNextRegistration] = useState("");
  const [nextTurn, setNextTurn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const epoch = useRef(0);
  const lock = useRef(false);
  const merge = (old: Row[], values: Row[], key: string) => [...new Map([...old, ...values].map(item => [item[key], item])).values()];
  const fetchPage = async (kind: "model-read-tools" | "model-tool-turns", after = "") => request(`${ROOT}/${kind}?security_domain_id=${encodeURIComponent(domain)}&limit=20${after ? `&after=${encodeURIComponent(after)}` : ""}`);
  const load = async (more?: "registration" | "turn") => {
    if (lock.current || !domain) return;
    const generation = epoch.current;
    lock.current = true; setBusy(true); setError("");
    try {
      const results = await Promise.allSettled([
        more === "turn" ? Promise.resolve(null) : fetchPage("model-read-tools", more === "registration" ? nextRegistration : ""),
        more === "registration" ? Promise.resolve(null) : fetchPage("model-tool-turns", more === "turn" ? nextTurn : ""),
      ]);
      if (generation !== epoch.current) return;
      const registered = results[0].status === "fulfilled" ? results[0].value : null;
      const observed = results[1].status === "fulfilled" ? results[1].value : null;
      if (results.some(value => value.status === "rejected")) setError(text("部分只读目录当前不可读取；有权的结果仍会显示。", "Some read-only directories are unavailable; authorized results remain visible."));
      if (registered) { setRegistrations(old => more ? merge(old, registered.items || [], "registration_id") : registered.items || []); setNextRegistration(registered.next_after || ""); }
      if (observed) { setTurns(old => more ? merge(old, observed.items || [], "turn_id") : observed.items || []); setNextTurn(observed.next_after || ""); }
    } catch (e) { if (generation === epoch.current) setError(e instanceof Error ? e.message : text("受控工具目录不可用", "Governed tool directory unavailable")); }
    finally { if (generation === epoch.current) { lock.current = false; setBusy(false); } }
  };
  useEffect(() => {
    ++epoch.current; lock.current = false;
    setRegistrations([]); setTurns([]); setRegistration(null); setTurn(null); setNextRegistration(""); setNextTurn("");
    void load();
    return () => { ++epoch.current; };
  }, [domain]);
  const inspect = async (kind: "registration" | "turn", id: string) => {
    if (lock.current) return;
    const generation = epoch.current;
    lock.current = true; setBusy(true); setError("");
    if (kind === "registration") setRegistration(null); else setTurn(null);
    try {
      if (!id) return;
      const value = await request(kind === "registration" ? `${ROOT}/model-read-tools/${encodeURIComponent(id)}/contract` : `${ROOT}/model-tool-turns/${encodeURIComponent(id)}`);
      if (generation === epoch.current) { if (kind === "registration") setRegistration(value); else setTurn(value); }
    } catch (e) { if (generation === epoch.current) setError(e instanceof Error ? e.message : text("当前记录不可读取", "Current record is unavailable")); }
    finally { if (generation === epoch.current) { lock.current = false; setBusy(false); } }
  };
  return <section className="model-tool-workflow" aria-label={text("受控模型工具协作", "Governed model tool collaboration")}>
    <h4>{text("Agent 提议、独立人工审批、受管 Worker 执行", "Agent proposal, independent Human approval, managed Worker execution")}</h4>
    <p>{text("当前界面供人查看只读注册、Task 阶段与已有审批。创建、运行和准入工具回合必须由原始认证 Agent 执行；人不能在这里冒用 Agent。", "Humans can inspect read registrations, Task phases, and existing approvals here. Only the original authenticated Agent can create, run, or admit a tool turn.")}</p>
    <p>{text("当前范围：一个已批准来源的 GET 读取，最多两次模型请求、一次工具调用、零次自动修复。模型提议不构成执行授权。", "Current subset: one approved-source GET read, at most two model requests, one tool call, and zero automatic repairs. A model proposal grants no execution authority.")}</p>
    <button type="button" className="secondary-button" disabled={busy} onClick={() => void load()}>{text("刷新只读目录", "Refresh read-only directories")}</button>
    {error && <p role="alert">{error}</p>}
    <div className="continuity-extension-grid">
      <section className="continuity-extension-column"><h4>{text("已批准只读工具注册", "Approved read-tool registrations")}</h4>
        <label className="workbench-field"><span>{text("选择授权注册", "Select an authorized registration")}</span><select aria-label={text("选择授权注册", "Select an authorized registration")} disabled={busy} value={registration?.registration_id || ""} onChange={e => void inspect("registration", e.target.value)}><option value="">{text("选择注册", "Select registration")}</option>{registrations.map(item => <option key={item.registration_id} value={item.registration_id}>{item.tool_id} · {item.source?.entity_id} · {item.registration_id}</option>)}</select></label>
        {!registrations.length && <p>{text("当前页没有可读注册。注册需绑定精确来源、只读分类和独立 Action Card。", "No readable registrations on this page. Registration requires an exact source, reviewed READ classification, and an independent Action Card.")}</p>}
        {nextRegistration && <button type="button" className="secondary-button" disabled={busy} onClick={() => void load("registration")}>{text("加载更多注册", "Load more registrations")}</button>}
        {registration && <dl><dt>{text("注册批准", "Registration approval")}</dt><dd>{registration.action_id}</dd><dt>{text("精确来源", "Exact source")}</dt><dd>{registration.source?.family} · {registration.source?.entity_id} · {registration.source?.revision_id}</dd><dt>{text("来源摘要", "Source digest")}</dt><dd><code>{registration.source?.content_digest}</code></dd><dt>{text("Schema 摘要", "Schema digest")}</dt><dd><code>{registration.schema_digest}</code></dd><dt>{text("只读输入契约", "Read-only input contract")}</dt><dd><pre>{JSON.stringify(registration.input_schema, null, 2)}</pre></dd></dl>}
      </section>
      <section className="continuity-extension-column"><h4>{text("Task 工具回合", "Task tool turns")}</h4>
        <label className="workbench-field"><span>{text("选择授权回合", "Select an authorized turn")}</span><select aria-label={text("选择授权回合", "Select an authorized turn")} disabled={busy} value={turn?.turn_id || ""} onChange={e => void inspect("turn", e.target.value)}><option value="">{text("选择回合", "Select turn")}</option>{turns.map(item => <option key={item.turn_id} value={item.turn_id}>{item.task_id} · {statusLabel(item.status, text)} · {item.turn_id}</option>)}</select></label>
        {!turns.length && <p>{text("当前页没有可读回合。查看仍需当前安全域、Task 与精确来源的读取权限。", "No readable turns on this page. Observation requires current Security Domain, Task, and exact-source read authority.")}</p>}
        {nextTurn && <button type="button" className="secondary-button" disabled={busy} onClick={() => void load("turn")}>{text("加载更多回合", "Load more turns")}</button>}
        {turn && <><p>{turn.turn_id} · {statusLabel(turn.status, text)}</p><dl><dt>Task / Step</dt><dd>{turn.task_id} / {turn.step_id}</dd><dt>{text("原始 Agent", "Original Agent")}</dt><dd>{turn.principal_id}</dd><dt>{text("模型修订", "Profile revision")}</dt><dd>{turn.profile_id} · v{turn.profile_version}</dd><dt>{text("精确探测", "Exact probe")}</dt><dd>{turn.probe_id}</dd><dt>{text("工具执行批准", "Tool execution approval")}</dt><dd>{turn.tool_call?.action_id || text("尚未申请", "Not requested")}</dd><dt>{text("工具 Worker 作业", "Tool Worker job")}</dt><dd>{turn.tool_call?.job_id || "—"}</dd></dl>
          <ul>{(turn.stages || []).map((stage: Row) => <li key={stage.phase}>{stage.phase} · {stage.attempt_id || text("未发送", "Not dispatched")} · {stage.output_digest || "—"}</li>)}</ul>
          {turn.answer && <p className="continuity-answer">{turn.answer}</p>}
          {["UNKNOWN", "UNOBSERVED"].includes(turn.status) && <p role="status">{text("发送结果未确认；此界面不会重发或自动继续。请先核对原尝试与容量记录。", "Send outcome is unconfirmed. This interface never resends or automatically resumes; reconcile the original attempt and capacity record first.")}</p>}
          <button type="button" className="secondary-button" disabled={busy} onClick={() => void inspect("turn", turn.turn_id)}>{text("刷新当前回合记录", "Refresh current turn record")}</button></>}
      </section>
    </div>
    <section><h4>{text("独立 Action Card 审批", "Independent Action Card approval")}</h4><p>{text("注册审批与每次工具调用审批分别绑定精确内容。由有权的另一名人类在原平台管理频道审核；批准后仍由原 Agent 准入并由 Worker 重查。", "Registration and each tool call use separate exact-content approvals. Another authorized Human reviews the existing card in the original administration channel; the original Agent then admits it and the Worker rechecks authority.")}</p>
      <a href={CHANNEL}>{text("前往平台管理频道审批", "Open administration channel approvals")}</a>
    </section>
  </section>;
}
