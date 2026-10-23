# Shared answers and final-answer evaluation v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](answer-quality_zh.md)

Portal and Channels share authorized retrieval, evidence selection and answer
preparation. Migration 105 adds immutable rubrics, durable evaluation runs,
encrypted input/output, exact sources and independent reviews on the existing
Task continuity ledger. Case/preparation records and final generated answers
are different evidence; neither alone certifies a software release.

## Answer policy and visible sources

The shared path requests `hybrid` retrieval by default; supported strategies are
`keyword`, `fulltext`, `vector` and `hybrid`. Each channel filters current
Human/Agent authorization before candidate use and rechecks exact sources
before disclosure. Unavailable search or Embedding capabilities may cause a
recorded authorized text fallback. Permission denial never permits broader
retrieval. Reciprocal-rank fusion orders candidates; its score is not a
probability or proof of factual sufficiency.

Evidence assessment separately checks subject, question coverage and explicit
contradictions. A multipart query can be `PARTIAL_MATCH`; conflicting authorized
sources or an ambiguous database/vendor subject can be `AMBIGUOUS`. Empty
evidence is `NO_MATCH`. The policy and approved source-disclosure Profile list
then determine the answer:

| Answer source | Meaning |
|---|---|
| `KNOWLEDGE_GROUNDED` | Prepared against authorized references; citations still require review |
| `KNOWLEDGE_EXTRACTS` | Authorized extracts, without sending source text to an unapproved Profile |
| `MODEL_SUPPLEMENT` | No matching authorized knowledge; general-model supplementation permitted by policy |
| `MIXED_SOURCES` | Partial evidence with permitted, separately labeled general-model coverage |
| `CLARIFICATION_REQUIRED` | The subject needs clarification before answering |
| `INSUFFICIENT_KNOWLEDGE` | Evidence or policy cannot support the requested conclusion |

Portal and Channels expose separate source notices and retrieval/evidence
metadata. A search failure or model failure remains an error. Revoked source
access, changed Profile binding or a now-disabled supplement policy blocks a
queued answer; changing policy does not authorize the old payload. Historical
answers also recheck current source readers. See
[Channel knowledge](channel-knowledge.md) for operational diagnosis.

## Prepare an evaluation

An authorized platform manager opens **Workspaces → Work continuity →
Retrospective and answer evaluation → Answer evaluation** in Dashboard.
The equivalent API prefix is `/api/agent-extensions/answer-evaluation`.
All evaluation routes require `platform.manage`; current Domain/workspace,
Agent visibility, knowledge readers and approved healthy Profile binding are
checked as well. Human clients log into Dashboard with `POST /api/auth/login`,
complete required MFA/setup and retain the session cookie and returned
`csrf_token`. These session-protected routes require that cookie and
`X-CSRF-Token` on every POST, including read-only POSTs, and every other method
except GET, HEAD and OPTIONS; log in again after expiry. Independent Gateway
machine endpoints use scoped Bearer authentication, not Human cookie/CSRF, and
their tokens do not replace the Dashboard session here. Portal does not grant
these management operations.

1. Register a case through `POST /cases` with an approved query, expected
   retrieval mode and the exact expected citation entity IDs. Read cases with
   `GET /cases`. Changing a case creates a new version and retires its prior
   active version; identical active content reuses its existing version.
2. Register a rubric for that exact case version through `POST /rubrics`.
   Set required/forbidden phrases, allowed answer sources, minimum length,
   retrieval strategy and whether real-model generation and independent Human
   review are required. Store the returned rubric revision.
3. Select an active native Agent whose current Profile is healthy and whose
   data/model permissions match the case. Source text is sent only under the
   current approved disclosure policy.

Case example:

```json
{
  "case_id": "deployment-answer-001",
  "query_text": "Which approved deployment steps apply?",
  "expected_mode": "MATCHED",
  "expected_entity_ids": ["KNOWLEDGE_ENTITY_ID"],
  "reason": "Approve the deployment answer case"
}
```

Rubric example (replace `case_version` with the actual returned version):

```json
{
  "case_id": "deployment-answer-001",
  "case_version": 1,
  "rubric": {
    "required_phrases": ["deployment"],
    "forbidden_phrases": [],
    "allowed_answer_sources": ["KNOWLEDGE_GROUNDED"],
    "minimum_characters": 20,
    "require_real_model": true,
    "require_human_review": true,
    "strategy": "hybrid"
  },
  "reason": "Freeze the required answer and evidence checks"
}
```

The case's `expected_mode` is one of `MATCHED`, `PARTIAL_MATCH`, `NO_MATCH`,
`AMBIGUOUS`; it is distinct from the allowed answer-source labels above.
Expected entities are compared as an exact set for final-answer evaluation.
Phrase checks measure only the approved rubric, not factual truth.

## Queue, execute and review

`POST /runs` queues an explicit run:

```json
{
  "case_id": "deployment-answer-001",
  "case_version": 1,
  "rubric_revision": 1,
  "security_domain_id": "DOMAIN_ID",
  "agent_id": "NATIVE_AGENT_ID",
  "entry_kind": "PORTAL",
  "idempotency_key": "answer-run-001",
  "reason": "Evaluate the approved answer path"
}
```

Replace all IDs and versions with current values. `entry_kind` is `PORTAL` or
`CHANNEL`; it records the shared answer-path case and does not itself prove a
browser interaction, actual Channel membership workflow or Portal allocation.
The run freezes case/rubric, Agent/Profile and policy revisions and creates its
Task/Step continuity link. A successful queue response is not a model result.

Read `GET /runs/{run_id}`. Explicitly confirm the possible model request in the
UI, or call `POST /runs/{run_id}/execute` as the authorized operator. Execution
rechecks original authority, source versions, Profile/policy and lease/fencing,
then stores the exact final answer, generation kind, latency and assertions.
`REAL_MODEL` and `DETERMINISTIC` observations stay distinct. A deterministic
clarification may be valid behavior while failing a rubric requiring a real
model. `SUCCEEDED` is the recorded execution outcome, not a factual certificate.

A different authorized **Human** reviews the actual output and references.
Submit `POST /runs/{run_id}/reviews` with `output_digest` from
`observation.output_digest`, `factual_correct`, `citations_supported` and a
reason of at least three characters. The requester cannot review their own run.
A stale digest is rejected. Record a negative review when the answer is wrong;
do not change the case or rubric merely to turn a failed observation into PASS.

## Failures, repeatability and evidence

Run states are `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `UNOBSERVED`.
Completed work is read back without a second model call. An expired attempt
whose send cannot be confirmed becomes `UNOBSERVED`, never an automatic resend.
Changed authority/Profile/policy blocks use. Inspect the original run, Task
attempt, source state and error before proposing a new authorized run. Do not
clear leases or replace a frozen credential to reuse an old send.

`POST /results` retains the earlier explicitly reported-result contract; a
caller-provided `passed` does not prove a final answer was generated. Likewise,
retrieval/preparation tests cannot replace `/runs` output and review.
Compare fixed cases, workloads, rubrics, strategies and model versions; retain
source and package/served-asset digests in the acceptance record. The run itself
returns `release_acceptance: NOT_ESTABLISHED_BY_THIS_RUN`. Five package archives,
seven real database targets, complete workflows, browser checks and current
materials remain separate release requirements.
