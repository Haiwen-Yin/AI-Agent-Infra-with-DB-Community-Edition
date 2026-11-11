import React, { useEffect, useRef, useState } from "react";
import { RefreshCw, Save } from "lucide-react";
import { usePageResource } from "./usePageResource";

type Row = Record<string, any>;
export default function PortalKnowledgePolicy({ request, text }: {
  request: (path: string, options?: RequestInit) => Promise<Row>;
  text: (zh: string, en: string) => string;
}) {
  const [policy, setPolicy] = useState<Row | null>(null);
  const [profiles, setProfiles] = useState<Row[]>([]);
  const [mode, setMode] = useState("KNOWLEDGE_FIRST");
  const [supplement, setSupplement] = useState(false);
  const [disclosure, setDisclosure] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [organizations, setOrganizations] = useState<Row[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const organization = usePageResource<Row>(organizationId ? `/api/knowledge/organization-groups/${encodeURIComponent(organizationId)}` : null, request, {});
  const organizationKnowledge: Row[] = organization.data.knowledge || [];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const mounted = useRef(false);
  const locked = useRef(false);
  const load = async () => {
    const [next, models, orgs] = await Promise.all([
      request("/api/platform/portal-knowledge-policy"), request("/api/platform/portal-llm-policy"),
      request("/api/knowledge/access-options"),
    ]);
    if (!mounted.current) return;
    setPolicy(next); setMode(next.mode); setSupplement(next.allow_model_supplement === "Y");
    setDisclosure(next.disclosure_profiles); setProfiles(models.profiles || []); setOrganizations(orgs.items || []); setReason("");
  };
  const run = async (save: boolean) => {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError(""); setSaved(false);
    try {
      if (save && policy) await request("/api/platform/portal-knowledge-policy", {
        method: "PUT", body: JSON.stringify({ mode, allow_model_supplement: mode === "KNOWLEDGE_FIRST" && supplement,
          disclosure_profiles: disclosure, expected_version: policy.version, reason: reason.trim() }),
      });
      await load();
      if (mounted.current) setSaved(save);
    } catch (error) {
      if (mounted.current) setError(error instanceof Error ? error.message : String(error));
    } finally { locked.current = false; if (mounted.current) setBusy(false); }
  };
  useEffect(() => { mounted.current = true; void run(false); return () => { mounted.current = false; }; }, []);
  const known = new Set(profiles.map((item) => String(item.profile_id)));
  return <section className="info-panel portal-knowledge-policy" aria-label={text("Portal 知识回答策略", "Portal knowledge answer policy")} aria-busy={busy}>
    <div className="page-toolbar"><h3>{text("Portal 知识回答策略", "Portal knowledge answer policy")}</h3>
      <button type="button" className="small-button" disabled={busy} onClick={() => void run(false)}><RefreshCw size={14} />{text("重新读取", "Reload")}</button></div>
    <p>{text("控制知识回答的模式和模型披露范围，适用于频道与 Portal。", "Control knowledge answer mode and model disclosure for Channels and Portal.")}</p>
    {error && <p role="alert">{error}</p>}
    {saved && <p role="status">{text("知识回答策略已保存", "Knowledge answer policy saved")}</p>}
    {busy && !policy && <p role="status">{text("正在读取知识策略…", "Loading knowledge policy…")}</p>}
    {policy && <form onSubmit={(event) => { event.preventDefault(); void run(true); }}>
      <fieldset disabled={busy} className="portal-policy-fields">
        <legend>{text("策略版本", "Policy version")} {policy.version}</legend>
        <label className="config-field"><span>{text("回答模式", "Answer mode")}</span><select value={mode} onChange={(event) => { setMode(event.target.value); setSaved(false); }}>
          <option value="KNOWLEDGE_FIRST">{text("知识优先", "Knowledge first")}</option>
          <option value="KNOWLEDGE_ONLY">{text("仅知识", "Knowledge only")}</option>
        </select></label>
        <label className="checkbox-field"><input type="checkbox" checked={mode === "KNOWLEDGE_FIRST" && supplement} disabled={mode === "KNOWLEDGE_ONLY"} onChange={(event) => { setSupplement(event.target.checked); setSaved(false); }} />{text("频道与 Portal 未命中知识时自动使用通用模型回答", "Use general model answers automatically when Channels or Portal find no knowledge match")}</label>
        <fieldset className="portal-policy-disclosure"><legend>{text("允许接收授权知识的模型配置", "Model profiles permitted to receive authorized knowledge")}</legend>
          <p>{text("仅向所选配置披露当前用户已获授权的知识。", "Disclose only the current user's authorized knowledge to selected profiles.")}</p>
          {[...profiles, ...disclosure.filter((id) => !known.has(id)).map((id) => ({ profile_id: id, profile_key: id, status: "UNAVAILABLE" }))].map((item) => {
            const id = String(item.profile_id);
            return <label className="checkbox-field" key={id}><input type="checkbox" checked={disclosure.includes(id)} onChange={(event) => { setDisclosure((old) => event.target.checked ? [...old, id] : old.filter((value) => value !== id)); setSaved(false); }} />{String(item.profile_key || id)}{!known.has(id) && text("（不可用）", " (unavailable)")}</label>;
          })}
          {!profiles.length && !disclosure.length && <p>{text("暂无模型配置", "No model profiles")}</p>}
        </fieldset>
        <label className="config-field"><span>{text("变更原因", "Change reason")}</span><input required minLength={3} maxLength={2000} value={reason} onChange={(event) => { setReason(event.target.value); setSaved(false); }} /><small>{text("至少 3 个字符，保存时校验当前策略版本。", "At least 3 characters; saving checks the current policy version.")}</small></label>
        <button className="primary-button" disabled={reason.trim().length < 3}><Save size={14} />{text("保存知识策略", "Save knowledge policy")}</button>
      </fieldset>
    </form>}
    <section className="portal-policy-coverage" aria-label={text("组织知识覆盖", "Organization knowledge coverage")} aria-busy={organization.loading}>
      <h4>{text("组织知识覆盖", "Organization knowledge coverage")}</h4>
      <label className="config-field"><span>{text("组织范围", "Organization scope")}</span>
        <select value={organizationId} disabled={busy} onChange={(event) => setOrganizationId(event.target.value)}>
          <option value="">{text("选择组织查看覆盖", "Select an organization")}</option>
          {organizations.map((item) => <option key={String(item.organization_id)} value={String(item.organization_id)}>{String(item.organization_name || item.organization_id)}</option>)}
        </select>
      </label>
      {organization.error ? <p role="alert">{organization.error} <button type="button" className="small-button" onClick={organization.reload}>{text("重试", "Retry")}</button></p> : <p role="status">{organization.loading ? text("正在读取组织知识覆盖…", "Loading organization knowledge coverage…") : organizationId ? text(`当前返回 ${organizationKnowledge.length} 条有效知识策略`, `${organizationKnowledge.length} active knowledge policies returned`) : text("选择组织后查看其知识覆盖。", "Select an organization to view its knowledge coverage.")}</p>}
      {organizationKnowledge.length > 20 && <p>{text("下方预览前 20 条。", "Previewing the first 20 policies below.")}</p>}
      <ul className="continuity-record-list">{organizationKnowledge.slice(0, 20).map((item) => <li key={String(item.entity_id || item.policy_id)}><span>{String(item.title || item.entity_id)} · {String(item.scope_type)}</span></li>)}</ul>
    </section>
  </section>;
}
