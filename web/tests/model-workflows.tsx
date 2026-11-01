import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import ContinuityQuality from "../src/ContinuityQuality";
import "../src/app.css";

type Row = Record<string, any>;
type HarnessState = { calls: { path: string; method: string; body: Row }[]; hold: boolean; pending: { path: string; resolve: () => void }[]; probeStatus: string; runStatus: string; language: string };
declare global { interface Window { modelWorkflowHarness: HarnessState } }
const params = new URLSearchParams(location.search);
const scenario = params.get("scenario") || "default";
const state = window.modelWorkflowHarness = { calls: [], hold: false, pending: [], probeStatus: "VERIFIED", runStatus: "UNOBSERVED", language: params.get("lang") || "en" } as HarnessState;
const source = { family: "KNOWLEDGE", entity_id: "source-a", revision_id: "revision-a", content_digest: "a".repeat(64) };
const schemas = { type: "object", properties: { family: { type: "string" } }, required: ["family"], additionalProperties: false };
let frozen: Row = {};
let run = false;
const request = async (path: string, options?: RequestInit): Promise<Row> => {
  const method = options?.method || "GET";
  const body = options?.body ? JSON.parse(String(options.body)) : {};
  state.calls.push({ path, method, body });
  const url = new URL(path, location.origin);
  const finish = async (value: Row) => { if (state.hold) await new Promise<void>(resolve => state.pending.push({ path, resolve })); return value; };
  if (path.startsWith("/api/llm-provider-profiles?")) return { items: ["profile-a", "profile-b"].map(profile_id => ({ profile_id, version: 3, model_id: "synthetic-model", status: "ACTIVE", health_state: "HEALTHY" })) };
  if (path.startsWith("/api/native-agents?")) return { items: [] };
  if (path === "/api/platform/portal-knowledge-policy") return { version: 4 };
  if (path.includes("/answer-evaluation/cases")) return { items: [] };
  if (path.includes("/retrospective-output-contracts/")) {
    const profile_id = url.pathname.split("/").pop();
    const family = url.searchParams.get("target_family");
    return finish({ profile_id, profile_version: 3, target_family: family, output_schema: schemas, example: { family }, schema_digest: "b".repeat(64), parameter_digest: "c".repeat(64), items: [
      { probe_id: `${profile_id}-${family}-fresh`, expires_at: "2099-01-01T00:00:00" },
      { probe_id: `${profile_id}-${family}-expired`, expires_at: "2000-01-01T00:00:00" },
    ] });
  }
  if (path.includes("/model-output-contracts/") && method === "POST") return { status: state.probeStatus };
  if (url.pathname.endsWith("/retrospectives") && method === "POST") { frozen = body; return { job_id: "job-a", status: "PENDING", ...body, schema_digest: "b".repeat(64), parameter_digest: "c".repeat(64) }; }
  if (path.endsWith("/retrospectives/job-a/run")) { run = true; return { job_id: "job-a", status: state.runStatus, ...frozen }; }
  if (path.endsWith("/retrospectives/job-a")) return { job_id: "job-a", status: run ? state.runStatus : "PENDING", ...frozen };
  if (path.includes("/model-read-tools?") || path.endsWith("/model-read-tools/registration-a/contract")) {
    if (scenario === "partial") throw new Error("Synthetic registration directory denied");
    const value = { registration_id: "registration-a", tool_id: "tool-a", source, action_id: "registration-card", schema_digest: "d".repeat(64), input_schema: schemas };
    return finish(path.includes("?") ? { items: [value], next_after: url.searchParams.has("after") ? null : "registration-a" } : value);
  }
  if (path.includes("/model-tool-turns?") || path.endsWith("/model-tool-turns/turn-a")) {
    const domain = url.searchParams.get("security_domain_id") || "domain-a";
    const value = { turn_id: "turn-a", status: "UNOBSERVED", task_id: `${domain}-task`, step_id: "step-a", principal_id: "agent-a", profile_id: "profile-a", profile_version: 3, probe_id: "tool-probe", tool_call: { action_id: "tool-card", job_id: "worker-job" }, stages: [{ phase: "PROPOSAL", attempt_id: "attempt-a" }, { phase: "FINAL" }], observer_only: true };
    return finish(path.includes("?") ? { items: [value], next_after: null } : value);
  }
  throw new Error(`Unexpected synthetic request: ${method} ${path}`);
};
function Harness() {
  const [domain, setDomain] = useState("domain-a");
  return <main className="continuity-workbench" style={{ maxWidth: 1200, margin: "20px auto", padding: 12 }}><button type="button" onClick={() => setDomain(value => value === "domain-a" ? "domain-b" : "domain-a")}>Switch domain</button>
    <ContinuityQuality key={domain} request={request} text={(zh, en) => state.language === "zh" ? zh : en} domain={domain} principalId="human-a" work={{ execution_links: [{ link_kind: "TASK", entity_id: "task-a" }] }} sources={[source]} canWrite={scenario !== "readonly"} canManage={scenario !== "unprivileged"} modelRuntimeEnabled={scenario !== "legacy"} />
  </main>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
