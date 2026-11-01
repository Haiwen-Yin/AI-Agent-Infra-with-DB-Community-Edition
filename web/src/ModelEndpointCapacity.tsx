import React, { useEffect, useRef, useState } from "react";
import PrincipalPicker from "./PrincipalPicker";
import "./ModelEndpointCapacity.css";

type Row = Record<string, any>;
type Props = { request: (path: string, options?: RequestInit) => Promise<Row>; text: (zh: string, en: string) => string; profiles: Row[] };
const root = "/api/model-endpoint-capacity";

export default function ModelEndpointCapacity({ request, text, profiles }: Props) {
  const [groups, setGroups] = useState<Row[]>([]), [after, setAfter] = useState("");
  const [selected, setSelected] = useState(""), [group, setGroup] = useState<Row | null>(null);
  const [requests, setRequests] = useState<Row[]>([]), [next, setNext] = useState<number | null>(null);
  const [resolution, setResolution] = useState<Row | null>(null);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false);
  const lock = useRef(false), generation = useRef(0), pending = useRef(new Map<string, Row>());
  const state = (value: string) => ({ ACTIVE: text("启用", "Active"), DRAINING: text("停止接收新请求", "Draining"), REVOKED: text("已撤销", "Revoked"),
    QUEUED: text("排队中", "Queued"), RESERVED: text("等待发送", "Reserved"), DISPATCHING: text("请求进行中", "Request ongoing"), UNKNOWN: text("结果未知，仍占用容量", "Outcome unknown; capacity held"),
    COMPLETED: text("请求已结束", "Request completed"), REJECTED: text("发送前拒绝", "Rejected before send"), CANCELLED: text("排队已取消", "Queue cancelled"), EXPIRED: text("发送前过期", "Expired before send") }[value] || value);
  const run = async (operation: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try { await operation(); } catch (e) { setError(e instanceof Error ? e.message : text("操作失败，请刷新状态后核对", "Operation failed; refresh and check state")); }
    finally { lock.current = false; setBusy(false); }
  };
  const loadGroups = async (cursor = "") => {
    const result = await request(`${root}/groups?limit=20${cursor ? `&after=${encodeURIComponent(cursor)}` : ""}`);
    setGroups(old => cursor ? [...old, ...result.groups] : result.groups); setAfter(result.next_after || "");
  };
  const loadGroup = async (id: string) => {
    const current = ++generation.current;
    setGroup(null); setRequests([]); setNext(null); setResolution(null);
    if (!id) return;
    const value = await request(`${root}/groups/${encodeURIComponent(id)}`);
    if (current === generation.current) setGroup(value);
  };
  const loadRequests = async (cursor = 0) => {
    const id = selected, current = generation.current;
    const value = await request(`${root}/groups/${encodeURIComponent(id)}/admissions?after_sequence=${cursor}&limit=20`);
    if (current !== generation.current) return;
    setRequests(old => cursor ? [...old, ...value.items] : value.items); setNext(value.next_sequence ?? null);
  };
  const post = async (path: string, body: Row) => {
    const signature = path + JSON.stringify(body);
    const payload = pending.current.get(signature) || { ...body, idempotency_key: crypto.randomUUID() };
    pending.current.set(signature, payload);
    const result = await request(path, { method: "POST", body: JSON.stringify(payload) });
    pending.current.delete(signature); return result;
  };
  useEffect(() => { void run(() => loadGroups()); return () => { generation.current++; }; }, []);
  const reason = <label className="workbench-field"><span>{text("操作原因", "Reason")}</span><input name="reason" minLength={3} maxLength={1000} required /></label>;
  const key = (label: string, name: string) => <label className="workbench-field"><span>{label}</span><input name={name} pattern="[A-Za-z0-9][A-Za-z0-9_.:-]*" maxLength={128} required /></label>;
  return <section className="panel model-capacity" aria-label={text("共享模型容量", "Shared model capacity")}>
    <h3>{text("共享模型容量", "Shared model capacity")}</h3>
    <p>{text("将同一模型资源的配置和地址纳入同一队列。多个安装需通过同一协调网关接入；各自的数据库锁不能形成全局串行。刷新只读取状态。", "Put profiles and addresses for one model resource in the same queue. Multiple installations must use the same coordinating gateway; independent database locks cannot provide global serialization. Refresh only reads state.")}</p>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <label className="workbench-field"><span>{text("模型资源", "Model resource")}</span><select aria-label={text("模型资源", "Model resource")} value={selected} disabled={busy} onChange={e => { const id = e.target.value; setSelected(id); void run(() => loadGroup(id)); }}><option value="">{text("选择资源", "Select resource")}</option>{groups.map(item => <option key={item.group_id} value={item.group_id}>{item.resource_key} · {state(item.status)}</option>)}</select></label>
    <div className="actions-row"><button type="button" className="small-button" disabled={busy} onClick={() => void run(async () => { await loadGroups(); if (selected) await loadGroup(selected); })}>{text("刷新", "Refresh")}</button>{after && <button type="button" className="small-button" disabled={busy} onClick={() => void run(() => loadGroups(after))}>{text("更多资源", "More resources")}</button>}</div>
    <details><summary>{text("登记模型资源", "Register model resource")}</summary><form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); void run(async () => {
      const value = await post(root + "/groups", { resource_key: data.get("resource_key"), coordinator_id: data.get("coordinator_id"), reason: data.get("reason"), policy: { capacity: 1 } });
      await loadGroups(); setSelected(value.group_id); await loadGroup(value.group_id); setNotice(text("资源已登记，默认一次运行一个请求。请登记参与者和配置地址。", "Resource registered with capacity one. Register participants and profile addresses."));
    }); }}><fieldset className="operation-explainer-form" disabled={busy}><legend>{text("新资源", "New resource")}</legend>{key(text("资源名称", "Resource key"), "resource_key")}{key(text("协调服务名称", "Coordinator key"), "coordinator_id")}{reason}<button className="primary-button">{text("登记", "Register")}</button></fieldset></form></details>
    {group && <>
      <p>{text("当前占用", "Current occupancy")}: {(group.occupancy || []).map((item: Row) => `${state(item.status)} ${item.request_count}`).join(" · ") || text("无进行中或排队请求", "No ongoing or queued requests")}</p>
      <p>{text("容量", "Capacity")}: {group.policy.capacity} · {state(group.status)} · {text("策略版本", "Policy revision")}: {group.policy_revision}</p>
      <details><summary>{text("修改容量与超时", "Change capacity and deadlines")}</summary><form key={`${selected}-${group.version}`} onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); void run(async () => {
        const policy: Row = { capacity: Number(data.get("capacity")) };
        for (const name of ["queue_ms", "socket_ms", "idle_ms", "overall_ms", "reservation_ms"]) policy[name] = Math.round(Number(data.get(name)) * 1000);
        await post(`${root}/groups/${encodeURIComponent(selected)}/revisions`, { expected_version: group.version, policy, status: data.get("status"), reason: data.get("reason") });
        await loadGroup(selected); setNotice(text("策略已保存", "Policy saved"));
      }); }}><fieldset className="operation-explainer-form" disabled={busy}><legend>{text("新策略", "New policy")}</legend>
        <label className="workbench-field"><span>{text("同时请求数", "Concurrent requests")}</span><input type="number" name="capacity" min={1} max={16} step={1} defaultValue={group.policy.capacity} required /></label>
        {([ ["queue_ms", "排队超时（秒）", "Queue deadline (seconds)", 0, 3600], ["socket_ms", "连接与读取超时（秒）", "Socket deadline (seconds)", 1, 600], ["idle_ms", "流空闲超时（秒）", "Stream idle deadline (seconds)", 1, 600], ["overall_ms", "请求总时限（秒）", "Overall deadline (seconds)", 1, 7200], ["reservation_ms", "未发送预留时限（秒）", "Unused reservation (seconds)", 1, 120] ] as const).map(([name, zh, en, min, max]) => <label className="workbench-field" key={name}><span>{text(zh, en)}</span><input name={name} type="number" min={min} max={max} step={0.001} defaultValue={group.policy[name] / 1000} required /></label>)}
        <label className="workbench-field"><span>{text("接收新请求", "Accept new requests")}</span><select name="status" defaultValue={group.status}><option value="ACTIVE">{text("启用", "Active")}</option><option value="DRAINING">{text("停止接收", "Drain")}</option></select></label>{reason}<button className="primary-button">{text("保存策略", "Save policy")}</button>
      </fieldset></form></details>
      <h4>{text("参与者", "Participants")}</h4>
      <ul>{group.origins.map((item: Row) => <li key={item.origin_id}>{item.installation_key} · {item.principal_id} · {state(item.status)}<details><summary>{text("变更参与状态", "Change participant status")}</summary><form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); void run(async () => {
        await post(`${root}/groups/${encodeURIComponent(selected)}/origins/${encodeURIComponent(item.origin_id)}/state`, { expected_version: Number(item.version), status: item.status === "ACTIVE" ? "REVOKED" : "ACTIVE", reason: data.get("reason") }); await loadGroup(selected);
      }); }}><fieldset className="operation-explainer-form" disabled={busy}>{reason}<button className="small-button">{item.status === "ACTIVE" ? text("撤销参与", "Revoke participation") : text("恢复参与", "Restore participation")}</button></fieldset></form></details></li>)}</ul>
      <details><summary>{text("登记参与者", "Register participant")}</summary><form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); void run(async () => {
        await post(`${root}/groups/${encodeURIComponent(selected)}/origins`, Object.fromEntries(data)); await loadGroup(selected);
      }); }}><fieldset className="operation-explainer-form" disabled={busy}><legend>{text("参与身份", "Participant identity")}</legend>{key(text("参与者名称", "Participant key"), "origin_id")}{key(text("安装名称", "Installation key"), "installation_key")}
        <label className="workbench-field"><span>{text("原始请求主体", "Original requesting principal")}</span><PrincipalPicker name="principal_id" required text={text} /></label>{reason}<button className="primary-button">{text("登记参与者", "Register participant")}</button>
      </fieldset></form></details>
      <h4>{text("受控服务地址", "Controlled provider addresses")}</h4><ul>{group.aliases.map((item: Row) => <li key={item.endpoint_url}>{item.endpoint_url}</li>)}</ul>
      <form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget), profile = profiles.find(item => item.profile_id === data.get("profile_id")); if (!profile) return; void run(async () => {
        await post(`${root}/groups/${encodeURIComponent(selected)}/aliases`, { expected_version: group.version, profile_id: profile.profile_id, endpoint_url: profile.provider_url, reason: data.get("reason") }); await loadGroup(selected);
      }); }}><fieldset className="operation-explainer-form" disabled={busy}><legend>{text("绑定已保存的模型配置", "Bind a saved model profile")}</legend><label className="workbench-field"><span>{text("模型配置", "Model profile")}</span><select name="profile_id" required><option value="">{text("选择配置", "Select profile")}</option>{profiles.filter(item => item.status === "ACTIVE").map(item => <option key={item.profile_id} value={item.profile_id}>{item.profile_key} · {item.model_id}</option>)}</select></label>{reason}<button className="primary-button">{text("绑定地址与配置", "Bind address and profile")}</button></fieldset></form>
      <h4>{text("请求记录", "Request records")}</h4><button type="button" className="small-button" disabled={busy} onClick={() => void run(() => loadRequests())}>{text("读取请求记录", "Read request records")}</button>
      <p>{text("关闭客户端连接不证明模型停止。未知请求会继续占用容量，需核实原请求已结束后再由管理员明确处理。", "Closing the client connection does not prove the model stopped. Unknown requests retain capacity until an administrator verifies the original request ended and records a resolution.")}</p>
      <ul>{requests.map(item => <li key={item.admission_id}><code>{item.admission_id}</code> · {state(item.status)}{item.status === "UNKNOWN" && <button type="button" className="small-button" disabled={busy} onClick={() => setResolution(item)}>{text("记录人工核实", "Record operator resolution")}</button>}</li>)}</ul>
      {next !== null && <button type="button" className="small-button" disabled={busy} onClick={() => void run(() => loadRequests(next))}>{text("更多请求", "More requests")}</button>}
      {resolution && <form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); if (!data.get("confirmed")) return; void run(async () => {
        const evidence = JSON.stringify({ admission_id: resolution.admission_id, attempt_id: resolution.attempt_id, version: resolution.version, reason: data.get("reason") });
        const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(evidence))), value => value.toString(16).padStart(2, "0")).join("");
        await post(`${root}/admissions/${encodeURIComponent(resolution.admission_id)}/reconcile`, { expected_version: resolution.version, attempt_id: resolution.attempt_id, fencing_token: resolution.fencing_token,
          evidence_kind: "OPERATOR_CONFIRMATION", evidence_digest: hash, finish_code: "OPERATOR_CONFIRMED_TERMINATED", reason: data.get("reason") }); setResolution(null); await loadRequests();
      }); }}><fieldset className="operation-explainer-form" disabled={busy}><legend>{text("人工确认原请求结束", "Operator confirmation of original request termination")}</legend><p><code>{resolution.admission_id}</code></p>{reason}<label><input type="checkbox" name="confirmed" required />{text("我已核实这个原始请求已结束。这是人工确认，不是服务端独立观测。", "I verified this original request ended. This is operator confirmation, not independent server observation.")}</label><button className="primary-button">{text("确认并记录", "Confirm and record")}</button><button type="button" className="small-button" onClick={() => setResolution(null)}>{text("返回", "Back")}</button></fieldset></form>}
    </>}
  </section>;
}
