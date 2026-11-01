# Structured retrospectives and governed read-only tool turns

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](model-workflows_zh.md)

These explicit workflows reuse Task continuity, pending candidates, Action Cards
and Workers. Model text, valid JSON and tool names do not grant authority.
They require the v5.0.2 runtime contract and migration 108.

## Retrospective output contracts

`TEXT_JSON` validates the completed JSON and business structure without claiming
native strict decoding. `NATIVE_STRICT` requires an unexpired actual observation
matching the saved Profile revision, model, Chat Completions dialect, parameters
and complete `response_format` digest. A generic `CX_OK` probe does not verify
the retrospective's business schema. Both paths create only `PENDING` Memory,
Knowledge, Experience or Skill candidates. Independent review and explicit
publication still apply.

Use **Work continuity → Quality → Retrospectives** to select the exact schema
and an existing matching observation, or explicitly request a schema probe.
Changing Profile or target family clears incompatible selections. A page visit
and contract read never probe the model.

## A bounded tool round trip

The selected subset supports one independently approved read-only tool, one exact
currently readable source revision, and one required path or query argument.
The HTTP method is GET and the response must satisfy the registered JSON-object
schema. GET alone is not evidence of a read-only effect; the approved registration
supplies the effect classification.

Outbound HTTP tools identify the installed product and version in the default
`User-Agent` (`Chuanxu/<version>` or `OpenTenBase-AgentX/<version>`). An explicit
header in an approved HTTP request retains its value. This client identity does
not change destination validation, redirects, approval or source authorization.

Registration binds the current tool revision, input/output contracts, update
time, source revision and digest. Reimport, exposure revocation and contract
changes invalidate the old registration. The model supplies a complete proposal;
the service then atomically creates the existing tool request and pending Worker
job. A second independent Human Action Card must authorize that exact call.
The model cannot approve it.

An ordinary business Agent can request the invocation approval in its current
business Channel with `{"channel_id":"<channel-id>"}` at the turn's
`approval-requests` endpoint. The Channel must be active, belong to the turn's
original Security Domain and currently admit the original Agent. Its independent
Human approver must also retain current Channel and Domain membership and
approval permission. The Agent must retain `channels.write` through the final
Worker check. Neither a platform-management role nor an old membership bypasses
these Domain checks.

The first omitted Channel uses Platform Administration, which retains its
protected admission rules. Once an Action Card is bound, an omitted Channel
retains that card's original Channel; a different explicit Channel is rejected.
The business Channel and original Domain are included in the immutable approval
binding. Registration approvals and all other platform actions continue to use
the protected Platform Administration Channel.

Immediately before dispatch, the Worker rechecks its lease, original Agent
instance and credential, request digest, current approver, exposure, source
authority and governance. The bounded result enters the next model call as
untrusted `tool` data with the original call ID. It never becomes a system
instruction. Secret-bearing or invalid output is rejected before that next call.

Each turn freezes at most two model requests, one tool invocation, zero format
repair requests and an overall deadline. An unknown model or tool send retains
`UNOBSERVED`; reading or repeating run does not resend it. Workers holding a
business lease cancel an unused capacity queue admission rather than wait.
Final answers are encrypted and current authority is rechecked on reads.
Lifecycle success does not replace independent factual and citation review.

## Authenticated API

The prefix is `/api/agent-extensions`; the machine transport retains its existing
Gateway prefix and authentication. Deployment routing may add an outer prefix.

| Method and suffix | Operation |
|---|---|
| `GET /retrospective-output-contracts/{profile_id}?target_family=...` | Read the exact output schema and matching probe metadata. |
| `POST /model-output-contracts/{profile_id}/probes` | Explicitly probe the complete selected output contract. |
| `GET /model-read-tools?security_domain_id=...&after=...&limit=...` | Read the bounded authorized registration directory. |
| `POST /model-read-tools/approval-requests` | Request independent registration approval. |
| `POST /model-read-tools` | Adopt an approved registration Action Card. |
| `GET /model-read-tools/{registration_id}/contract` | Read the current exact tool contract. |
| `GET /model-tool-turns?security_domain_id=...&after=...&limit=...` | Read authorized turn summaries. |
| `POST /model-tool-turns`, `GET /model-tool-turns/{turn_id}` | Create or inspect one exact turn. |
| `POST /model-tool-turns/{turn_id}/run` | Explicitly advance one current phase. |
| `POST /model-tool-turns/{turn_id}/approval-requests` | Request approval of the exact proposed invocation. |
| `POST /model-tool-turns/{turn_id}/admit` | Adopt the independent invocation approval. |

Reads do not run models or Workers. Writes retain existing permission, CSRF and
machine-scope checks. JSON cannot supply a trusted actor, replacement credential
or self-reported `VERIFIED` state. Execution requires the original Agent
transport; a Human observer can read authorized summaries and original approval
links without impersonating that transport. Retrospectives may preserve an
original Human Web Session or Agent credential and recheck it before dispatch.
Existing Action Card expiry remains authoritative.

Historical retrospectives without the new contract show `LEGACY_TEXT_JSON`;
they do not establish native strict-output capability. See
[capacity and observations](model-endpoint-capacity.md) and
[processing recovery](processing-recovery.md).
