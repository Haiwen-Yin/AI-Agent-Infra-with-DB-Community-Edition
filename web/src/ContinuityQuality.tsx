import React, { FormEvent, useEffect, useRef, useState } from "react";
import { ClipboardCheck, RotateCcw } from "lucide-react";
import { statusLabel } from "./statusLabels";

type Row = Record<string, any>;
type SourceRef = { family: string; entity_id: string; revision_id: string; content_digest: string };
type Props = { request: (path: string, options?: RequestInit) => Promise<Row>; text: (zh: string, en: string) => string; domain: string; principalId: string; work?: Row; sources: SourceRef[]; canWrite: boolean; canManage: boolean };
const ROOT = "/api/agent-extensions";
const newId = () => crypto.randomUUID();
const SOURCE_MODES = ["KNOWLEDGE_GROUNDED", "MIXED_SOURCES", "MODEL_SUPPLEMENT", "KNOWLEDGE_EXTRACTS", "CLARIFICATION_REQUIRED", "INSUFFICIENT_KNOWLEDGE"];

export default function ContinuityQuality({ request, text, domain, principalId, work, sources, canWrite, canManage }: Props) {
  const [view, setView] = useState<"retrospective" | "evaluation">("retrospective");
  const [profiles, setProfiles] = useState<Row[]>([]);
  const [nativeAgents, setNativeAgents] = useState<Row[]>([]);
  const [policy, setPolicy] = useState<Row | null>(null);
  const [retrospective, setRetrospective] = useState<Row | null>(null);
  const [cases, setCases] = useState<Row[]>([]);
  const [selectedCase, setSelectedCase] = useState<Row | null>(null);
  const [rubricRevision, setRubricRevision] = useState(0);
  const [runRecord, setRunRecord] = useState<Row | null>(null);
  const [profileId, setProfileId] = useState("");
  const [allowModelSend, setAllowModelSend] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const lock = useRef(false);
  const pending = useRef(new Map<string, Row>());
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : text("操作失败", "Operation failed")); }
    finally { lock.current = false; setBusy(false); }
  };
  const post = async (path: string, body: Row) => {
    const signature = path + JSON.stringify(body);
    const payload = pending.current.get(signature) || { ...body, idempotency_key: newId() };
    pending.current.set(signature, payload);
    const value = await request(path, { method: "POST", body: JSON.stringify(payload) });
    pending.current.delete(signature); return value;
  };
  const loadCases = async () => {
    const value = await request(`${ROOT}/answer-evaluation/cases?limit=100`);
    setCases(Array.isArray(value) ? value : value.items || []);
  };
  useEffect(() => {
    if (!canManage) return;
    let active = true;
    void Promise.all([
      request("/api/llm-provider-profiles?limit=100"),
      request("/api/native-agents?limit=100"),
      request("/api/platform/portal-knowledge-policy"),
      request(`${ROOT}/answer-evaluation/cases?limit=100`),
    ]).then(([profileValue, agentValue, policyValue, caseValue]) => {
      if (!active) return;
      setProfiles(profileValue.items || []); setNativeAgents(agentValue.items || []); setPolicy(policyValue);
      setCases(Array.isArray(caseValue) ? caseValue : caseValue.items || []);
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : text("模型或验收目录不可用", "Model or evaluation inventory is unavailable")); });
    return () => { active = false; };
  }, [domain, canManage]);

  const submitRetrospective = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const refs = sources.filter(item => data.getAll("source_ref").includes(JSON.stringify(item)));
    void run(async () => {
      if (!refs.length) throw new Error(text("至少选择一个已授权的精确来源。", "Select at least one authorized exact source."));
      const value = await post(`${ROOT}/retrospectives`, {
        security_domain_id: domain, task_id: String(data.get("task_id")), trigger: String(data.get("trigger")), target_family: String(data.get("target_family")),
        sources: refs, policy_revision: String(policy?.version || data.get("policy_revision")), profile_id: String(data.get("profile_id")),
        profile_version: Number(data.get("profile_version")), token_budget: Number(data.get("token_budget")), reason: String(data.get("reason")),
      });
      setRetrospective(value); setAllowModelSend(false); setNotice(text("回顾作业已创建为待执行任务。", "Retrospective job created and is awaiting an explicit run."));
    });
  };
  const runRetrospective = () => {
    if (!retrospective?.job_id || !allowModelSend) return;
    void run(async () => {
      const value = await request(`${ROOT}/retrospectives/${encodeURIComponent(retrospective.job_id)}/run`, { method: "POST" });
      setRetrospective(value); setAllowModelSend(false);
      setNotice(text("模型结果仅生成待审核候选；不会自动审批或发布。", "Model output is only a pending candidate; it is not automatically approved or published."));
    });
  };
  const createCase = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void run(async () => {
      const value = await post(`${ROOT}/answer-evaluation/cases`, { case_id: String(data.get("case_id")), query_text: String(data.get("query_text")),
        expected_mode: String(data.get("expected_mode")), expected_entity_ids: String(data.get("expected_entity_ids") || "").split("\n").map(x => x.trim()).filter(Boolean), reason: String(data.get("reason")) });
      await loadCases(); const next = cases.find(item => item.case_id === value.case_id && Number(item.version) === Number(value.version)) || { case_id: value.case_id, version: value.version, status: "ACTIVE" };
      setSelectedCase(next); setRubricRevision(0); setNotice(text("验收用例已登记；请为精确用例版本设置 Rubric。", "Evaluation case recorded; register a rubric for this exact case revision."));
    });
  };
  const registerRubric = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const allowed = data.getAll("allowed_source").map(String);
    void run(async () => {
      if (!selectedCase) return;
      const value = await post(`${ROOT}/answer-evaluation/rubrics`, {
        case_id: selectedCase.case_id, case_version: Number(selectedCase.version),
        rubric: { allowed_answer_sources: allowed, required_phrases: String(data.get("required_phrases") || "").split("\n").map(x => x.trim()).filter(Boolean),
          forbidden_phrases: String(data.get("forbidden_phrases") || "").split("\n").map(x => x.trim()).filter(Boolean),
          minimum_characters: Number(data.get("minimum_characters")), require_real_model: data.get("require_real_model") === "on",
          require_human_review: data.get("require_human_review") === "on", strategy: String(data.get("strategy")) },
        reason: String(data.get("reason")),
      });
      setRubricRevision(Number(value.revision)); setNotice(text(`Rubric 修订 ${value.revision} 已登记。`, `Rubric revision ${value.revision} registered.`));
    });
  };
  const queueEvaluation = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void run(async () => {
      if (!selectedCase || !rubricRevision) throw new Error(text("请先选择用例并登记 Rubric。", "Select a case and register its rubric first."));
      const value = await post(`${ROOT}/answer-evaluation/runs`, { case_id: selectedCase.case_id, case_version: Number(selectedCase.version), rubric_revision: rubricRevision,
        security_domain_id: domain, agent_id: String(data.get("agent_id")), entry_kind: String(data.get("entry_kind")), reason: String(data.get("reason")) });
      setRunRecord(await request(`${ROOT}/answer-evaluation/runs/${encodeURIComponent(value.run_id)}`)); setAllowModelSend(false);
      setNotice(text("验收任务已排队。需要外部模型时，请单独确认并执行。", "Evaluation run queued. Explicitly confirm before a run that may call an external model."));
    });
  };
  const executeEvaluation = () => {
    const id = runRecord?.run?.run_id;
    if (!id || !allowModelSend) return;
    void run(async () => {
      await request(`${ROOT}/answer-evaluation/runs/${encodeURIComponent(id)}/execute`, { method: "POST" });
      setRunRecord(await request(`${ROOT}/answer-evaluation/runs/${encodeURIComponent(id)}`)); setAllowModelSend(false);
    });
  };
  const openEvaluation = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void run(async () => {
      const id = String(data.get("run_id") || "").trim();
      setRunRecord(await request(`${ROOT}/answer-evaluation/runs/${encodeURIComponent(id)}`));
      setAllowModelSend(false);
    });
  };
  const reviewEvaluation = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void run(async () => {
      const id = runRecord?.run?.run_id;
      if (!id || !runRecord?.observation?.output_digest) return;
      await post(`${ROOT}/answer-evaluation/runs/${encodeURIComponent(id)}/reviews`, {
        output_digest: runRecord.observation.output_digest, factual_correct: data.get("factual_correct") === "on",
        citations_supported: data.get("citations_supported") === "on", reason: String(data.get("reason")),
      });
      setRunRecord(await request(`${ROOT}/answer-evaluation/runs/${encodeURIComponent(id)}`)); setNotice(text("独立人工评审已记录。", "Independent human review recorded."));
    });
  };
  const eligibleProfiles = profiles.filter(item => item.status === "ACTIVE" && item.health_state === "HEALTHY");
  const activeAgents = nativeAgents.filter(item => item.status === "ACTIVE");
  const taskChoices = (work?.execution_links || []).filter((item: Row) => item.link_kind === "TASK");
  const field = (name: string, zh: string, en: string, props: Row = {}) => <label className="workbench-field"><span>{text(zh, en)}</span><input name={name} {...props} /></label>;
  const reason = (zh = "操作原因", en = "Reason") => field("reason", zh, en, { required: true, maxLength: 1000 });

  return <section className="panel continuity-quality-panel" aria-label={text("回顾与回答验收", "Retrospective and answer evaluation")}>
    <div className="continuity-extension-heading"><div><h3>{text("回顾与回答验收", "Retrospective and answer evaluation")}</h3><p>{text("复用 Task Continuity 与候选审核；模型输出、确定性检查和人工评审分别记录。", "Uses Task Continuity and candidate review; model output, deterministic checks, and human review remain distinct records.")}</p></div></div>
    <div className="continuity-extension-tabs" role="tablist" aria-label={text("质量工作区", "Quality workspace")}>
      <button role="tab" aria-selected={view === "retrospective"} className={view === "retrospective" ? "active" : ""} type="button" onClick={() => setView("retrospective")}><RotateCcw size={16} />{text("工作回顾", "Work retrospective")}</button>
      <button role="tab" aria-selected={view === "evaluation"} className={view === "evaluation" ? "active" : ""} type="button" onClick={() => setView("evaluation")}><ClipboardCheck size={16} />{text("答案验收", "Answer evaluation")}</button>
    </div>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!canManage && <p>{text("模型配置、来源披露策略和答案验收由有平台管理权限的人员在 Dashboard 中操作。", "Model configuration, source-disclosure policy, and answer evaluation are managed in the Dashboard by authorized platform managers.")}</p>}
    {view === "retrospective" && <div className="continuity-extension-grid">
      <form onSubmit={submitRetrospective}><fieldset className="operation-explainer-form" disabled={busy || !canWrite || !canManage}><legend>{text("创建结构化回顾作业", "Create a structured retrospective")}</legend>
        {taskChoices.length ? <label className="workbench-field"><span>{text("关联任务计划", "Linked Task Plan")}</span><select name="task_id" required>{taskChoices.map((item: Row) => <option key={item.entity_id} value={item.entity_id}>{item.entity_id}</option>)}</select></label> : <>{field("task_id", "任务计划标识", "Task Plan ID", { required: true, defaultValue: work?.task_id || "", maxLength: 128 })}<p>{text("需要选择当前主体有权访问的现有 Task Plan。", "Choose an existing Task Plan accessible to the current principal.")}</p></>}
        <label className="workbench-field"><span>{text("触发原因", "Trigger")}</span><select name="trigger"><option value="SUCCESS">{text("任务成功", "Task success")}</option><option value="FAILURE">{text("任务失败", "Task failure")}</option><option value="CORRECTION">{text("纠正", "Correction")}</option><option value="FEEDBACK">{text("反馈", "Feedback")}</option></select></label>
        <label className="workbench-field"><span>{text("目标类型", "Target family")}</span><select name="target_family">{["MEMORY", "KNOWLEDGE", "EXPERIENCE", "SKILL"].map(item => <option key={item} value={item}>{statusLabel(item, text)}</option>)}</select></label>
        <label className="workbench-field"><span>{text("来源证据", "Source evidence")}</span><select name="source_ref" multiple required size={Math.min(6, Math.max(3, sources.length))}>{sources.map(item => <option key={JSON.stringify(item)} value={JSON.stringify(item)}>{statusLabel(item.family, text)} · {item.entity_id} · {item.revision_id}</option>)}</select></label>
        {!sources.length && <p>{text("先完成来源同步、上下文组装或发布，再选择其精确来源引用。", "Complete source synchronization, a context assembly, or a publication first, then select its exact source reference.")}</p>}
        <label className="workbench-field"><span>{text("健康模型配置", "Healthy model profile")}</span><select name="profile_id" required value={profileId} onChange={e => setProfileId(e.target.value)}><option value="">{text("选择已健康配置", "Select a healthy profile")}</option>{eligibleProfiles.map(item => <option key={item.profile_id} value={item.profile_id}>{item.profile_name || item.profile_id} · {item.model_id}</option>)}</select></label>
        <input type="hidden" name="profile_version" value={eligibleProfiles.find(item => item.profile_id === profileId)?.version || ""} />{field("policy_revision", "策略修订", "Policy revision", { required: true, readOnly: true, value: policy?.version || "" })}
        <label className="workbench-field"><span>{text("Token 预算", "Token budget")}</span><input type="number" name="token_budget" min={128} max={32768} defaultValue={8192} required /></label>{reason()}
        <p>{text("创建会登记 Task Continuity 步骤。后续执行会把选定证据发送给健康且获准的模型，并只产生待审核候选。", "Creation records a Task Continuity step. A later explicit run sends selected evidence to the approved healthy model and creates only a pending candidate.")}</p><button className="primary-button">{text("创建回顾作业", "Create retrospective")}</button>
      </fieldset></form>
      <section className="continuity-extension-column"><h4>{text("当前回顾作业", "Current retrospective")}</h4>{retrospective ? <><p>{retrospective.job_id} · {statusLabel(retrospective.status, text)}</p>{retrospective.candidate_id && <p>{text("待审核候选", "Pending candidate")}: {retrospective.candidate_id}</p>}<label className="continuity-source-check"><input type="checkbox" checked={allowModelSend} onChange={e => setAllowModelSend(e.target.checked)} /><span>{text("我确认此次操作会向模型服务发送已选择的来源内容。", "I confirm this operation will send the selected source content to the model service.")}</span></label><button className="primary-button" type="button" disabled={busy || retrospective.status !== "PENDING" || !allowModelSend} onClick={runRetrospective}>{text("执行一次回顾", "Run retrospective once")}</button><p>{text("外部发送结果不确定时不会自动重试。", "Uncertain external sends are not retried automatically.")}</p></> : <p>{text("尚未创建回顾作业。", "No retrospective job has been created.")}</p>}</section>
    </div>}
    {view === "evaluation" && <div className="continuity-quality-grid">
      <section className="continuity-extension-column"><h4>{text("答案用例", "Answer cases")}</h4>
        <form onSubmit={createCase}><fieldset className="operation-explainer-form" disabled={busy || !canManage}><legend>{text("登记录入／检索用例", "Register a retrieval case")}</legend>{field("case_id", "用例标识", "Case ID", { required: true, maxLength: 128 })}<label className="workbench-field"><span>{text("问题", "Query")}</span><textarea name="query_text" required maxLength={2000} rows={2} /></label>
          <label className="workbench-field"><span>{text("预期检索模式", "Expected retrieval mode")}</span><select name="expected_mode">{["MATCHED", "PARTIAL_MATCH", "NO_MATCH", "AMBIGUOUS"].map(value => <option key={value} value={value}>{statusLabel(value, text)}</option>)}</select></label>
          <label className="workbench-field"><span>{text("预期实体标识（每行一个，可选）", "Expected entity IDs (one per line, optional)")}</span><textarea name="expected_entity_ids" rows={2} maxLength={4096} /></label>{reason("用例登记原因", "Case registration reason")}<button className="primary-button">{text("登记用例", "Register case")}</button>
        </fieldset></form>
        <label className="workbench-field"><span>{text("选择活动用例", "Select an active case")}</span><select value={selectedCase ? `${selectedCase.case_id}:${selectedCase.version}` : ""} onChange={e => { const value = cases.find(item => `${item.case_id}:${item.version}` === e.target.value) || null; setSelectedCase(value); setRubricRevision(0); }}><option value="">{text("选择用例版本", "Select case revision")}</option>{cases.filter(item => item.status === "ACTIVE").map(item => <option key={`${item.case_id}:${item.version}`} value={`${item.case_id}:${item.version}`}>{item.case_id} · v{item.version}</option>)}</select></label>
        {selectedCase && <form onSubmit={registerRubric}><fieldset className="operation-explainer-form" disabled={busy || !canManage}><legend>{text("版本化验收 Rubric", "Versioned answer rubric")}</legend>
          <div className="continuity-mode-list"><span>{text("允许的回答来源", "Allowed answer sources")}</span>{SOURCE_MODES.map(item => <label key={item}><input type="checkbox" name="allowed_source" value={item} defaultChecked={["KNOWLEDGE_GROUNDED", "MODEL_SUPPLEMENT", "CLARIFICATION_REQUIRED", "INSUFFICIENT_KNOWLEDGE"].includes(item)} />{statusLabel(item, text)}</label>)}</div>
          <label className="workbench-field"><span>{text("必须包含短语（每行一项）", "Required phrases (one per line)")}</span><textarea name="required_phrases" rows={2} /></label><label className="workbench-field"><span>{text("禁止出现短语（每行一项）", "Forbidden phrases (one per line)")}</span><textarea name="forbidden_phrases" rows={2} /></label>
          <label className="workbench-field"><span>{text("最少字符数", "Minimum characters")}</span><input name="minimum_characters" type="number" min={1} max={10000} defaultValue={10} /></label>
          <label className="workbench-field"><span>{text("检索策略", "Retrieval strategy")}</span><select name="strategy"><option value="hybrid">{text("混合检索", "Hybrid")}</option><option value="keyword">{text("关键词", "Keyword")}</option><option value="fulltext">{text("全文", "Full text")}</option><option value="vector">{text("向量", "Vector")}</option></select></label>
          <label className="continuity-source-check"><input type="checkbox" name="require_real_model" defaultChecked /><span>{text("要求真实模型回答", "Require a real-model answer")}</span></label><label className="continuity-source-check"><input type="checkbox" name="require_human_review" defaultChecked /><span>{text("要求独立人工评审", "Require independent human review")}</span></label>{reason("Rubric 登记原因", "Rubric registration reason")}<button className="primary-button">{text("登记新 Rubric 修订", "Register rubric revision")}</button>
        </fieldset></form>}
      </section>
      <section className="continuity-extension-column"><h4>{text("运行与独立评审", "Run and independent review")}</h4>
        <form onSubmit={queueEvaluation}><fieldset className="operation-explainer-form" disabled={busy || !canManage || !selectedCase || !rubricRevision}><legend>{text("排队答案验收", "Queue answer evaluation")}</legend>
          <label className="workbench-field"><span>{text("Native Agent", "Native Agent")}</span><select name="agent_id" required>{activeAgents.map(item => <option key={item.agent_id} value={item.agent_id}>{item.display_name || item.agent_id} · {item.llm_profile_id}</option>)}</select></label>
          <label className="workbench-field"><span>{text("入口", "Entry point")}</span><select name="entry_kind"><option value="PORTAL">Portal</option><option value="CHANNEL">{text("频道", "Channel")}</option></select></label>{reason("验收运行原因", "Evaluation run reason")}<button className="primary-button">{text("创建验收运行", "Create evaluation run")}</button><p>{text(`当前 Rubric 修订：${rubricRevision || "未登记"} · 策略：${policy?.version || "不可用"}`, `Rubric revision: ${rubricRevision || "not registered"} · policy: ${policy?.version || "unavailable"}`)}</p>
        </fieldset></form>
        <form onSubmit={openEvaluation}><fieldset className="operation-explainer-form" disabled={busy || !canManage}><legend>{text("打开已有验收运行", "Open an existing evaluation run")}</legend>{field("run_id", "验收运行标识", "Evaluation run ID", { required: true, maxLength: 128 })}<p>{text("独立评审者可输入运行标识；当前来源与域权限会重新核验。", "An independent reviewer can enter a run ID; current source and domain authority are rechecked.")}</p><button className="small-button">{text("打开运行", "Open run")}</button></fieldset></form>
        {runRecord && <section><p>{runRecord.run?.run_id} · {statusLabel(runRecord.run?.status, text)} · {runRecord.observation?.generation_kind ? statusLabel(runRecord.observation.generation_kind, text) : text("未生成", "not generated")}</p>{runRecord.output?.answer && <p className="continuity-body">{runRecord.output.answer}</p>}{runRecord.output?.assessment && <pre className="continuity-body">{JSON.stringify(runRecord.output.assessment, null, 2)}</pre>}
          {runRecord.run?.status === "PENDING" && <><label className="continuity-source-check"><input type="checkbox" checked={allowModelSend} onChange={e => setAllowModelSend(e.target.checked)} /><span>{text("确认此验收可能调用 Agent 绑定的外部模型。", "Confirm this evaluation may call the Agent's configured external model.")}</span></label><button type="button" className="primary-button" disabled={busy || !allowModelSend} onClick={executeEvaluation}>{text("执行验收", "Execute evaluation")}</button></>}
          {runRecord.output && <form onSubmit={reviewEvaluation}><fieldset className="operation-explainer-form" disabled={busy || !canWrite || runRecord.run?.actor_id === principalId}><legend>{text("独立人工事实与引用评审", "Independent factual and citation review")}</legend><label className="continuity-source-check"><input type="checkbox" name="factual_correct" /><span>{text("事实正确", "Factual claims are correct")}</span></label><label className="continuity-source-check"><input type="checkbox" name="citations_supported" /><span>{text("引用有来源支持", "Citations are supported")}</span></label>{reason("评审理由", "Review reason")}<button className="primary-button">{text("记录独立评审", "Record independent review")}</button></fieldset></form>}
          <p>{text("本次运行不单独构成发布验收；是否满足完整发布门槛应结合其他证据判断。", "This run alone does not establish release acceptance; evaluate it with the rest of the evidence.")}</p>
        </section>}
      </section>
    </div>}
  </section>;
}
