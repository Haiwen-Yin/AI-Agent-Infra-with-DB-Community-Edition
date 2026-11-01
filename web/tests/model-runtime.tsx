import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import ModelEndpointCapacity from "../src/ModelEndpointCapacity";
import RuntimeObservations from "../src/RuntimeObservations";
import "../src/app.css";
type Row = Record<string, any>;
const state = { calls: [] as Row[], failNextMutation: false, policyVersion: 3, resolved: false };
declare global { interface Window { modelRuntimeHarness: typeof state } }
window.modelRuntimeHarness = state;
const request = async (path: string, options?: RequestInit): Promise<Row> => {
  const body = options?.body ? JSON.parse(String(options.body)) : null;
  state.calls.push({ path, method: options?.method || "GET", body });
  if (options?.method === "POST") {
    if (state.failNextMutation) { state.failNextMutation = false; throw new Error("Synthetic response unavailable; inspect original request"); }
    if (path.endsWith("/revisions") || path.endsWith("/aliases")) state.policyVersion++;
    if (path.endsWith("/reconcile")) state.resolved = true;
    return { group_id: "group-a", version: state.policyVersion };
  }
  if (path.includes("/admissions?")) return { items: [{ admission_id: "original-unknown-request", status: state.resolved ? "COMPLETED" : "UNKNOWN", version: 5, attempt_id: "original-attempt", fencing_token: 7 }], next_sequence: null };
  if (/\/groups\?/.test(path)) return { groups: [{ group_id: "group-a", resource_key: "Shared coder", status: "ACTIVE" }], next_after: null };
  return { group_id: "group-a", resource_key: "Shared coder", coordinator_id: "coordinator", version: state.policyVersion, policy_revision: 1, status: "ACTIVE",
    policy: { capacity: 1, queue_ms: 60000, socket_ms: 180000, idle_ms: 60000, overall_ms: 600000, reservation_ms: 30000 },
    origins: [], aliases: [{ endpoint_url: "http://provider.invalid/v1" }], occupancy: state.resolved ? [] : [{ status: "UNKNOWN", request_count: 1 }] };
};
function Harness() {
  const [language, setLanguage] = useState("en"), [readOnly, setReadOnly] = useState(false);
  const text = (zh: string, en: string) => language === "zh" ? zh : en;
  return <main className="page-stack" style={{ maxWidth: 1000, margin: "20px auto", padding: 12 }}>
    <button onClick={() => setLanguage(old => old === "en" ? "zh" : "en")}>Switch language</button>
    <button onClick={() => setReadOnly(old => !old)}>Toggle read only</button>
    {!readOnly && <ModelEndpointCapacity request={request} text={text} profiles={[{ profile_id: "profile", profile_key: "Coder", model_id: "model", provider_url: "http://provider.invalid/v1", status: "ACTIVE" }]} />}
    <RuntimeObservations text={text} items={[
      { admission_id: "observed-request", model_id: "model", profile_version: 4, request_complete: "Y", result_state: "COMPLETED", queue_ms: 0, first_content_ms: null, provider_ms: 125, total_ms: 125, prompt_tokens: 0, completion_tokens: null, total_tokens: null, cached_tokens: 0, cache_write_tokens: null, reasoning_tokens: null, usage_provenance: "PARTIAL" },
      { admission_id: "central-admission", origin_receipt_id: "original-local-receipt", model_id: "model", profile_version: 2, request_complete: "Y", result_state: "COMPLETED", queue_ms: 3, first_content_ms: 100, provider_ms: 240, total_ms: 243, prompt_tokens: 20, completion_tokens: 10, total_tokens: 30, cached_tokens: 5, cache_write_tokens: null, reasoning_tokens: 3, usage_provenance: "PROVIDER_REPORTED" },
    ]} />
  </main>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
