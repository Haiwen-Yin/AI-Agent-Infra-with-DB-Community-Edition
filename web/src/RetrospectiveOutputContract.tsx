import React, { useEffect, useRef, useState } from "react";

type Row = Record<string, any>;
export type RetrospectiveOutput = { mode: "TEXT_JSON" | "NATIVE_STRICT"; probeId?: string; profileId?: string; profileVersion?: number; family?: string; expiresAt?: string };
type Props = { request: (path: string, options?: RequestInit) => Promise<Row>; text: (zh: string, en: string) => string; profileId: string; profileVersion: number; family: string; disabled: boolean; onChange: (value: RetrospectiveOutput) => void };
const ROOT = "/api/agent-extensions";
export const probeIsFresh = (value: string | undefined) => {
  if (!value) return false;
  // Database timestamps without an offset use UTC.
  return Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value.replace(" ", "T") + "Z") > Date.now();
};

export default function RetrospectiveOutputContract({ request, text, profileId, profileVersion, family, disabled, onChange }: Props) {
  const [mode, setMode] = useState<RetrospectiveOutput["mode"]>("TEXT_JSON");
  const [directory, setDirectory] = useState<Row | null>(null);
  const [probeId, setProbeId] = useState("");
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const operation = useRef(false);
  const notify = useRef(onChange); notify.current = onChange;
  const scope = `${profileId}:${profileVersion}:${family}`;
  const currentScope = useRef(scope); currentScope.current = scope;
  const matching = directory?.profile_id === profileId && Number(directory.profile_version) === profileVersion && directory.target_family === family;
  const choices = matching ? (directory.items || []).filter((item: Row) => probeIsFresh(item.expires_at)) : [];
  const select = (nextMode: RetrospectiveOutput["mode"], selected = "", value = directory) => {
    setMode(nextMode); setProbeId(selected); setConsent(false);
    const probe = (value?.items || []).find((item: Row) => item.probe_id === selected);
    notify.current({ mode: nextMode, ...(selected && probe ? { probeId: selected, profileId, profileVersion, family, expiresAt: probe.expires_at } : {}) });
  };
  const load = async () => request(`${ROOT}/retrospective-output-contracts/${encodeURIComponent(profileId)}?target_family=${encodeURIComponent(family)}`);
  useEffect(() => {
    let active = true;
    setDirectory(null); setProbeId(""); setConsent(false); setError(""); setNotice("");
    notify.current({ mode });
    if (!profileId || !profileVersion) return () => { active = false; };
    void load().then(value => { if (active) setDirectory(value); }).catch(e => { if (active) setError(e instanceof Error ? e.message : text("输出契约目录不可用", "Output contract directory unavailable")); });
    return () => { active = false; };
  }, [scope]);
  const probe = async () => {
    if (operation.current || disabled || !consent || !matching) return;
    const startedScope = scope;
    operation.current = true; setBusy(true); setError(""); setNotice(""); setConsent(false);
    try {
      const value = await request(`${ROOT}/model-output-contracts/${encodeURIComponent(profileId)}/probes`, { method: "POST", body: JSON.stringify({ output_schema: directory.output_schema, example: directory.example }) });
      if (currentScope.current !== startedScope) return;
      setNotice(value.status === "VERIFIED" ? text("精确 Schema 探测已验证；请从目录选择证据。", "Exact schema probe verified; select its evidence from the directory.") : text(`探测状态：${value.status}。不会自动重试。`, `Probe status: ${value.status}. No automatic retry.`));
      const refreshed = await load();
      if (currentScope.current === startedScope) { setDirectory(refreshed); select(mode, "", refreshed); }
    } catch (e) {
      if (currentScope.current === startedScope) setError(e instanceof Error ? e.message : text("精确契约探测失败；不会自动重试。", "Exact contract probe failed; no automatic retry."));
    } finally { operation.current = false; setBusy(false); }
  };
  return <fieldset className="operation-explainer-form retrospective-output-contract" disabled={disabled || busy}>
    <legend>{text("回顾输出契约", "Retrospective output contract")}</legend>
    <label className="workbench-field"><span>{text("输出方式", "Output mode")}</span><select aria-label={text("输出方式", "Output mode")} name="output_mode" value={mode} onChange={e => select(e.target.value as RetrospectiveOutput["mode"])}><option value="TEXT_JSON">{text("TEXT_JSON · 文本 JSON，应用校验", "TEXT_JSON · Text JSON, application validation")}</option><option value="NATIVE_STRICT">{text("NATIVE_STRICT · 模型原生严格 Schema", "NATIVE_STRICT · Provider-native strict schema")}</option></select></label>
    <p>{mode === "TEXT_JSON" ? text("模型返回文本 JSON，由应用校验；此方式不声明原生严格输出能力。", "The application validates text JSON. This mode makes no native strict-output claim.") : text("仅接受当前模型修订、Schema 和参数完全一致且未过期的探测证据；创建和发送时会再次校验。", "Requires fresh probe evidence for the exact current profile revision, schema, and parameters; rechecked on creation and dispatch.")}</p>
    {mode === "NATIVE_STRICT" && <>
      <label className="workbench-field"><span>{text("精确探测证据", "Exact probe evidence")}</span><select aria-label={text("精确探测证据", "Exact probe evidence")} name="output_probe_id" required value={probeId} onChange={e => select(mode, e.target.value)}><option value="">{text("选择当前有效证据", "Select current verified evidence")}</option>{choices.map((item: Row) => <option key={item.probe_id} value={item.probe_id}>{item.probe_id} · {text("有效至", "Expires")} {item.expires_at}</option>)}</select></label>
      {!choices.length && <p>{text("没有匹配的有效证据。可显式发起一次仅含合成示例的探测。", "No matching fresh evidence. You may explicitly run one probe using a synthetic example.")}</p>}
      {matching && <><details><summary>{text("查看只读 Schema 与合成示例", "Inspect read-only schema and synthetic example")}</summary><p>{text("Schema 摘要", "Schema digest")}: <code>{directory.schema_digest}</code></p><p>{text("参数摘要", "Parameter digest")}: <code>{directory.parameter_digest}</code></p><pre>{JSON.stringify({ schema: directory.output_schema, example: directory.example }, null, 2)}</pre></details>
        <label className="continuity-source-check"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /><span>{text("我确认向所选模型发送一次合成示例探测请求。", "I confirm one synthetic-example probe request to the selected model.")}</span></label><button type="button" className="secondary-button" disabled={!consent || busy || disabled} onClick={() => void probe()}>{text("探测精确输出契约一次", "Probe exact output contract once")}</button></>}
    </>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </fieldset>;
}
