import React, { useEffect, useRef, useState } from "react";

type Row = Record<string, any>;
type Props = { request: (path: string, options?: RequestInit) => Promise<Row>; text: (zh: string, en: string) => string };

export default function PlatformLearning({ request, text }: Props) {
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState("HUMAN");
  const [goal, setGoal] = useState("onboarding");
  const [items, setItems] = useState<Row[]>([]);
  const [content, setContent] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [delivery, setDelivery] = useState("");
  const [canImport, setCanImport] = useState(false);
  const [bundle, setBundle] = useState("");
  const [refresh, setRefresh] = useState(0);
  const sequence = useRef(0);
  useEffect(() => {
    const current = ++sequence.current;
    setContent(null); setItems([]); setError(""); setCanImport(false); setDelivery("");
    if (!open) { setBusy(false); return; }
    setBusy(true);
    void request(`/api/learning?role=${role}&goal=${goal}`).then(value => {
      if (current === sequence.current) {
        setItems(value.items || []); setDelivery(value.delivery || ""); setCanImport(value.can_import === true);
      }
    }).catch(reason => { if (current === sequence.current) setError(reason instanceof Error ? reason.message : text("指南加载失败", "Guidance unavailable")); })
      .finally(() => { if (current === sequence.current) setBusy(false); });
    return () => { sequence.current++; };
  }, [open, role, goal, refresh]);
  const importGuidance = async () => {
    const current = ++sequence.current;
    setContent(null); setBusy(true); setError("");
    try {
      await request('/api/platform/learning/import', { method: 'POST', body: JSON.stringify({ bundle_json: bundle }) });
      if (current === sequence.current) { setBundle(""); setRefresh(value => value + 1); }
    } catch (reason) {
      if (current === sequence.current) setError(reason instanceof Error ? reason.message : text("指南导入失败", "Guidance import failed"));
    } finally { if (current === sequence.current) setBusy(false); }
  };
  const read = async (item: Row) => {
    const current = ++sequence.current;
    setContent(null); setBusy(true); setError("");
    try {
      const value = await request(`/api/learning/${encodeURIComponent(item.entity_id)}?expected_digest=${item.content_digest}`);
      if (current === sequence.current) setContent(value);
    } catch (reason) {
      if (current === sequence.current) setError(reason instanceof Error ? reason.message : text("此版本或来源已不可用，请刷新目录。", "This revision or source is unavailable; refresh the directory."));
    } finally { if (current === sequence.current) setBusy(false); }
  };
  return <section className="panel platform-learning" aria-label={text("平台学习指南", "Platform learning")}>
    <button className="text-button" type="button" aria-expanded={open} onClick={() => setOpen(value => !value)}>{text("平台学习指南", "Platform learning")}</button>
    {open && <>
      <p>{text("按角色和目标选择已发布指南，再读取所需章节。操作仍需当前权限；阅读不会创建资源或执行任务。", "Choose published guidance by role and goal, then load the chapter you need. Operations still require current grants; reading creates no resources and runs no tasks.")}</p>
      <div className="page-toolbar">
        <label className="workbench-field"><span>{text("学习角色", "Learning role")}</span><select value={role} onChange={event => setRole(event.target.value)}>{[["HUMAN", "使用者", "User"], ["ADMIN", "管理员", "Administrator"], ["AGENT", "Agent", "Agent"]].map(([value, zh, en]) => <option key={value} value={value}>{text(zh, en)}</option>)}</select></label>
        <label className="workbench-field"><span>{text("学习目标", "Learning goal")}</span><select value={goal} onChange={event => setGoal(event.target.value)}>{[["onboarding", "首次使用", "First use"], ["access", "身份与权限", "Identity and access"], ["collaboration", "人机协作", "Collaboration"], ["tasks", "任务与流程", "Tasks and workflows"], ["knowledge", "知识与回答", "Knowledge and answers"], ["memory", "记忆", "Memory"], ["capabilities", "Agent 能力", "Agent capabilities"], ["integration", "集成", "Integration"], ["handoff", "交接与 DB4A2A", "Handoff and DB4A2A"], ["recovery", "排错与恢复", "Diagnosis and recovery"]].map(([value, zh, en]) => <option key={value} value={value}>{text(zh, en)}</option>)}</select></label>
      </div>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">{text("正在读取当前授权资料…", "Reading currently authorized guidance…")}</p>}
      {delivery === 'separate' && <p>{text("此版本的完整平台学习知识单独提供，软件安装不自动导入。知识库与学习入口可正常使用；管理员可按需导入匹配的知识文件。", "Complete platform learning content is supplied separately and is not imported during software installation. Knowledge and learning entrypoints remain available; an administrator can import a matching knowledge file when needed.")}</p>}
      {!busy && !error && items.length === 0 && <p>{text("当前筛选下没有适用的已发布指南。请调整筛选，或由有权管理员检查是否已导入适用资料。", "No applicable published guidance matches these filters. Change the filters or ask an authorized administrator to check whether applicable guidance has been imported.")}</p>}
      {canImport && <div className="page-toolbar">
        <label className="workbench-field"><span>{text("选择独立平台知识文件", "Select a separate platform knowledge file")}</span><input type="file" accept=".json,application/json" disabled={busy} onChange={async event => {
          const file = event.target.files?.[0]; setBundle(""); setError("");
          if (!file) return;
          if (file.size > 4 * 1024 * 1024) { setError(text("文件不能超过 4 MiB", "File must not exceed 4 MiB")); return; }
          try { setBundle(await file.text()); } catch { setError(text("无法读取文件", "Cannot read file")); }
        }} /></label>
        <p>{text("导入会将匹配当前产品、版本和数据库的指南发布为公共平台知识。", "Import publishes guidance matching the current product, version and database as public platform knowledge.")}</p>
        <button type="button" disabled={busy || !bundle} onClick={() => void importGuidance()}>{text("导入并发布指南", "Import and publish guidance")}</button>
      </div>}
      <ul>{items.map(item => <li key={item.entity_id}><button className="text-button" type="button" disabled={busy} onClick={() => void read(item)}>{item.title}</button><span> · {item.product_key} · {item.database} · v{item.version}</span></li>)}</ul>
      {content && <article aria-label={text("已授权的指南正文", "Authorized guide content")}><h4>{content.title}</h4><pre className="continuity-body">{content.content}</pre><p>{text("精确内容摘要", "Exact content digest")}: {content.content_digest}</p></article>}
    </>}
  </section>;
}
