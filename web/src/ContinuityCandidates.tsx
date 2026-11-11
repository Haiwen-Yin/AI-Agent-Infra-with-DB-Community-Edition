import { newRequestId } from "./requestId";
import React, { FormEvent, useEffect, useRef, useState } from "react";

type Row = Record<string, any>;
type Source = { family: string; entity_id: string; revision_id: string; content_digest: string };
type Props = { request: (path: string, options?: RequestInit) => Promise<Row>; text: (zh: string, en: string) => string; domain: string; principalId: string; canWrite: boolean };
const emptySource = (): Source => ({ family: "HANDOFF", entity_id: "", revision_id: "", content_digest: "" });
const sourceFamilies = ["HANDOFF", "HANDOFF_OUTCOME", "MEMORY", "KNOWLEDGE", "EXPERIENCE", "SKILL", "SOURCE", "TASK", "GRAPH", "DB4A2A", "AUDIT", "WORKING_NOTE"];
const fields: Record<string, [string, string, string][]> = {
  MEMORY: [["title", "标题", "Title"], ["body", "记忆正文", "Memory content"]],
  KNOWLEDGE: [["title", "标题", "Title"], ["body", "知识正文", "Knowledge content"]],
  EXPERIENCE: [["title", "标题", "Title"], ["problem", "遇到的问题", "Problem"], ["solution", "解决方法", "Solution"], ["validation", "验证结果", "Validation"], ["applicability", "适用范围", "Applicability"]],
  SKILL: [["title", "标题", "Title"], ["instructions", "操作说明", "Instructions"], ["input_contract", "输入约定", "Input contract"], ["output_contract", "输出约定", "Output contract"]],
};
const intakeFields = [
  ["purpose", "用途与要解决的问题", "Purpose and intended question"],
  ["source_locator", "原始来源与章节位置", "Original source and chapter location"],
  ["responsible_principal_id", "责任人身份标识", "Responsible principal ID"],
  ["subject", "业务主题", "Business subject"],
  ["applicable_product", "适用产品或业务", "Applicable product or business"],
  ["applicable_version", "适用版本", "Applicable version"],
  ["effective_from", "生效时间", "Effective from"],
  ["effective_until", "失效时间（可选）", "Effective until (optional)"],
] as const;

export default function ContinuityCandidates({ request, text, domain, principalId, canWrite }: Props) {
  const [items, setItems] = useState<Row[]>([]);
  const [cursor, setCursor] = useState("");
  const [candidate, setCandidate] = useState<Row | null>(null);
  const [historical, setHistorical] = useState<Row | null>(null);
  const [family, setFamily] = useState("EXPERIENCE");
  const [sources, setSources] = useState<Source[]>([emptySource()]);
  const [replacement, setReplacement] = useState<Source | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [intakePreview, setIntakePreview] = useState<Row | null>(null);
  const lock = useRef(false);
  const pending = useRef(new Map<string, string>());
  const mounted = useRef(true);
  const label = (value: string) => ({ MEMORY: text("记忆", "Memory"), KNOWLEDGE: text("知识", "Knowledge"), EXPERIENCE: text("经验", "Experience"), SKILL: text("技能", "Skill"), HANDOFF: text("交接", "Handoff"), HANDOFF_OUTCOME: text("交接结果", "Handoff outcome"), PENDING: text("待审核", "Pending"), APPROVED: text("审核通过", "Approved"), REJECTED: text("已拒绝", "Rejected"), SUPERSEDED: text("已替代", "Superseded"), EXPIRED: text("已过期", "Expired") }[value] || value);
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : text("操作失败", "Operation failed")); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  };
  const post = async (path: string, body: Row) => {
    const signature = path + JSON.stringify(body);
    const id = pending.current.get(signature) || newRequestId();
    pending.current.set(signature, id);
    const result = await request(path, { method: "POST", body: JSON.stringify({ ...body, idempotency_key: id }) });
    pending.current.delete(signature); return result;
  };
  const load = async (next = "") => {
    const result = await request(`/api/artifact-candidates?security_domain_id=${encodeURIComponent(domain)}${next ? `&cursor=${encodeURIComponent(next)}` : ""}`);
    if (!mounted.current) return;
    setItems(previous => next ? [...previous, ...(result.items || [])] : result.items || []); setCursor(result.next_cursor || "");
  };
  useEffect(() => { mounted.current = true; void run(() => load()); return () => { mounted.current = false; }; }, []);
  const select = async (id: string) => {
    const value = await request(`/api/artifact-candidates/${encodeURIComponent(id)}`);
    if (!mounted.current) return;
    setCandidate(value); setHistorical(null); setFamily(value.payload.content.family); setSources(value.payload.sources); setReplacement(value.payload.replaces); setIntakePreview(null);
  };
  const fresh = () => { setCandidate(null); setHistorical(null); setSources([emptySource()]); setReplacement(null); setNotice(""); setIntakePreview(null); };
  const sourceFields = (value: Source, change: (value: Source) => void, onlyFamily?: string) => <>
    <label className="workbench-field"><span>{text("来源类型", "Source family")}</span><select disabled={!!candidate?.legacy_remediation_allowed} value={value.family} onChange={e => change({ ...value, family: e.target.value })}>{(onlyFamily ? [onlyFamily] : sourceFamilies).map(item => <option key={item} value={item}>{label(item)}</option>)}</select></label>
    {([["entity_id", "实体标识", "Entity ID"], ["revision_id", "精确版本标识", "Exact revision ID"], ["content_digest", "内容摘要（SHA-256）", "Content digest (SHA-256)"]] as const).map(([name, zh, en]) => <label key={name} className="workbench-field"><span>{text(zh, en)}</span><input required readOnly={!!candidate?.legacy_remediation_allowed} value={value[name]} maxLength={name === "content_digest" ? 64 : 128} pattern={name === "content_digest" ? "[0-9a-f]{64}" : undefined} onChange={e => change({ ...value, [name]: e.target.value })} /></label>)}
  </>;
  const proposal = (form: HTMLFormElement) => {
      const data = new FormData(form);
      const content: Row = { family, ...Object.fromEntries(fields[family].map(([name]) => [name, String(data.get(name))])) };
      if (family === "MEMORY") content.memory_type = String(data.get("memory_type"));
      if (family === "SKILL") content.required_actions = String(data.get("required_actions") || "").split("\n").map(x => x.trim()).filter(Boolean);
      const intake = family === "KNOWLEDGE" ? Object.fromEntries([...intakeFields.map(([name]) => name), "classification", "audience", "decision_status"].map(name => {
        const value = String(data.get(`intake_${name}`) || "").trim();
        return [name, value && name.startsWith("effective_") ? new Date(value).toISOString() : value || null];
      })) : undefined;
      return { security_domain_id: domain, content, sources, replaces: replacement, reason: String(data.get("reason")), ...(intake ? { intake } : {}) };
  };
  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const body = { ...proposal(event.currentTarget), ...(candidate ? { expected_version: candidate.version } : {}) };
    void run(async () => {
      const result = await post(candidate ? `/api/artifact-candidates/${encodeURIComponent(candidate.candidate_id)}/revisions` : "/api/artifact-candidates", body);
      await load(); await select(result.candidate_id); setNotice(text("候选已保存，尚未成为正式内容。", "Candidate saved; it has not become a formal artifact."));
    });
  };
  const preview = (form: HTMLFormElement) => {
    if (!form.reportValidity()) return;
    const body = proposal(form);
    void run(async () => { const value = await post('/api/knowledge-intake/preview', body); if (mounted.current) setIntakePreview(value); });
  };
  const decision = (event: FormEvent<HTMLFormElement>, operation: "review" | "promote") => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void run(async () => {
      await post(`/api/artifact-candidates/${encodeURIComponent(candidate!.candidate_id)}/${operation}`, {
        expected_version: candidate!.version, expected_digest: candidate!.content_digest, reason: String(data.get("reason")),
        ...(operation === "review" ? { decision: String(data.get("decision")) } : {}),
      });
      await load(); await select(candidate!.candidate_id); setNotice(text("操作已记录。", "Operation recorded."));
    });
  };
  const reason = <label className="workbench-field"><span>{text("操作原因", "Reason")}</span><input name="reason" required maxLength={1000} /></label>;
  const localTime = (value?: string) => value ? new Date(new Date(value).getTime() - new Date(value).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
  const qualityPreview = (value: Row) => <section aria-label={text("入库质量与分块预览", "Intake quality and chunk preview")}>
    <h4>{text("入库质量与分块预览", "Intake quality and chunk preview")}</h4>
    <p>{value.publication_eligible ? text("必填信息已声明，仍需独立审核与显式发布。", "Required metadata is declared; independent review and explicit promotion are still required.") : text("当前只能保存待补充候选，请补齐以下信息后再审核。", "Save as a pending candidate and complete the following information before approval.")}</p>
    <ul>{value.findings.map((finding: Row) => <li key={finding.code}>{finding.code.startsWith("MISSING_") ? text("请声明：", "Declare: ") + (() => { const field = intakeFields.find(([key]) => key === finding.field); const labels: Record<string, string> = { classification: text("密级", "Classification"), audience: text("预期读者", "Intended audience") }; return field ? text(field[1], field[2]) : labels[String(finding.field)] || String(finding.field); })() : finding.code === "NONCURRENT_DECISION" ? text("保留提案或历史状态，不能作为当前政策。", "Retain the proposed or historical status; do not present it as current policy.") : finding.code === "POSSIBLE_DUPLICATE" ? text("发现同标题、同正文的可读资料；请核对来源、版本与适用范围。", "Readable material has the same title and body; compare source, revision and applicability.") : finding.code === "POSSIBLE_CONFLICT" ? text("发现同标题、不同正文的可读资料；可能存在冲突，请比较原始依据，不自动替换。", "Readable material has the same title and different content; compare original evidence for a possible conflict without automatic replacement.") : text("请复核较长语义块；拆分时保留表头、单位、条件和例外。", "Review the long semantic block; retain table headers, units, conditions and exceptions when splitting.")}</li>)}</ul>
    <p>{text("预览保留原文；重复和潜在冲突检查仅比较当前可读、同标题的前 20 条正式资料，不代表全库检查。", "Preview retains the original text. Duplicate and possible-conflict checks compare at most 20 currently readable formal entries with the same title; this is not an exhaustive corpus check.")}</p>
    {value.comparisons?.length > 0 && <ul>{value.comparisons.map((item: Row) => <li key={item.entity_id}>{text("可读资料标识", "Readable source ID")}: {item.entity_id}</li>)}</ul>}
    {value.chunks.map((chunk: Row) => <details key={chunk.number}><summary>{text("原文块", "Source block")} {chunk.number} · {chunk.start}–{chunk.end}</summary><pre className="continuity-body">{chunk.text}</pre></details>)}
  </section>;
  const contentPreview = (value: Row) => <><p>{text("修订", "Revision")} {value.revision_no} · {value.content_digest}</p>{Object.entries(value.payload.content).filter(([name]) => name !== "family").map(([name, body]) => <p className="continuity-body" key={name}><strong>{fields[value.payload.content.family]?.find(item => item[0] === name)?.slice(1).map(String).reduce((zh, en) => text(zh, en)) || (name === "memory_type" ? text("记忆类型", "Memory type") : text("所需权限", "Required actions"))}</strong>: {Array.isArray(body) ? body.join("\n") : String(body)}</p>)}<ul>{value.payload.sources.map((source: Source, i: number) => <li key={i}>{label(source.family)} · {source.entity_id} · {source.revision_id} · {source.content_digest}</li>)}</ul></>;
  return <section className="panel" aria-label={text("候选审核与正式版本", "Candidate review and formal versions")}>
    <h3>{text("候选审核与正式版本", "Candidate review and formal versions")}</h3>
    <p>{text("先提交带精确来源的候选，由独立审核者审核，再显式生成正式版本。来源权限撤回后，读取、审核和生成都会重新校验。", "Submit a candidate with exact sources, obtain an independent review, then explicitly create a formal revision. Reads, reviews and promotion recheck current source permissions.")}</p>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="page-toolbar"><select disabled={busy} value={candidate?.candidate_id || ""} aria-label={text("选择候选", "Select candidate")} onChange={e => e.target.value && void run(() => select(e.target.value))}><option value="">{text("选择候选记录", "Select candidate record")}</option>{items.map(item => <option key={item.candidate_id} value={item.candidate_id}>{label(item.family)} · {String(item.candidate_id).slice(-12)} · {label(item.status)}</option>)}</select><button className="small-button" type="button" disabled={busy} onClick={fresh}>{text("新建候选", "New candidate")}</button><button className="small-button" type="button" disabled={busy} onClick={() => void run(() => load())}>{text("刷新候选", "Refresh candidates")}</button>{cursor && <button className="small-button" type="button" disabled={busy} onClick={() => void run(() => load(cursor))}>{text("加载更多候选", "Load more candidates")}</button>}</div>
    {candidate && <section aria-label={text("当前候选内容", "Current candidate content")}><h4>{label(candidate.status)}</h4>{contentPreview(candidate)}{candidate.intake_preview && qualityPreview(candidate.intake_preview)}{candidate.result_entity_id && <p>{text("正式实体／版本", "Formal entity / revision")}: {candidate.result_entity_id} / {candidate.result_revision_id}</p>}</section>}
    {candidate?.legacy_remediation_allowed && <p role="status">{text("此历史候选已审核，但缺少入库信息。只能补充入库信息，原正文与精确来源保持不变；保存后必须重新独立审核。", "This reviewed historical candidate lacks intake metadata. Supplement metadata while preserving the content and exact sources; saving requires a new independent review.")}</p>}
    <form key={candidate ? `${candidate.candidate_id}-${candidate.version}` : `new-${family}`} onSubmit={save} onChange={() => setIntakePreview(null)}><fieldset className="operation-explainer-form" disabled={busy || !canWrite || !!candidate && (candidate.proposed_by !== principalId || candidate.status !== "PENDING" && !candidate.legacy_remediation_allowed)}><legend>{candidate ? text("修订候选", "Revise candidate") : text("创建候选", "Create candidate")}</legend>
      <label className="workbench-field"><span>{text("候选类型", "Candidate family")}</span><select value={family} disabled={!!candidate} onChange={e => { setFamily(e.target.value); setReplacement(null); }}>{Object.keys(fields).map(item => <option key={item} value={item}>{label(item)}</option>)}</select></label>
      {fields[family].map(([name, zh, en]) => <label key={name} className="workbench-field"><span>{text(zh, en)}</span><textarea name={name} required readOnly={!!candidate?.legacy_remediation_allowed} maxLength={4000} rows={name === "title" ? 1 : 3} defaultValue={candidate?.payload.content[name] || ""} /></label>)}
      {family === "KNOWLEDGE" && <fieldset className="operation-explainer-form"><legend>{text("知识入库引导", "Guided knowledge intake")}</legend>
        <p>{text("未知信息可以留空并保存候选。生效时间来自原始依据，不能用入库时间代替。预期读者只记录意图；实际共享仍需当前授权。", "Leave unknowns empty and save a candidate. Effective time comes from source evidence, not ingestion time. Intended audience records intent; actual sharing still requires current authorization.")}</p>
        {intakeFields.map(([name, zh, en]) => <label className="workbench-field" key={name}><span>{text(zh, en)}</span><input name={`intake_${name}`} type={name.startsWith("effective_") ? "datetime-local" : "text"} maxLength={["purpose", "source_locator"].includes(name) ? 4000 : name === 'subject' ? 256 : 128} defaultValue={name.startsWith("effective_") ? localTime(candidate?.payload.intake?.[name]) : candidate?.payload.intake?.[name] || ""} /></label>)}
        <label className="workbench-field"><span>{text("密级（应与安全域一致）", "Classification (must match domain)")}</span><select name="intake_classification" defaultValue={candidate?.payload.intake?.classification || ""}><option value="">{text("待确认", "Unknown")}</option>{[["PUBLIC", "公开", "Public"], ["INTERNAL", "内部", "Internal"], ["CONFIDENTIAL", "机密", "Confidential"], ["RESTRICTED", "受限", "Restricted"]].map(([value, zh, en]) => <option key={value} value={value}>{text(zh, en)}</option>)}</select></label>
        <label className="workbench-field"><span>{text("预期读者", "Intended audience")}</span><select name="intake_audience" defaultValue={candidate?.payload.intake?.audience || ""}><option value="">{text("待确认", "Unknown")}</option>{[["PRINCIPAL_PRIVATE", "本人", "Private"], ["DOMAIN", "安全域成员", "Domain members"], ["ORGANIZATION", "组织", "Organization"], ["PUBLIC", "公众", "Public"]].map(([value, zh, en]) => <option key={value} value={value}>{text(zh, en)}</option>)}</select></label>
        <label className="workbench-field"><span>{text("决策状态", "Decision status")}</span><select name="intake_decision_status" defaultValue={candidate?.payload.intake?.decision_status || "PROPOSED"}>{[["PROPOSED", "提案", "Proposed"], ["CURRENT", "当前有效", "Current"], ["REJECTED", "已拒绝", "Rejected"], ["SUPERSEDED", "已替代", "Superseded"], ["HISTORICAL", "历史资料", "Historical"]].map(([value, zh, en]) => <option key={value} value={value}>{text(zh, en)}</option>)}</select></label>
        <button className="small-button" type="button" onClick={event => event.currentTarget.form && preview(event.currentTarget.form)}>{text("检查信息与分块", "Check metadata and chunks")}</button>
        {intakePreview && qualityPreview(intakePreview)}
      </fieldset>}
      {family === "MEMORY" && <label className="workbench-field"><span>{text("记忆类型", "Memory type")}</span><select name="memory_type" defaultValue={candidate?.payload.content.memory_type || "FACT"}>{[["FACT", "事实", "Fact"], ["EPISODIC", "事件", "Event"], ["PREFERENCE", "偏好", "Preference"], ["DECISION", "决定", "Decision"], ["PROCEDURAL", "流程", "Procedure"]].map(([value, zh, en]) => <option key={value} value={value}>{text(zh, en)}</option>)}</select></label>}
      {family === "SKILL" && <label className="workbench-field"><span>{text("所需权限（每行一项，可选）", "Required actions (one per line, optional)")}</span><textarea name="required_actions" maxLength={4000} defaultValue={candidate?.payload.content.required_actions?.join("\n") || ""} /></label>}
      {sources.map((source, i) => <fieldset key={i} className="operation-explainer-form"><legend>{text("精确来源", "Exact source")} {i + 1}</legend>{sourceFields(source, value => setSources(previous => previous.map((item, index) => index === i ? value : item)))}<button className="small-button" type="button" disabled={sources.length === 1 || !!candidate?.legacy_remediation_allowed} onClick={() => setSources(previous => previous.filter((_, index) => index !== i))}>{text("移除此来源", "Remove source")}</button></fieldset>)}
      <button className="small-button" type="button" disabled={sources.length >= 100 || !!candidate?.legacy_remediation_allowed} onClick={() => setSources(previous => [...previous, emptySource()])}>{text("添加来源", "Add source")}</button>
      <label><input type="checkbox" disabled={!!candidate?.legacy_remediation_allowed} checked={!!replacement} onChange={e => setReplacement(e.target.checked ? { ...emptySource(), family } : null)} />{text("替换已有正式版本", "Replace an existing formal revision")}</label>{replacement && <fieldset className="operation-explainer-form"><legend>{text("被替换的精确版本", "Exact revision to replace")}</legend>{sourceFields(replacement, setReplacement, family)}</fieldset>}
      {reason}<button className="primary-button">{text("保存候选", "Save candidate")}</button>
    </fieldset></form>
    {candidate && <>
      <form onSubmit={event => decision(event, "review")}><fieldset className="operation-explainer-form" disabled={busy || !canWrite || candidate.proposed_by === principalId || candidate.status !== "PENDING"}><legend>{text("独立审核", "Independent review")}</legend><select name="decision" aria-label={text("审核决定", "Review decision")}><option value="APPROVED">{text("通过", "Approve")}</option><option value="REJECTED">{text("拒绝", "Reject")}</option></select>{reason}<button className="primary-button">{text("提交审核", "Submit review")}</button></fieldset></form>
      <form onSubmit={event => decision(event, "promote")}><fieldset className="operation-explainer-form" disabled={busy || !canWrite || candidate.proposed_by === principalId || candidate.status !== "APPROVED" || !!candidate.result_entity_id}><legend>{text("生成正式版本", "Create formal revision")}</legend><p>{text("此操作采用上方已读取的版本与摘要，不自动审批其他修订。", "This operation uses the version and digest shown above; other revisions are not automatically approved.")}</p>{reason}<button className="primary-button">{text("生成正式版本", "Create formal revision")}</button></fieldset></form>
      <form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); void run(async () => { const value = await request(`/api/artifact-candidates/${encodeURIComponent(candidate.candidate_id)}?revision=${Number(data.get("revision"))}`); if (mounted.current) setHistorical(value); }); }}><fieldset className="operation-explainer-form" disabled={busy}><legend>{text("候选历史", "Candidate history")}</legend><label className="workbench-field"><span>{text("修订号", "Revision number")}</span><input type="number" name="revision" min={1} max={candidate.current_revision_no} defaultValue={1} required /></label><button className="small-button">{text("读取候选历史", "Read candidate history")}</button></fieldset></form>
      {historical && <section aria-label={text("候选历史只读预览", "Read-only candidate history")}><h4>{text("候选历史只读预览", "Read-only candidate history")}</h4>{contentPreview(historical)}{historical.intake_preview && qualityPreview(historical.intake_preview)}</section>}
    </>}
  </section>;
}
