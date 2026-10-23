# Harness Template System - AI Agent Infra with DB v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

> This is a technical document for **Chuanxu (川序)**, the **AI Agent
> Management Platform**. `AI Agent Infra with DB` is the unified technical project
> name; database-specific package names identify the adapter and edition.

## Overview

A Harness Template is a reusable agent execution blueprint stored as an `ENTITY` with `ENTITY_TYPE='HARNESS_TEMPLATE'`. It defines input/output schemas, execution mode, and runtime configuration for an agent. Templates are extended via HARNESS_META and support instantiation with variable substitution.

## Lifecycle

Templates use entity states including `DRAFT`, `ACTIVE` and `ARCHIVED`.
Deployment facts are separate from template state. Publish, update, instantiate
and deploy through authorized services; changing text or state cannot bypass a
Business Agent's template admission, owner, model or runtime-isolation requirements.
Template text and substituted variables do not grant database, tool, model or deployment authority.

## Built-in Templates

Seeded idempotently by the selected backend's `4_harness_templates.sql` under
`scripts/deploy/` in a single-backend package or `scripts/deploy/<database>/`
in the unified package.

| Template | Category | Execution Mode | Input Variables | Output Fields |
|----------|----------|---------------|-----------------|---------------|
| **Research Analyst** | research | SEQUENTIAL | role, domain, objective, query | findings, sources |
| **Code Assistant** | development | SEQUENTIAL | role, language, guidelines, task | solution, explanation |
| **Data Analyst** | analytics | PARALLEL | role, focus_area, data_query | analysis, recommendations |
| **Task Planner** | orchestration | CONDITIONAL | role, constraints, objective | plan, dependencies |
| **Security Auditor** | security | SEQUENTIAL | role, policies, action | assessment, risks, mitigations |

All templates are seeded with IMPORTANCE=2, VISIBILITY='SHARED', OWNED_BY_AGENT='SYSTEM'.
