import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import ProcessingRecovery from "../src/ProcessingRecovery";
import "../src/app.css";
type Row = Record<string, any>;
const state = { calls: [] as Row[], failNext: false, denied: false, accepted: false, dispatched: false };
declare global { interface Window { processingHarness: typeof state } }
window.processingHarness = state;
const target = { continuity_id: "chain-a", attempt_id: "attempt-a", target_kind: "RUNTIME", target_id: "execution-a", target_revision: "revision-a", input_digest: "a".repeat(64), business_key: "original-key" };
const receipt = () => ({ recovery_id: "recovery-a", status: state.dispatched ? "DISPATCHED" : "ACCEPTED", successor_continuity_id: "successor-a", original_attempt_id: "attempt-a" });
const request = async (path: string, options?: RequestInit): Promise<Row> => {
  const method = options?.method || "GET", body = options?.body ? JSON.parse(String(options.body)) : null;
  state.calls.push({ path, method, body });
  if (state.denied) throw new Error("Synthetic current authority denied");
  if (method === "POST") {
    if (state.failNext) { state.failNext = false; throw new Error("Synthetic response lost; retry original receipt"); }
    if (path.endsWith("/retries")) { state.accepted = true; return receipt(); }
    if (path.endsWith("/dispatch")) { state.dispatched = true; return receipt(); }
    if (path.endsWith("/reconcile")) return { status: body.mode === "READ_ORIGINAL" ? "UNOBSERVED" : body.outcome, generation_requested: false };
    throw new Error("Unexpected synthetic mutation");
  }
  return { continuity_id: "chain-a", canonical_task_id: "task-a", lifecycle_status: "FAILED", consumed: { requests: 32, steps: 40, tokens: 1200 }, limits: { requests: 32, steps: 128, tokens: 262144 },
    next_cursor: path.includes("&after=") ? null : "block-b", recoveries: state.accepted ? [receipt()] : [],
    observations: path.includes("&after=") ? [] : [
      { block_id: "block-a", version: 3, category: "BLOCKED", reason_code: "BUDGET_REQUESTS", status: state.accepted ? "RECOVERY_ACCEPTED" : "OPEN", target_id: target.target_id, target_revision: target.target_revision, target },
      { block_id: "block-b", version: 7, category: "UNKNOWN", reason_code: "POSSIBLE_SEND", status: "OPEN", target_id: "execution-b", target_revision: "revision-b", target: { ...target, target_id: "execution-b", attempt_id: "attempt-b" } },
    ] };
};
function Harness() {
  const [language, setLanguage] = useState("en"), [canRecover, setCanRecover] = useState(true);
  return <main className="continuity-workbench" style={{ maxWidth: 1000, padding: 12, margin: "20px auto" }}>
    <button onClick={() => setLanguage(value => value === "en" ? "zh" : "en")}>Switch language</button>
    <button onClick={() => setCanRecover(value => !value)}>Toggle read only</button>
    <ProcessingRecovery request={request} text={(zh, en) => language === "zh" ? zh : en} canRecover={canRecover} />
  </main>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
