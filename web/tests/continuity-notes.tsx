import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import ContinuityNotes from "../src/ContinuityNotes";
import "../src/app.css";

// Synthetic component-only API. No server, credentials, database or model calls.
type Harness = {
  calls: string[];
  nextPageFailures: number;
  delayed: boolean;
  replies: (() => void)[];
  rejections: ((error: Error) => void)[];
  language: "zh" | "en";
};
declare global { interface Window { notesHarness: Harness } }
const state: Harness = window.notesHarness = { calls: [], nextPageFailures: 0, delayed: false, replies: [], rejections: [], language: "en" };
const rows = (start: number, end: number, prefix: string) => Array.from({ length: end - start + 1 }, (_, i) => ({
  note_id: `${prefix}-note-${String(i + start).padStart(3, "0")}`, status: "ACTIVE", version: 1,
}));
const request = async (path: string) => {
  state.calls.push(path);
  const url = new URL(path, window.location.origin);
  const prefix = url.pathname.includes("/work-b/") ? "b" : "a";
  const after = url.searchParams.get("after");
  if (after && state.nextPageFailures > 0) { state.nextPageFailures--; throw new Error("Synthetic continuation unavailable"); }
  const result = after ? { items: rows(100, 105, prefix), next_after: null } : { items: rows(1, 100, prefix), next_after: `${prefix}-note-100` };
  if (state.delayed) await new Promise<void>((resolve, reject) => { state.replies.push(resolve); state.rejections.push(reject); });
  return result;
};
function Harness() {
  const [work, setWork] = useState("work-a");
  return <main style={{ maxWidth: 1200, margin: "20px auto", padding: 12 }}>
    <button type="button" onClick={() => setWork(previous => previous === "work-a" ? "work-b" : "work-a")}>Switch work</button>
    <output aria-label="Current work">{work}</output>
    <ContinuityNotes request={request} text={(zh, en) => state.language === "zh" ? zh : en}
      work={{ work_contract_id: work, version: 1 }} canWrite={false} sources={[]} />
  </main>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
