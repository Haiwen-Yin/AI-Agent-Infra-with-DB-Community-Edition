import React, { useEffect, useRef, useState } from "react";
import { RefreshCw, Save, ShieldCheck } from "lucide-react";

type Row = Record<string, any>;
export default function NetworkAccessPolicy({ request, text }: {
  request: (path: string, options?: RequestInit) => Promise<Row>;
  text: (zh: string, en: string) => string;
}) {
  const [policy, setPolicy] = useState<Row | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [mode, setMode] = useState("DENYLIST");
  const [rules, setRules] = useState("");
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<Row | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const mounted = useRef(false);
  const locked = useRef(false);
  const load = async () => {
    const next = await request("/api/platform/ip-access");
    if (!mounted.current) return;
    setPolicy(next); setEnabled(next.enabled); setMode(next.list_mode);
    setRules((next.rules || []).join("\n")); setReason(""); setPreview(null); setAcknowledged(false);
  };
  const edited = () => { setPreview(null); setAcknowledged(false); setSaved(false); };
  const run = async (action: "load" | "preview" | "save") => {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError(""); setSaved(false);
    try {
      if (action === "load") { await load(); return; }
      const proposed = { enabled, list_mode: mode, rules: rules.split(/\r?\n/).map(value => value.trim()).filter(Boolean) };
      const checked = await request("/api/platform/ip-access/preview", { method: "POST", body: JSON.stringify(proposed) });
      if (!mounted.current) return;
      setPreview(checked);
      if (action === "preview" || (!checked.current_source_allowed && !acknowledged)) return;
      if (!policy) return;
      await request("/api/platform/ip-access", { method: "PUT", body: JSON.stringify({ ...proposed,
        expected_revision: policy.revision, reason: reason.trim() }) });
      // The save response is authoritative. A follow-up GET could already be
      // denied when this administrator deliberately excludes their own source.
      if (checked.current_source_allowed) await load();
      else { setPolicy(null); setPreview(checked); }
      if (mounted.current) setSaved(true);
    } catch (caught) {
      if (mounted.current) {
        const message = caught instanceof Error ? caught.message : String(caught);
        setError(/changed|409/i.test(message)
          ? text("配置已被其他管理员修改，请重新读取后再保存。", "Another administrator changed this policy. Reload before saving.")
          : /reason|UTF-8/i.test(message)
          ? text("变更原因至少需要 3 个字符，且不能超过 2000 个 UTF-8 字节。", "The change reason needs at least 3 characters and must fit within 2000 UTF-8 bytes.")
          : /CIDR|prefix|IP address|512|rule/i.test(message)
          ? text("规则无效：每行填写一个 IPv4 / IPv6 地址或 CIDR 网段，最多 512 条，不支持域名、端口或区域标识。", "Invalid rules: use one IPv4 / IPv6 address or CIDR per line, up to 512; no hostnames, ports or zone IDs.")
          : text("操作未完成，请检查连接、权限和输入后重试。", "The operation could not be completed. Check the connection, permissions and input, then retry."));
      }
    } finally { locked.current = false; if (mounted.current) setBusy(false); }
  };
  useEffect(() => { mounted.current = true; void run("load"); return () => { mounted.current = false; }; }, []);
  return <section className="panel ip-access-panel page-stack" data-testid="ip-access-page" aria-label={text("访问 IP 限制", "Source IP access")}>
    <div className="ip-access-heading"><div><h3>{text("访问 IP 限制", "Source IP access")}</h3>
      <p>{text("统一限制 Dashboard、Portal 和接口的来源地址。关闭时不按名单限制；开启后约 1 秒内在各服务进程生效。", "Restrict sources for Dashboard, Portal and APIs. Lists are inactive while disabled; changes propagate across service processes within about one second.")}</p></div>
      <button type="button" className="small-button" disabled={busy} onClick={() => void run("load")}><RefreshCw size={14} />{text("重新读取", "Reload")}</button></div>
    <div className="ip-access-recovery" role="note"><ShieldCheck size={19} /><p>{text("应急地址 127.0.0.1 始终保留，仅限直接本机连接，仍需正常登录和管理权限。本机代理必须使用其他来源地址；经代理转发不享有应急放行，其他回环地址按规则处理。", "127.0.0.1 is always reserved for direct local recovery, with normal login and management permissions. Local proxies must use a different source address. Forwarded requests have no recovery exemption; other loopback addresses follow the policy.")}</p></div>
    {error && <p role="alert" className="form-error">{error}</p>}
    {saved && <p role="status">{text("访问策略已保存并记录审计。", "Access policy saved and audited.")}</p>}
    {policy && <form className="configuration-form" onSubmit={event => { event.preventDefault(); void run("save"); }}>
      <fieldset disabled={busy} className="ip-access-fields">
        <legend>{text("策略版本", "Policy revision")} {policy.revision}</legend>
        <p className="ip-access-source">{text("当前识别来源：", "Detected source: ")}<code>{policy.current_source}</code>
          {policy.recovery_connection && text(" · 应急连接", " · Recovery connection")}{policy.proxied && text(" · 可信代理转发", " · Trusted proxy")}</p>
        <div className="ip-access-controls"><label className="checkbox-field ip-access-enable-toggle"><input type="checkbox" checked={enabled} onChange={event => { edited(); setEnabled(event.target.checked); }} /><span>{text("开启访问 IP 限制", "Enable source IP restriction")}</span></label>
          <label className="ip-access-mode-control">{text("名单模式", "List mode")}<select aria-label={text("名单模式", "List mode")} value={mode} onChange={event => { edited(); setMode(event.target.value); }}>
            <option value="ALLOWLIST">{text("白名单：仅允许匹配来源", "Allowlist: admit matching sources")}</option>
            <option value="DENYLIST">{text("黑名单：拒绝匹配来源", "Denylist: reject matching sources")}</option>
          </select></label></div>
        <label>{text("IP 地址或网段（每行一条）", "IP addresses or CIDRs (one per line)")}
          <textarea data-testid="ip-access-rules" rows={7} maxLength={33280} value={rules} spellCheck={false} placeholder={"192.0.2.10\n198.51.100.0/24\n2001:db8::/32"} onChange={event => { edited(); setRules(event.target.value); }} /></label>
        <p className="field-help">{text("支持 IPv4、IPv6，最多 512 条。网段会规范化并去重；空白名单仅保留应急访问，空黑名单不限制来源。IPv4 映射 IPv6 按对应 IPv4 处理。", "IPv4 and IPv6, up to 512 rules. Networks are normalized and deduplicated. An empty allowlist permits only recovery; an empty denylist restricts no source. IPv4-mapped IPv6 uses the corresponding IPv4.")}</p>
        <div className="ip-access-guide" role="note">
          <div className="ip-access-guide-heading"><h4>{text("配置示例", "Configuration examples")}</h4><p>{text("下面的地址是文档保留地址，仅用于说明格式；使用前请替换为实际来源地址。每行一条，不要填写端口、域名或 http://。", "The addresses below are documentation-only examples. Replace them with your real source addresses before saving. Use one per line; do not add ports, hostnames or http://.")}</p></div>
          <div className="ip-access-examples">
            <div><strong>{text("白名单：仅允许办公网", "Allowlist: office networks only")}</strong><code>{"198.51.100.0/24\n2001:db8:1234::/48"}</code><small>{text("适合固定办公网或 VPN 出口；未匹配来源都会被拒绝。", "Use for fixed office or VPN egress ranges; every other source is rejected.")}</small></div>
            <div><strong>{text("白名单：只允许一台管理机", "Allowlist: one administrator host")}</strong><code>{"192.0.2.10/32\n2001:db8::10/128"}</code><small>{text("单个地址使用 /32（IPv4）或 /128（IPv6）表示；请保留本机应急登录能力。", "Use /32 for one IPv4 host or /128 for one IPv6 host; keep direct local recovery available.")}</small></div>
            <div><strong>{text("黑名单：阻断问题网段", "Denylist: block problem networks")}</strong><code>{"203.0.113.0/24\n2001:db8:bad::/48"}</code><small>{text("适合只阻断少量已知来源；其他来源仍可访问。", "Use when only a small set of known sources should be blocked; other sources remain allowed.")}</small></div>
          </div>
          <p className="ip-access-guide-tip">{text("建议先点击“预检规则”，确认当前识别来源可以继续访问，再填写变更原因并保存。保存后约 1 秒内在其他服务进程生效。", "Select Preview rules first and confirm that the detected source retains access, then enter a reason and save. Other service processes apply the change within about one second.")}</p>
        </div>
        <label>{text("变更原因", "Change reason")}<input minLength={3} maxLength={2000} value={reason} onChange={event => setReason(event.target.value)} /></label>
        <p>{text("变更原因至少 3 个字符，最多 2000 个 UTF-8 字节；中文通常每字占 3 字节。", "Use at least 3 characters and no more than 2000 UTF-8 bytes; most Chinese characters use 3 bytes each.")}</p>
        {preview && <div className="ip-access-preview" role="status"><p>{preview.current_source_allowed
          ? text("预检通过：当前来源可继续访问。", "Preview: the current source will retain access.")
          : text("当前来源将被限制。保存后页面与接口将无法继续访问，请先确认可以通过 127.0.0.1 应急登录。", "This source will be restricted. Pages and APIs will become unavailable after saving. Confirm that direct 127.0.0.1 recovery is available first.")}</p>
          <p>{text("规范化规则：", "Normalized rules: ")}{preview.rules.length ? <code>{preview.rules.join(", ")}</code> : text("无", "None")}</p>
          {!preview.current_source_allowed && <label className="checkbox-field"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />{text("我已确认应急访问方式，仍要保存", "I have confirmed recovery access and want to save")}</label>}</div>}
        <div className="actions-row"><button type="button" className="small-button" onClick={() => void run("preview")}>{text("预检规则", "Preview rules")}</button>
          <button className="primary-button" disabled={Array.from(reason.trim()).length < 3 || new TextEncoder().encode(reason.trim()).byteLength > 2000}><Save size={14} />{text("保存访问策略", "Save access policy")}</button></div>
      </fieldset>
    </form>}
    {!!policy?.history?.length && <details className="ip-access-history"><summary>{text("最近 20 次策略记录", "Last 20 policy revisions")}</summary>
      <div className="table-scroll"><table><thead><tr>{[text("版本", "Revision"), text("状态", "State"), text("模式", "Mode"), text("操作人", "Actor"), text("原因", "Reason")].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>
        {policy.history.map((item: Row) => <tr key={item.revision}><td>{item.revision}</td><td>{item.enabled === "Y" ? text("开启", "Enabled") : text("关闭", "Disabled")}</td>
          <td>{item.list_mode === "ALLOWLIST" ? text("白名单", "Allowlist") : text("黑名单", "Denylist")}</td><td>{item.updated_by}</td><td>{item.reason}</td></tr>)}</tbody></table></div>
    </details>}
  </section>;
}
