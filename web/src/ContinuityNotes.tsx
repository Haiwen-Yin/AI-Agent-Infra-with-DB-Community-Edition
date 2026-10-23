import React, { FormEvent, useEffect, useRef, useState } from "react";
import { statusLabel } from "./statusLabels";

type Row = Record<string, any>;
type SourceRef = { family: string; entity_id: string; revision_id: string; content_digest: string };
type Props = {
  request: (path: string, options?: RequestInit) => Promise<Row>;
  text: (zh: string, en: string) => string;
  work: Row;
  canWrite: boolean;
  sources: SourceRef[];
};
const newId = () => crypto.randomUUID();
const sourceKey = (source: SourceRef) => JSON.stringify(source);

export default function ContinuityNotes({ request, text, work, canWrite, sources }: Props) {
  const [items, setItems] = useState<Row[]>([]);
  const [nextAfter, setNextAfter] = useState("");
  const [note, setNote] = useState<Row | null>(null);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const lock = useRef(false);
  const scope = useRef(0);
  const pending = useRef(new Map<string, Row>());
  const run = async (action: (operation: number) => Promise<void>) => {
    if (lock.current) return;
    const operation = scope.current;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(operation); } catch (e) { if (operation === scope.current) setError(e instanceof Error ? e.message : text("操作失败", "Operation failed")); }
    finally { if (operation === scope.current) { lock.current = false; setBusy(false); } }
  };
  const post = async (path: string, body: Row) => {
    const signature = path + JSON.stringify(body);
    const payload = pending.current.get(signature) || { ...body, idempotency_key: newId() };
    pending.current.set(signature, payload);
    const value = await request(path, { method: "POST", body: JSON.stringify(payload) });
    pending.current.delete(signature); return value;
  };
  const load = async (after = "", operation = scope.current) => {
    if (operation !== scope.current) return;
    const value = await request(`/api/agent-extensions/works/${encodeURIComponent(work.work_contract_id)}/notes?limit=100${after ? `&after=${encodeURIComponent(after)}` : ""}`);
    if (operation !== scope.current) return;
    const pageItems: Row[] = value.items || [];
    setItems(previous => [...new Map((after ? [...previous, ...pageItems] : pageItems).map(item => [item.note_id, item])).values()]);
    setNextAfter(value.next_after || "");
  };
  useEffect(() => {
    scope.current++; lock.current = false;
    setNote(null); setItems([]); setNextAfter(""); setSelectedSources([]);
    void run(operation => load("", operation));
    return () => { scope.current++; };
  }, [work.work_contract_id]);
  const read = async (id: string, operation = scope.current) => {
    if (operation !== scope.current) return;
    const value = await request(`/api/agent-extensions/work-notes/${encodeURIComponent(id)}`);
    if (operation !== scope.current) return;
    setNote(value); setSelectedSources((value.content?.sources || []).map(sourceKey));
  };
  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    const refs = sources.filter(item => selectedSources.includes(sourceKey(item)));
    void run(async operation => {
      const content = { note_type: String(data.get("note_type")), title: String(data.get("title")), body: String(data.get("body")), sources: refs, expires_at: null };
      const path = note ? `/api/agent-extensions/work-notes/${encodeURIComponent(note.note_id)}/revisions` : `/api/agent-extensions/works/${encodeURIComponent(work.work_contract_id)}/notes`;
      const body = note ? { expected_version: note.version, content, reason: String(data.get("reason")) } : {
        expected_work_version: work.version, content, reason: String(data.get("reason")),
      };
      const result = await post(path, body);
      if (operation !== scope.current) return;
      await load("", operation); await read(result.note_id || note!.note_id, operation);
      if (operation === scope.current) setNotice(text("工作便签已保存。", "Working note saved."));
    });
  };
  const retire = () => {
    if (!note) return;
    void run(async operation => {
      await post(`/api/agent-extensions/work-notes/${encodeURIComponent(note.note_id)}/state`, { expected_version: note.version, status: "RETIRED", reason: text("工作便签不再适用", "Working note is no longer applicable") });
      if (operation !== scope.current) return;
      await load("", operation); await read(note.note_id, operation);
      if (operation === scope.current) setNotice(text("便签已归档，历史修订仍保留。", "Note retired; its revision history is retained."));
    });
  };
  const kind = (value: string) => ({ FINDING: text("发现", "Finding"), REJECTED_APPROACH: text("已排除方案", "Rejected approach"), VALIDATION: text("验证结果", "Validation"), OPEN_QUESTION: text("待确认问题", "Open question"), NEXT_ACTION: text("后续行动", "Next action") }[value] || value);
  const reason = <label className="workbench-field"><span>{text("操作原因", "Reason")}</span><input name="reason" required maxLength={1000} /></label>;
  return <section className="panel continuity-notes" aria-label={text("工作便签", "Working notes")}>
    <div className="page-toolbar"><h3>{text("工作便签", "Working notes")}</h3><div><button type="button" className="small-button" disabled={busy} onClick={() => void run(operation => load("", operation))}>{text("刷新", "Refresh")}</button><button type="button" className="small-button" disabled={busy} onClick={() => { setNote(null); setSelectedSources([]); }}>{text("新建便签", "New note")}</button></div></div>
    <p>{text("便签是当前工作契约的临时交接证据，不会自动成为长期记忆、知识或 Skill；来源权限在保存和使用时重新检查。", "Notes are temporary handoff evidence attached to this Work contract. They do not become Memory, Knowledge or Skills automatically; source authority is rechecked on save and use.")}</p>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="continuity-notes-layout"><div><h4>{text("便签记录", "Note records")}</h4>{items.length ? <ul className="continuity-record-list">{items.map(item => <li key={item.note_id}><button type="button" className="text-action" disabled={busy} onClick={() => void run(operation => read(item.note_id, operation))}>{item.note_id} · v{item.version}</button><span>{statusLabel(item.status, text)}</span></li>)}</ul> : <p>{busy ? text("便签加载中…", "Loading notes…") : text("当前工作没有便签。", "No notes are attached to this Work contract.")}</p>}{nextAfter && <button type="button" className="small-button" disabled={busy} onClick={() => void run(operation => load(nextAfter, operation))}>{text("加载更多便签", "Load more notes")}</button>}</div>
      <form key={note ? `${note.note_id}-${note.version}` : `new-${work.work_contract_id}`} onSubmit={save}><fieldset className="operation-explainer-form" disabled={busy || !canWrite || !!note && note.status !== "ACTIVE"}><legend>{note ? text("修订便签", "Revise note") : text("创建便签", "Create note")}</legend>
        <label className="workbench-field"><span>{text("便签类型", "Note type")}</span><select name="note_type" defaultValue={note?.content?.note_type || "FINDING"}>{[["FINDING", "发现", "Finding"], ["REJECTED_APPROACH", "已排除方案", "Rejected approach"], ["VALIDATION", "验证结果", "Validation"], ["OPEN_QUESTION", "待确认问题", "Open question"], ["NEXT_ACTION", "后续行动", "Next action"]].map(([value, zh, en]) => <option key={value} value={value}>{text(zh, en)}</option>)}</select></label>
        <label className="workbench-field"><span>{text("标题", "Title")}</span><input name="title" required maxLength={4000} defaultValue={note?.content?.title || ""} /></label>
        <label className="workbench-field"><span>{text("内容", "Body")}</span><textarea name="body" required maxLength={4000} rows={4} defaultValue={note?.content?.body || ""} /></label>
        {sources.length > 0 && <fieldset className="operation-explainer-form"><legend>{text("关联精确来源（可选）", "Link exact sources (optional)")}</legend>{sources.map(source => <label className="continuity-source-check" key={sourceKey(source)}><input type="checkbox" checked={selectedSources.includes(sourceKey(source))} onChange={e => setSelectedSources(previous => e.target.checked ? [...previous, sourceKey(source)] : previous.filter(value => value !== sourceKey(source)))} /><span>{statusLabel(source.family, text)} · {source.entity_id} · {source.revision_id}</span></label>)}</fieldset>}
        {reason}<button className="primary-button">{text(note ? "保存新修订" : "创建便签", note ? "Save new revision" : "Create note")}</button>
      </fieldset></form></div>
    {note && <section className="continuity-note-preview"><h4>{kind(note.content?.note_type || "")} · {statusLabel(note.status, text)}</h4><p>{note.content?.title || text("来源权限已变化，当前正文不可读取。", "Source authority changed; this note body cannot be read.")}</p>{note.content?.body && <p className="continuity-body">{note.content.body}</p>}<p>{text("修订", "Revision")}: {note.revision_no} · {text("摘要", "Digest")}: {note.content_digest}</p>{note.status === "ACTIVE" && <button type="button" className="small-button" disabled={busy || !canWrite} onClick={retire}>{text("归档便签", "Retire note")}</button>}</section>}
  </section>;
}
