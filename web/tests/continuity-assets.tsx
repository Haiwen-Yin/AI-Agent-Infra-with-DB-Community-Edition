import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import ContinuityAgentAssets from "../src/ContinuityAgentAssets";
import "../src/app.css";

type Harness = { calls: string[]; failures: number; hold: string; pending: { path: string; resolve: () => void; reject: (error: Error) => void }[] };
declare global { interface Window { assetsHarness: Harness } }
const params = new URLSearchParams(window.location.search);
const state = window.assetsHarness = { calls: [], failures: 0, hold: params.get("hold") || "", pending: [] } as Harness;
const scenario = params.get("scenario");
const rows = (start: number, end: number, kind: string, prefix = "") => Array.from({ length: end - start + 1 }, (_, index) => {
  const key = `${prefix}${kind}-${String(index + start).padStart(3, "0")}`;
  return kind === "binding" ? { binding_id: key, purpose: key, version: 1, status: "ACTIVE", source: { family: "MEMORY", entity_id: key, revision_id: key } }
    : { source_id: key, row_version: 1, source_kind: "DOCUMENT", status: "ACTIVE" };
});
const request = async (path: string, options?: RequestInit) => {
  state.calls.push(path);
  const url = new URL(path, window.location.origin);
  const domain = url.searchParams.get("security_domain_id") || "";
  const agent = url.searchParams.get("agent_id") || "";
  const finish = async (value: Record<string, any>) => {
    if (state.hold && (path.includes(state.hold) || state.hold === `data:${domain}` && !!agent || state.hold === `agent:${agent}` && !!agent))
      await new Promise<void>((resolve, reject) => state.pending.push({ path, resolve, reject }));
    return value;
  };
  if (url.pathname === "/api/context/assemblies") return { items: [] };
  if (url.pathname === "/api/continuity-recipients") return finish({ items: (scenario === "scope" ? ["a", "b"] : ["a"]).map(suffix => ({
    principal_id: scenario === "scope" ? `${domain}-agent-${suffix}` : "agent-a", display_name: `Synthetic Agent ${suffix}`, principal_type: "AGENT", status: "ACTIVE",
  })) });
  if (url.pathname.endsWith("/directory/recommend")) {
    const body = JSON.parse(String(options?.body));
    return finish({ candidate_count: 1, items: [{ entity_id: `skill-${body.security_domain_id}`, name: `Skill ${body.security_domain_id}`, version: 1, content_digest: "a".repeat(64) }] });
  }
  if (url.pathname.endsWith("/directory/load")) {
    const body = JSON.parse(String(options?.body)).value;
    return finish({ name: body.entity_id, version: 1, content_digest: body.content_digest, content: { text_content: `Private body for ${body.entity_id}` } });
  }
  const kind = url.pathname.endsWith("/asset-bindings") ? "binding" : "source";
  const paged = scenario === "both" || (scenario === "bindings" ? kind === "binding" : kind === "source");
  const after = url.searchParams.get("after");
  if (after && state.failures > 0) { state.failures--; throw new Error("Synthetic page unavailable"); }
  const prefix = scenario === "scope" ? `${domain}:${agent}:` : "";
  return finish({ items: after ? rows(50, 55, kind, prefix) : rows(1, 50, kind, prefix), next_cursor: paged && !after ? `${kind}-050` : null });
};
function Harness() {
  const [domain, setDomain] = useState(scenario === "scope" ? "domain-a" : "synthetic-domain");
  return <main style={{ maxWidth: 1200, margin: "20px auto", padding: 12 }}>
    <button type="button" onClick={() => setDomain(previous => previous === "domain-a" ? "domain-b" : "domain-a")}>Switch domain</button>
    <ContinuityAgentAssets request={request} text={(_zh, en) => en} domain={domain} canWrite={true}
      canManage={true} canOperateAgents={true} onSourceRefsChange={() => undefined} />
  </main>;
}
createRoot(document.getElementById("root")!).render(<Harness />);
