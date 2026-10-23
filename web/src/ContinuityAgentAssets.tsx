import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Database, Download, Search, ShieldCheck } from "lucide-react";
import { statusLabel } from "./statusLabels";

type Row = Record<string, any>;
type SourceRef = { family: string; entity_id: string; revision_id: string; content_digest: string };
type RequestScope = { active: boolean; generation: number };
type Props = {
  request: (path: string, options?: RequestInit) => Promise<Row>;
  text: (zh: string, en: string) => string;
  domain: string;
  canWrite: boolean;
  canManage: boolean;
  canOperateAgents: boolean;
  onSourceRefsChange: (sources: SourceRef[]) => void;
};
const id = () => crypto.randomUUID();
const ROOT = "/api/agent-extensions";
const sourceKey = (source: SourceRef) => JSON.stringify(source);
const uniqueRows = (rows: Row[], key: string): Row[] => [...new Map(rows.map(item => [item[key], item])).values()];

export default function ContinuityAgentAssets({ request, text, domain, canWrite, canManage, canOperateAgents, onSourceRefsChange }: Props) {
  const [view, setView] = useState<"assets" | "sources" | "recommend">("assets");
  const [agents, setAgents] = useState<Row[]>([]);
  const [agent, setAgent] = useState("");
  const [agentCursor, setAgentCursor] = useState("");
  const [bindings, setBindings] = useState<Row[]>([]);
  const [bindingCursor, setBindingCursor] = useState("");
  const [sources, setSources] = useState<Row[]>([]);
  const [sourceCursor, setSourceCursor] = useState("");
  const [references, setReferences] = useState<SourceRef[]>([]);
  const [assemblies, setAssemblies] = useState<Row[]>([]);
  const [selectedAssembly, setSelectedAssembly] = useState("");
  const [selectedBindings, setSelectedBindings] = useState<string[]>([]);
  const [job, setJob] = useState<Row | null>(null);
  const [recommendations, setRecommendations] = useState<Row | null>(null);
  const [loadedSkill, setLoadedSkill] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const lock = useRef(false);
  const pending = useRef(new Map<string, Row>());
  const inventoryDomain = useRef("");
  const inventoryScope = useMemo<RequestScope>(() => ({ active: true, generation: 0 }), [domain]);
  const selectedScope = useMemo<RequestScope>(() => ({ active: true, generation: 0 }), [domain, agent, canWrite, canManage, canOperateAgents]);
  const guardedRequest = async (scope: RequestScope, path: string, options?: RequestInit) => {
    const generation = scope.generation;
    if (!scope.active) throw new Error("Stale selection");
    const value = await request(path, options);
    if (!scope.active || generation !== scope.generation) throw new Error("Stale selection");
    return value;
  };
  const scopedRequest = (path: string, options?: RequestInit) => guardedRequest(selectedScope, path, options);

  useEffect(() => {
    selectedScope.active = true; selectedScope.generation++;
    lock.current = false; setBusy(false); setError(""); setNotice("");
    return () => { selectedScope.active = false; };
  }, [selectedScope]);

  const run = async (action: () => Promise<void>) => {
    if (lock.current || !selectedScope.active) return;
    const generation = selectedScope.generation;
    const current = () => selectedScope.active && selectedScope.generation === generation;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (e) { if (current()) setError(e instanceof Error ? e.message : text("操作失败", "Operation failed")); }
    finally { if (current()) { lock.current = false; setBusy(false); } }
  };
  const post = async (path: string, body: Row) => {
    const signature = path + JSON.stringify(body);
    const payload = pending.current.get(signature) || { ...body, idempotency_key: id() };
    pending.current.set(signature, payload);
    const value = await scopedRequest(path, { method: "POST", body: JSON.stringify(payload) });
    pending.current.delete(signature);
    return value;
  };
  const postRaw = async (path: string, body: Row) => scopedRequest(path, { method: "POST", body: JSON.stringify(body) });
  const addReferences = (items: SourceRef[]) => {
    setReferences(previous => {
      const merged = new Map(previous.map(item => [sourceKey(item), item]));
      for (const item of items) merged.set(sourceKey(item), item);
      const next = [...merged.values()];
      return next;
    });
  };
  useEffect(() => { onSourceRefsChange(references); }, [references, onSourceRefsChange]);
  const loadAgents = async (cursor = "") => {
    const value = await guardedRequest(inventoryScope, `/api/continuity-recipients?security_domain_id=${encodeURIComponent(domain)}&limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
    const items = (value.items || []).filter((item: Row) => item.principal_type === "AGENT" && item.status === "ACTIVE");
    inventoryDomain.current = domain;
    setAgents(previous => uniqueRows(cursor ? [...previous, ...items] : items, "principal_id"));
    setAgentCursor(value.next_cursor || "");
    if (!cursor) setAgent(previous => items.some((item: Row) => item.principal_id === previous) ? previous : items[0]?.principal_id || "");
  };
  const loadAgentData = async (next: false | "bindings" | "sources" = false) => {
    if (!selectedScope.active || inventoryDomain.current !== domain || !agent || !(canManage || canOperateAgents)) return;
    const generation = selectedScope.generation;
    const [assetPage, sourcePage] = await Promise.all([
      !next || next === "bindings" && bindingCursor ? scopedRequest(`${ROOT}/asset-bindings?security_domain_id=${encodeURIComponent(domain)}&agent_id=${encodeURIComponent(agent)}&limit=50${next ? `&after=${encodeURIComponent(bindingCursor)}` : ""}`) : Promise.resolve(null),
      !next || next === "sources" && sourceCursor ? scopedRequest(`${ROOT}/sources?security_domain_id=${encodeURIComponent(domain)}&agent_id=${encodeURIComponent(agent)}&limit=50${next ? `&after=${encodeURIComponent(sourceCursor)}` : ""}`) : Promise.resolve(null),
    ]);
    if (!selectedScope.active || generation !== selectedScope.generation) return;
    if (assetPage) {
      setBindings(previous => uniqueRows(next ? [...previous, ...(assetPage.items || [])] : assetPage.items || [], "binding_id"));
      if (!next) setSelectedBindings(previous => previous.filter(value => (assetPage.items || []).some((item: Row) => item.binding_id === value)));
      setBindingCursor(assetPage.next_cursor || "");
    }
    if (sourcePage) {
      setSources(previous => uniqueRows(next ? [...previous, ...(sourcePage.items || [])] : sourcePage.items || [], "source_id"));
      setSourceCursor(sourcePage.next_cursor || "");
    }
  };
  useEffect(() => {
    inventoryScope.active = true; inventoryScope.generation++;
    const generation = inventoryScope.generation;
    inventoryDomain.current = "";
    setAgents([]); setAgent(""); setAgentCursor("");
    setReferences([]); onSourceRefsChange([]); setAssemblies([]); setSelectedAssembly(""); setRecommendations(null); setLoadedSkill(null);
    void guardedRequest(inventoryScope, "/api/context/assemblies?security_domain_id=" + encodeURIComponent(domain) + "&limit=50").then(page => {
      setAssemblies(page.items || []);
    }).catch(() => undefined);
    void loadAgents().catch(e => { if (inventoryScope.active && inventoryScope.generation === generation) setError(e instanceof Error ? e.message : text("Agent 列表加载失败", "Agent inventory failed")); });
    return () => { inventoryScope.active = false; };
  }, [domain]);
  useEffect(() => {
    setBindings([]); setSources([]); setBindingCursor(""); setSourceCursor(""); setSelectedBindings([]); setJob(null); setRecommendations(null); setLoadedSkill(null);
    if (agent && (canManage || canOperateAgents)) void run(() => loadAgentData());
  }, [selectedScope]);

  const loadSyncReferences = async (value: Row) => {
    const refs: SourceRef[] = [];
    for (const item of value.imports || []) {
      const candidate = await scopedRequest(`/api/artifact-candidates/${encodeURIComponent(item.candidate_id)}`);
      for (const source of candidate.payload?.sources || []) refs.push(source);
    }
    if (selectedScope.active) addReferences(refs);
    return refs.length;
  };
  const referenceLabel = (source: SourceRef) => `${statusLabel(source.family, text)} · ${source.entity_id} · ${source.revision_id}`;
  const reason = (data: FormData) => String(data.get("reason") || "").trim();

  const configureSource = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    void run(async () => {
      const kind = String(data.get("kind"));
      const value = await post(`${ROOT}/sources`, {
        security_domain_id: domain, agent_id: agent, kind, endpoint: String(data.get("endpoint")).trim(),
        pinned_commit: kind === "GITHUB" ? String(data.get("pinned_commit")).trim() : "",
        paths: kind === "GITHUB" ? String(data.get("paths")).split("\n").map(x => x.trim()).filter(Boolean) : ["/"],
        credential_ref: String(data.get("credential_ref") || "").trim(), content_types: ["text/plain", "text/markdown", "text/html"],
        max_bytes: Number(data.get("max_bytes")), max_attempts: 3, reason: reason(data),
      });
      await loadAgentData();
      if (!selectedScope.active) return;
      form.reset(); setNotice(text("只读来源已配置：", "Read-only source configured: ") + value.source_id);
    });
  };
  const syncSource = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void run(async () => {
      const sourceId = String(data.get("source_id"));
      const queued = await post(`${ROOT}/sources/${encodeURIComponent(sourceId)}/sync`, { reason: reason(data), task_id: null });
      const result = await scopedRequest(`${ROOT}/source-sync-jobs/${encodeURIComponent(queued.job_id)}/run`, { method: "POST" });
      setJob(result); const count = await loadSyncReferences(result);
      await loadAgentData();
      if (!selectedScope.active) return;
      setNotice(text(`同步完成，发现 ${count} 条精确来源引用。生成的候选仍需独立审核。`, `Sync finished with ${count} exact source references. Resulting candidates still require independent review.`));
    });
  };
  const recommend = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void run(async () => {
      const value = await postRaw(`${ROOT}/directory/recommend`, { security_domain_id: domain, query: String(data.get("query")), limit: 10, candidate_limit: 100 });
      if (selectedScope.active) setRecommendations(value);
    });
  };
  const loadRecommendation = (item: Row) => void run(async () => {
    const value = await postRaw(`${ROOT}/directory/load`, { value: { security_domain_id: domain, family: "SKILL", entity_id: item.entity_id, version: item.version, content_digest: item.content_digest } });
    if (selectedScope.active) setLoadedSkill(value);
  });
  const bindAsset = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void run(async () => {
      const source = data.get("source_option") === "manual" ? {
        family: String(data.get("family")), entity_id: String(data.get("entity_id")).trim(), revision_id: String(data.get("revision_id")).trim(), content_digest: String(data.get("content_digest")).trim(),
      } : JSON.parse(String(data.get("source_option"))) as SourceRef;
      const value = await post(`${ROOT}/asset-bindings`, {
        security_domain_id: domain, agent_id: agent, source, purpose: String(data.get("purpose")), priority: Number(data.get("priority")),
        resolution_policy: String(data.get("resolution_policy")), valid_until: null, reason: reason(data),
      });
      await loadAgentData();
      if (selectedScope.active) setNotice(text("资产绑定已保存：", "Asset binding saved: ") + value.binding_id);
    });
  };
  const changeBindingState = (binding: Row, status: string) => void run(async () => {
    await post(`${ROOT}/asset-bindings/${encodeURIComponent(binding.binding_id)}/state`, { expected_version: binding.version, status, reason: text("管理者更新绑定状态", "Manager changed binding state") });
    await loadAgentData();
  });
  const assemble = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void run(async () => {
      const path = `${ROOT}/asset-bindings/assemble`;
      const body = {
        binding_ids: selectedBindings,
        assembly: { security_domain_id: domain, work_contract_id: null, handoff_id: null, sources: [], mandatory_sources: [],
          query_text: String(data.get("query_text") || ""), token_budget: Number(data.get("token_budget")), entry_limit: Number(data.get("entry_limit")),
          ttl_seconds: 300, purpose: String(data.get("purpose")) },
      };
      const signature = path + JSON.stringify(body);
      const payload = pending.current.get(signature) || { ...body, assembly: { ...body.assembly, request_id: id(), idempotency_key: id() } };
      pending.current.set(signature, payload);
      const value = await postRaw(path, payload);
      pending.current.delete(signature);
      if (!selectedScope.active) return;
      addReferences((value.items || []).map((item: Row) => ({ family: item.family, entity_id: item.entity_id, revision_id: item.revision_id, content_digest: item.content_digest })));
      setNotice(text("上下文已组装，尚未发送给模型。", "Context assembled; it has not been sent to a model."));
    });
  };

  const input = (name: string, zh: string, en: string, props: Row = {}) => <label className="workbench-field"><span>{text(zh, en)}</span><input name={name} {...props} /></label>;
  const activeRefs = references.filter(item => item.content_digest && item.revision_id && item.entity_id);
  const assetRefs = activeRefs.filter(item => ["MEMORY", "KNOWLEDGE", "SKILL", "GRAPH", "SOURCE"].includes(item.family));
  const views = [["assets", text("资产绑定", "Asset bindings"), Database], ["sources", text("来源同步", "Source sync"), Download], ["recommend", text("Skill 推荐", "Skill recommendations"), Search]] as const;

  return <section className="panel continuity-extension-panel" aria-label={text("Agent 资产与来源", "Agent assets and sources")}>
    <div className="continuity-extension-heading"><div><h3>{text("Agent 资产与来源", "Agent assets and sources")}</h3><p>{text("来源、绑定和上下文仍以数据库记录为准；每次使用都会重新核验当前权限。", "Sources, bindings and context remain database-authoritative; current permissions are rechecked at every use.")}</p></div>
      <label className="workbench-field continuity-agent-select"><span>{text("目标 Agent", "Target Agent")}</span><select value={agent} disabled={busy} onChange={e => setAgent(e.target.value)}><option value="">{text("选择 Agent", "Select an Agent")}</option>{agents.map(item => <option key={item.principal_id} value={item.principal_id}>{item.display_name || item.principal_id} · {item.principal_id}</option>)}</select>{agentCursor && <button type="button" className="small-button" disabled={busy} onClick={() => void run(() => loadAgents(agentCursor))}>{text("加载更多 Agent", "Load more Agents")}</button>}</label>
    </div>
    <div className="continuity-extension-tabs" role="tablist" aria-label={text("Agent 扩展能力", "Agent extensions")}>{views.map(([key, label, Icon]) => <button key={key} role="tab" aria-selected={view === key} className={view === key ? "active" : ""} type="button" onClick={() => setView(key)}><Icon size={16} />{label}</button>)}</div>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!(canManage || canOperateAgents) && view !== "recommend" && <p>{text("资产变更和来源同步由具备 Agent 操作权限的人员在 Dashboard 中管理。", "Asset changes and source synchronization are managed in the Dashboard by authorized Agent operators.")}</p>}
    <div className="page-toolbar continuity-reference-toolbar"><label className="workbench-field"><span>{text("从组装记录导入精确引用", "Import exact references from an assembly")}</span><select value={selectedAssembly} disabled={busy} onChange={e => setSelectedAssembly(e.target.value)}><option value="">{text("选择我的组装记录", "Select one of my assemblies")}</option>{assemblies.map(item => <option key={item.assembly_id} value={item.assembly_id}>{String(item.assembly_id).slice(-12)} · {statusLabel(item.status, text)}</option>)}</select></label><button type="button" className="small-button" disabled={busy || !selectedAssembly} onClick={() => void run(async () => {
      const value = await scopedRequest(`/api/context/assemblies/${encodeURIComponent(selectedAssembly)}/items`);
      if (!selectedScope.active) return;
      addReferences((value.items || []).map((item: Row) => ({ family: item.family, entity_id: item.entity_id, revision_id: item.revision_id, content_digest: item.content_digest })));
      setNotice(text("已导入所选组装的精确来源引用；正文未加载到页面。", "Exact source references imported from the selected assembly; its body is not loaded into the page."));
    })}>{text("导入来源引用", "Import source references")}</button>{canManage && <button type="button" className="small-button" disabled={busy} title={text("需要当前安全域的所有者或管理员权限；仅导入版本引用。", "Requires owner or administrator authority in this domain; imports revision references only.")} onClick={() => void run(async () => {
      const page = await scopedRequest("/api/context-publications?security_domain_id=" + encodeURIComponent(domain) + "&limit=100");
      if (!selectedScope.active) return;
      addReferences((page.items || []).filter((item: Row) => item.status === "PUBLISHED").map((item: Row) => ({
        family: item.family, entity_id: item.entity_id, revision_id: item.source_revision_id, content_digest: item.content_digest,
      })));
      setNotice(text("已导入本域已发布来源的精确引用；正文未加载到页面。", "Exact references imported from this domain's publications; bodies are not loaded into the page."));
    })}>{text("导入已发布来源版本", "Import published source revisions")}</button>}</div>
    {!agent && <p>{text("当前安全域没有可管理的活动 Agent。", "No active Agent is available in this security domain.")}</p>}
    {view === "assets" && agent && <div className="continuity-extension-grid">
      <section className="continuity-extension-column"><h4>{text("绑定精确来源", "Bind an exact source")}</h4>
        <form onSubmit={bindAsset}><fieldset className="operation-explainer-form" disabled={busy || !canOperateAgents}><legend>{text("创建数据库资产绑定", "Create database-backed asset binding")}</legend>
          <label className="workbench-field"><span>{text("来源版本", "Source revision")}</span><select name="source_option" required defaultValue=""><option value="">{text("选择已知精确来源", "Select a known exact source")}</option>{assetRefs.map(item => <option key={sourceKey(item)} value={JSON.stringify(item)}>{referenceLabel(item)}</option>)}<option value="manual">{text("手动填写精确引用（高级）", "Enter an exact reference manually (advanced)")}</option></select></label>
          <label className="workbench-field"><span>{text("解析策略", "Resolution policy")}</span><select name="resolution_policy"><option value="PINNED">{text("固定版本", "Pinned revision")}</option><option value="CURRENT">{text("当前版本（仅支持记忆/知识/技能）", "Current revision (Memory/Knowledge/Skill)")}</option></select></label>
          <label className="workbench-field"><span>{text("优先级", "Priority")}</span><input name="priority" type="number" min={0} max={100} defaultValue={50} required /></label>
          {input("purpose", "使用目的", "Purpose", { required: true, maxLength: 1000 })}{input("reason", "操作原因", "Reason", { required: true, maxLength: 1000 })}
          <details><summary>{text("手动精确引用字段", "Manual exact-reference fields")}</summary>
            <label className="workbench-field"><span>{text("来源类型", "Source family")}</span><select name="family">{["MEMORY", "KNOWLEDGE", "SKILL", "GRAPH", "SOURCE"].map(item => <option key={item} value={item}>{statusLabel(item, text)}</option>)}</select></label>
            {input("entity_id", "来源实体标识", "Source entity ID", { maxLength: 128 })}{input("revision_id", "精确修订标识", "Exact revision ID", { maxLength: 128 })}{input("content_digest", "SHA-256 内容摘要", "SHA-256 content digest", { pattern: "[0-9a-f]{64}", maxLength: 64 })}
          </details><button className="primary-button">{text("保存资产绑定", "Save asset binding")}</button>
        </fieldset></form>
      </section>
      <section className="continuity-extension-column"><div className="page-toolbar"><h4>{text("已启用的绑定", "Active bindings")}</h4><button className="small-button" type="button" disabled={busy} onClick={() => void run(() => loadAgentData())}>{text("刷新", "Refresh")}</button></div>
        {bindings.length ? <ul className="continuity-record-list">{bindings.map(item => <li key={item.binding_id}><label><input type="checkbox" checked={selectedBindings.includes(item.binding_id)} onChange={e => setSelectedBindings(previous => e.target.checked ? [...previous, item.binding_id] : previous.filter(value => value !== item.binding_id))} /> <span>{item.name || item.purpose || item.binding_id}<small>{statusLabel(item.source?.family, text)} · {item.source?.entity_id} · {item.source?.revision_id} · v{item.version}</small></span></label><button className="small-button" type="button" disabled={busy || !canOperateAgents} title={text("暂停绑定", "Pause binding")} onClick={() => changeBindingState(item, "PAUSED")}>{text("暂停", "Pause")}</button></li>)}</ul> : <p>{text("尚无可用绑定。", "No active bindings.")}</p>}
        {bindingCursor && <button className="small-button" type="button" disabled={busy} onClick={() => void run(() => loadAgentData("bindings"))}>{text("加载更多", "Load more")}</button>}
        <form onSubmit={assemble}><fieldset className="operation-explainer-form" disabled={busy || !canWrite || !selectedBindings.length}><legend>{text("使用选中绑定组装上下文", "Assemble context from selected bindings")}</legend>
          <label className="workbench-field"><span>{text("当前查询", "Current query")}</span><textarea name="query_text" rows={2} maxLength={4000} /></label>
          <label className="workbench-field"><span>{text("Token 预算", "Token budget")}</span><input name="token_budget" type="number" min={1} max={131072} defaultValue={4096} /></label>
          <label className="workbench-field"><span>{text("条目上限", "Entry limit")}</span><input name="entry_limit" type="number" min={0} max={100} defaultValue={20} /></label>
          {input("purpose", "组装用途", "Assembly purpose", { required: true, maxLength: 1000 })}<button className="primary-button">{text("组装并查看结果", "Assemble and inspect")}</button>
          <p>{text("组装仅生成短期、带预算的上下文记录；不会自动调用模型或改变长期记忆。", "Assembly creates only a short-lived, budgeted context record; it does not call a model or change long-term Memory.")}</p>
        </fieldset></form>
      </section>
    </div>}
    {view === "sources" && agent && <div className="continuity-extension-grid">
      <section className="continuity-extension-column"><h4>{text("配置只读来源", "Configure a read-only source")}</h4>
        <form onSubmit={configureSource}><fieldset className="operation-explainer-form" disabled={busy || !canManage}><legend>{text("来源配置", "Source configuration")}</legend>
          <label className="workbench-field"><span>{text("来源类型", "Source kind")}</span><select name="kind" defaultValue="DOCUMENT"><option value="DOCUMENT">{text("单个 HTTPS 文档", "Single HTTPS document")}</option><option value="GITHUB">{text("固定提交的 GitHub 仓库", "Pinned GitHub commit")}</option></select></label>
          {input("endpoint", "HTTPS 地址", "HTTPS URL", { type: "url", required: true, maxLength: 2000, placeholder: "https://docs.example.org/guide.html" })}
          {input("pinned_commit", "完整提交 SHA（GitHub）", "Full commit SHA (GitHub)", { pattern: "[0-9a-f]{40}", maxLength: 40 })}
          <label className="workbench-field"><span>{text("限定路径（每行一个）", "Allowed paths (one per line)")}</span><textarea name="paths" rows={3} defaultValue="/" maxLength={25000} /></label>
          {input("credential_ref", "主机凭据引用（可选，不填写密钥）", "Host credential reference (optional; never enter a secret)", { maxLength: 100, pattern: "[A-Z][A-Z0-9_]{0,99}" })}
          <label className="workbench-field"><span>{text("最大导入字节数", "Maximum import size")}</span><input name="max_bytes" type="number" min={128} max={262144} defaultValue={16384} required /></label>
          {input("reason", "操作原因", "Reason", { required: true, maxLength: 1000 })}<button className="primary-button">{text("保存只读来源", "Save read-only source")}</button>
          <p>{text("仅 HTTPS/443；禁止跳转到其他地址。GitHub 必须固定完整提交 SHA。导入内容只形成待审候选，不会自动发布。", "HTTPS/443 only; redirects are rejected. GitHub requires a full pinned commit SHA. Imports become pending candidates and are never published automatically.")}</p>
        </fieldset></form>
      </section>
      <section className="continuity-extension-column"><div className="page-toolbar"><h4>{text("来源与同步", "Sources and sync")}</h4><button className="small-button" type="button" disabled={busy} onClick={() => void run(() => loadAgentData())}>{text("刷新", "Refresh")}</button></div>
        {sources.length ? <ul className="continuity-record-list">{sources.map(item => <li key={item.source_id}><label><input type="radio" name="sync-source" checked={job?.source_id === item.source_id} onChange={() => setJob({ source_id: item.source_id })} /><span>{statusLabel(item.source_kind, text)} · {item.source_id}<small>{text("状态", "State")}: {statusLabel(item.status, text)} · {text("版本", "Version")}: {item.row_version} · {item.checkpoint_digest || text("尚未同步", "not synced")}</small></span></label><button className="small-button" type="button" disabled={busy || item.status !== "ACTIVE"} onClick={() => setJob({ source_id: item.source_id })}>{text("选择", "Select")}</button></li>)}</ul> : <p>{text("尚未配置来源。", "No configured sources.")}</p>}
        {sourceCursor && <button className="small-button" type="button" disabled={busy} onClick={() => void run(() => loadAgentData("sources"))}>{text("加载更多", "Load more")}</button>}
        <form onSubmit={syncSource}><fieldset className="operation-explainer-form" disabled={busy || !canOperateAgents || !job?.source_id}><legend>{text("立即同步所选来源", "Synchronize selected source")}</legend><input type="hidden" name="source_id" value={job?.source_id || ""} />{input("reason", "同步原因", "Reason", { required: true, maxLength: 1000 })}<button className="primary-button"><Download size={15} />{text("排队并执行一次", "Queue and run once")}</button></fieldset></form>
        {job?.job_id && <section><h4>{text("最近同步任务", "Latest sync job")}</h4><p>{job.job_id} · {statusLabel(job.status, text)} · {text("候选不会自动发布", "Candidates are not auto-published")}</p><ul>{(job.imports || []).map((item: Row) => <li key={item.revision_id}>{text("候选", "Candidate")}: {item.candidate_id} · {text("来源修订", "Source revision")}: {item.revision_id}</li>)}</ul></section>}
      </section>
    </div>}
    {view === "recommend" && <div className="continuity-extension-grid">
      <section className="continuity-extension-column"><h4>{text("查询感知 Skill 推荐", "Query-aware Skill recommendations")}</h4>
        <form onSubmit={recommend}><fieldset className="operation-explainer-form" disabled={busy}><legend>{text("输入任务或问题", "Describe the task or question")}</legend><label className="workbench-field"><span>{text("查询", "Query")}</span><textarea name="query" required maxLength={2000} rows={3} /></label><button className="primary-button"><Search size={15} />{text("查找相关 Skill", "Find relevant Skills")}</button></fieldset></form>
        {recommendations && <><p>{recommendations.candidate_count} {text("条授权范围内元数据候选；正文未加载，推荐不授予执行权限。", "authorized metadata candidates; bodies stay unloaded and recommendations grant no execution authority.")}</p><ul className="continuity-record-list">{(recommendations.items || []).map((item: Row) => <li key={item.entity_id}><span><strong>{item.name}</strong><small>{item.description || item.entity_id} · v{item.version} · {text("相关度", "relevance")}: {item.rank_score}</small></span><button className="small-button" type="button" disabled={busy} onClick={() => loadRecommendation(item)}>{text("读取精确版本", "Load exact version")}</button></li>)}</ul>{!recommendations.items?.length && <p>{text("没有匹配的 Skill。", "No matching Skill was found.")}</p>}</>}
      </section>
      <section className="continuity-extension-column"><h4><ShieldCheck size={16} /> {text("授权正文预览", "Authorized content preview")}</h4>{loadedSkill ? <><p>{loadedSkill.name} · v{loadedSkill.version} · {loadedSkill.content_digest}</p><pre className="continuity-body">{loadedSkill.content?.text_content || text("没有可显示的正文。", "No content is available to display.")}</pre><p>{text("仅在显式读取后展示。正文读取不授权执行；实际调用仍走既有工具/Skill 授权。", "Shown only after explicit loading. Reading does not authorize execution; invocation still uses existing Skill/tool authorization.")}</p></> : <p>{text("选择一个推荐项并显式读取其当前授权版本。", "Choose a recommendation and explicitly load its currently authorized revision.")}</p>}</section>
    </div>}
    <div className="continuity-extension-foot"><span>{text("精确来源引用", "Exact source references")}: {activeRefs.length}</span><button className="small-button" type="button" disabled={busy} onClick={() => void run(async () => { await loadAgentData(); if (selectedScope.active) await loadAgents(); })}>{text("刷新数据", "Refresh data")}</button></div>
  </section>;
}
