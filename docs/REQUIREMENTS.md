# Requirements traceability

Status of each requirement in *Env Management: Requirements for an Enterprise Environment Management Platform*
(6 Nov 2026) as implemented in this repository.

**Status:** ✅ built · 🟡 partly built (the gap is stated) · ⬜ not built.
**Where:** API path (all paths are also served under `/api/v1/…`; OpenAPI at `/docs`) and UI page.
Tests: `backend/tests/test_platform_*.py` (API) and `frontend/e2e/platform.spec.ts` (UI).

## Summary

| Area | ✅ | 🟡 | ⬜ |
| ---- | -- | -- | -- |
| 3.1 Inventory and lifecycle (12) | 12 | 0 | 0 |
| 3.2 Topology (11) | 10 | 1 | 0 |
| 3.3 Deployments and versions (8) | 7 | 0 | 1 |
| 3.4 Booking and scheduling (9) | 9 | 0 | 0 |
| 3.5 Configuration (9) | 9 | 0 | 0 |
| 3.6 Secrets references (5) | 4 | 1 | 0 |
| 3.7 Test data (5) | 5 | 0 | 0 |
| 3.8 Health and monitoring (7) | 5 | 2 | 0 |
| 3.9 Change, incident, issue (6) | 5 | 1 | 0 |
| 3.10 Search and reporting (10) | 9 | 1 | 0 |
| 3.11 Integrations and API (10) | 5 | 4 | 1 |
| 3.12 Governance (9) | 8 | 0 | 1 |
| **Total (101)** | **88** | **10** | **3** |

The three not built are all *could* priority (DEP-08, INT-10, GOV-07). Every *must* is built or partly built;
the partial ones are where an enterprise product (vault, ServiceNow, Jira, cloud APIs) has to be called with
real credentials — the platform side (data model, endpoints, mapping) is built and those connectors are the
next step.

## 3.1 Environment inventory and lifecycle

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| ENV-01 | M | ✅ | Environment record with id, name, description, type, tier, purpose. Types are a configurable list (`env_types` setting). |
| ENV-02 | M | ✅ | Owner, delivery manager, technical contact, cost centre, programme, support group. |
| ENV-03 | M | ✅ | Lifecycle Requested → Provisioning → Available ⇄ In use / Frozen / Under maintenance → Decommissioning → Retired. Allowed transitions are enforced (`POST /environments/{id}/transition`) and every move is audited with its reason. |
| ENV-04 | M | ✅ | Platform, cloud account / data centre, region, network zone, access URLs. |
| ENV-05 | M | ✅ | Parent/child (cycle-checked), family, shared-infrastructure flag; system instances can be shared between environments (TOP-05). |
| ENV-06 | S | ✅ | Tags; custom attributes and mandatory fields per environment type, configured in Admin → Settings (`custom_attributes`, `mandatory_fields`). Validation errors name the field. |
| ENV-07 | S | ✅ | `POST /environments/{id}/clone` copies the record, topology and configuration (secret values are not copied). |
| ENV-08 | S | ✅ | `POST /environments/requests` creates a Requested environment with an SLA due date (`environment_request_sla_days`); approval is the move to Provisioning by an environment manager; breaches are flagged on the record and in data quality. |
| ENV-09 | S | ✅ | Entering Decommissioning creates a checklist (configurable); Retired is blocked until it is complete and no live bookings remain; retirement date set; history kept (soft records). |
| ENV-10 | M | ✅ | Import CSV / Excel / JSON with preview (`POST /environments/import?dry_run=`), bulk update (`PATCH /environments/bulk`), full REST API. |
| ENV-11 | M | ✅ | Confirmation in the UI; soft delete, restore (`POST /environments/{id}/restore`), admin-only purge of deleted records. |
| ENV-12 | C | ✅ | Run cost, chargeback model, licence constraints. |

## 3.2 Topology

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| TOP-01 | M | ✅ | Catalogue = Flow Explorer systems plus profile (category, criticality, technology, owner, domain): `/catalogue/systems`, UI Catalogue. |
| TOP-02 | M | ✅ | System instances per environment with instance name, URL, version, build, release (`/environments/{id}/instances`). |
| TOP-03 | M | ✅ | Integrations between instances per environment, linked to the catalogue integration (protocol, pattern, hops) or ad hoc, with status and endpoint. |
| TOP-04 | M | ✅ | Mode real / virtualised / stubbed / mocked / not available, with the service-virtualisation asset reference. |
| TOP-05 | M | ✅ | An instance can serve several environments (`shared_with`); `/topology/shared`; booking conflicts take shared instances into account. |
| TOP-06 | M | 🟡 | Per-environment topology diagram (health and status coloured) and journey view, plus the existing Flow Explorer (filters by journey, pattern, protocol). Gap: the Flow Explorer graph itself is not yet filterable by environment. |
| TOP-07 | S | ✅ | `/topology/compare?left=&right=`: missing systems, version and mode differences, integration status/protocol/endpoint differences. |
| TOP-08 | S | ✅ | `/environments/{id}/journeys`: systems and integrations each journey touches, and gaps. |
| TOP-09 | M | ✅ | Last verified + verifier on instances and integrations, one-click verify, stale after `STALE_AFTER_DAYS` (90). |
| TOP-10 | S | ✅ | `/impact?system_id=`: affected environments, journeys, integrations, bookings/projects and open issues. |
| TOP-11 | M | ✅ | Export Excel / JSON / CSV / Mermaid diagram; import Excel / JSON / CSV with row-level errors, preview and rollback. |

Open question 1 (environment column in the Excel template): resolved by keeping the catalogue environment-neutral
and mapping it onto environments through instances; "Add all from catalogue" bootstraps an environment.

## 3.3 Deployments and versions

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| DEP-01 | M | ✅ | Version, build, commit, release per instance. |
| DEP-02 | M | ✅ | Deployment history: who, when, pipeline/run link, outcome, rollback reference (`/deployments`, rollback endpoint). |
| DEP-03 | M | ✅ | `POST /api/v1/ci/deployments` with an API token; tool recorded (Jenkins, Azure DevOps, GitHub Actions, GitLab). Example call in Config → Pipeline access. |
| DEP-04 | M | ✅ | `/version-matrix`, UI Releases → Version matrix. |
| DEP-05 | S | ✅ | `/drift`: versions and configuration against a baseline or the next environment on the promotion path. |
| DEP-06 | S | ✅ | Promotion paths with gate status per stage and pending promotions. |
| DEP-07 | S | ✅ | Freeze / blackout calendar; deployments during an enforced freeze need an override reason or an environment manager; bookings get warnings. |
| DEP-08 | C | ⬜ | Deployment request/approval workflow not built (deployments are recorded, not requested). |

## 3.4 Booking and scheduling

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| BKG-01 | M | ✅ | Book a whole environment or selected instances for project, team, purpose and date range. |
| BKG-02 | M | ✅ | Timeline by environment, project or team (UI Bookings) with freezes overlaid; calendar list (UI Calendar). |
| BKG-03 | M | ✅ | `POST /bookings/check` and on create: whole-environment, same-component and shared-component conflicts. |
| BKG-04 | S | ✅ | Approval for configured types (`booking_approval_types`); delegated approver per booking; escalation notification after `booking_escalation_hours`. |
| BKG-05 | M | ✅ | Requested / Approved / Active / Completed / Cancelled (+ Rejected, Waitlisted); automatic start and release at the end date (scheduler and on read). |
| BKG-06 | S | ✅ | Recurring bookings (`recurrence`), approved or cancelled as a series. |
| BKG-07 | S | ✅ | `/reports/forecast` demand vs supply per type and week; `/reports/contention`. |
| BKG-08 | C | ✅ | Priorities (production fix > release > project > training), waitlist, automatic promotion when capacity frees up. |
| BKG-09 | M | ✅ | In-app notifications, e-mail (SMTP), Slack / Teams webhooks: created, decided, conflict, expiring, released, escalated. |

## 3.5 Configuration and variables

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| CFG-01 | M | ✅ | Create, edit, delete, search in the UI; key format, duplicates and typed values validated. |
| CFG-02 | M | ✅ | Global default < environment < system instance; `/environments/{id}/config` shows the source and what each value overrides. |
| CFG-03 | M | ✅ | Description, owner, type, sensitivity, last changed by/at. |
| CFG-04 | M | ✅ | `/config/compare?env_ids=` across two or more environments; secrets compared without revealing them. |
| CFG-05 | M | ✅ | Per-variable history (old/new value, secrets excluded) with restore, including restoring deleted variables. |
| CFG-06 | S | ✅ | Import .env / JSON / YAML / CSV with preview; export in the same formats. |
| CFG-07 | S | ✅ | Bulk edit (`/environments/{id}/variables/bulk`), copy between environments; protected types (`protected_types`) create an approval request. |
| CFG-08 | S | ✅ | Templates per environment type; missing/empty required keys shown and addable. |
| CFG-09 | S | ✅ | `GET /api/v1/config/{env}?format=env|json|yaml` for pipelines (token). No packaged pipeline plugin. |

## 3.6 Secrets and credential references

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| SEC-01 | M | 🟡 | Secrets can be stored as a vault reference (value cleared) and are exported as `vault:<ref>`. Gap: no live vault client (HashiCorp / Azure Key Vault), and legacy plaintext secret values are still accepted (flagged as errors in data quality). |
| SEC-02 | M | ✅ | Masked in UI, API and exports by default; reveal is a separate call, contributor+ and audited. |
| SEC-03 | M | ✅ | Exports exclude secrets unless `include_secrets=true` by an environment manager (audited). |
| SEC-04 | S | ✅ | Last rotated, next due, owner; overdue alerts from the scheduler; flagged in data quality. |
| SEC-05 | C | ✅ | Credential-looking keys and values (AWS keys, private keys, JWTs, tokens, URLs with passwords) in non-secret fields are warned on save and listed in data quality. |

## 3.7 Test data

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| TDM-01 | S | ✅ | Data set catalogue per environment. |
| TDM-02 | S | ✅ | Refresh / masking jobs with status and owner; a successful job updates the data set. |
| TDM-03 | S | ✅ | Source environment and system links. |
| TDM-04 | C | ✅ | Reserve / release for a booking or until a date. |
| TDM-05 | S | ✅ | Environment sensitive / production-derived flags (set automatically from data sets), controls text, risk rating. |

## 3.8 Health, status and monitoring

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| HLT-01 | M | ✅ | Healthy / Degraded / Down / Unknown per environment and instance with last-checked time; environment rolls up from instances. |
| HLT-02 | S | 🟡 | Scheduled HTTP and TCP checks with history. Gap: custom scripts are deliberately not run by the server (security); run them elsewhere and post results to HLT-03. |
| HLT-03 | S | 🟡 | Generic ingestion (`POST /health/events`) usable from Dynatrace, Datadog, Splunk and AppDynamics webhooks; native Prometheus Alertmanager adapter. Gap: no native adapters for the other tools' payload formats. |
| HLT-04 | M | ✅ | Manual override / planned outage with reason and expiry, per environment or instance. |
| HLT-05 | S | ✅ | Uptime %, outage count, mean time to restore (`/environments/{id}/health/metrics`). |
| HLT-06 | S | ✅ | Owners and current bookers notified on change; subscriptions per user (in app or e-mail) and webhooks. |
| HLT-07 | S | ✅ | Status summary on the dashboard (`/health/status`). |

## 3.9 Change, incident and issue management

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| CHG-01 | M | ✅ | Issues and incidents against an environment or instance with severity, owner, status, resolution. |
| CHG-02 | M | 🟡 | External ticket links; inbound status sync (`POST /tickets/webhook`, ServiceNow/Jira/ADO status and priority mapping) and outbound `issue.*` webhook events. Gap: no native ServiceNow/Jira API client to create tickets. |
| CHG-03 | S | ✅ | Known-issues register shown when booking and in readiness. |
| CHG-04 | M | ✅ | `/calendar`: planned changes, releases, outages, refreshes, maintenance, bookings, deployments, incidents. |
| CHG-05 | S | ✅ | `/reports/test-impact`: hours lost per booking from outages and logged incident time. |
| CHG-06 | C | ✅ | Ageing, SLA due dates per severity, breach alerts, root-cause categories (`/reports/issues`). |

## 3.10 Search, navigation and reporting

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| RPT-01 | M | ✅ | Global search (header) across environments, systems, instances, integrations, non-secret variables, bookings, issues, test data. |
| RPT-02 | M | ✅ | Every list: filter, sort, column choice, CSV export, saved views (per user, optionally shared). |
| RPT-03 | M | ✅ | Dashboard: status, availability, utilisation, open issues, approvals, data quality, upcoming changes. |
| RPT-04 | M | ✅ | Utilisation by environment, team or project with idle time. |
| RPT-05 | S | ✅ | Contention report: over-subscribed environments and weeks. |
| RPT-06 | S | ✅ | Readiness report (RAG) covering health, components, topology, verification, versions, configuration, data, issues, calendar. |
| RPT-07 | C | ✅ | Cost by environment, programme, cost centre; allocation to projects by booked hours. |
| RPT-08 | S | 🟡 | Export to CSV / Excel (server) and print-to-PDF. Gap: scheduled e-mail delivery of reports. |
| RPT-09 | S | ✅ | Data quality dashboard with score and fix links. |
| RPT-10 | S | ✅ | Empty states with guidance; admins can load sample data; import templates. |

## 3.11 Integrations and API

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| INT-01 | M | ✅ | REST API for every UI function, OpenAPI docs at `/docs`, versioned alias `/api/v1`, API tokens. |
| INT-02 | M | 🟡 | `GET /cmdb/export` (CIs) and `POST /cmdb/sync` (ServiceNow-style field mapping, preview, upsert by CMDB id or name). Gap: no scheduled connector that calls the CMDB itself. |
| INT-03 | M | ✅ | Deployment reporting and configuration reads over REST with tokens (see Config → Pipeline access). |
| INT-04 | M | 🟡 | As CHG-02: inbound sync and outbound events; no native create-ticket client. |
| INT-05 | M | ✅ | SSO via the gateway (`AUTH_MODE=header`, OIDC or SAML) with group-to-role mapping for every role (`ADMIN_GROUPS`, `ENV_MANAGER_GROUPS`, …) and group role assignments. |
| INT-06 | S | ✅ | Webhooks with event patterns and HMAC signatures for environment, booking, deployment, health, issue, config and approval events. |
| INT-07 | S | 🟡 | Slack / Teams notifications; `POST /chatops/command` (`status`, `who`, `free`, `book`). Gap: Slack request-signature verification — protect the endpoint with an API token (`?api_token=`) or the gateway. |
| INT-08 | C | ✅ | `GET /calendar.ics` subscription for Outlook / Google (accepts `?api_token=`). |
| INT-09 | S | 🟡 | `POST /discovery/ingest` verifies the inventory against discovered resources (version mismatches, unknown and missing resources). Gap: the platform does not call AWS / Azure / Kubernetes APIs itself; a discovery job posts the results. |
| INT-10 | C | ⬜ | Test management tool integration not built. |

## 3.12 Governance, audit and administration

| ID | P | Status | Where / notes |
| -- | - | ------ | ------------- |
| GOV-01 | M | ✅ | Roles admin, env_manager, contributor, booker, viewer; scoped to environment, programme, region or family; checked on every write. |
| GOV-02 | M | ✅ | Audit of creates, updates, deletes, bookings, approvals, reveals and exports; SHA-256 hash chain with `/audit/verify`; searchable and exportable. |
| GOV-03 | S | ✅ | Approval rules per environment type for bookings (`booking_approval_types`) and configuration changes (`protected_types`). |
| GOV-04 | S | ✅ | Maximum booking length, mandatory fields, freeze windows, SLAs — enforced in the workflows. |
| GOV-05 | M | ✅ | Preview, diff and rollback for environment, variable and topology imports and bulk edits (Admin → Bulk operations), in addition to flow dataset versions. |
| GOV-06 | S | ✅ | `PORTFOLIO_SEGREGATION=true`: users see and change only environments in their scoped assignments. |
| GOV-07 | C | ⬜ | Retention policies and legal hold not built. |
| GOV-08 | M | ✅ | Admin console: roles, API tokens, webhooks, lists of values, policies, checklist and notification templates (JSON editor), audit, approvals. |
| GOV-09 | S | ✅ | Banner showing the instance (`APP_ENV`: local, QA, production). |

## 4. Non-functional requirements

| ID | Status | Notes |
| -- | ------ | ----- |
| NFR-01 | 🟡 | Scale test with 500 environments, 5,000 instances, 2,000 bookings (`test_platform_performance.py`). 20,000 integrations and 1 million audit events not yet load-tested. |
| NFR-02 | 🟡 | List, matrix, search and dashboard asserted under 2 s at that scale (SQLite, in-process). Topology graph at 1,000 nodes not measured. |
| NFR-03 | ⬜ | 10,000-row import timing not measured. |
| NFR-04 | ⬜ | Hosting concern. Note: the Render free plan sleeps when idle (cold start), which conflicts with "no cold-start delay". |
| NFR-05 | ⬜ | Backups / restore are a Supabase / hosting configuration task. |
| NFR-06 | 🟡 | Consistent navigation, errors that name the field, confirmation on destructive actions; inline help is partial. |
| NFR-07 | 🟡 | Responsive MUI layout; not tested on tablet/mobile. |
| NFR-08 | 🟡 | Request logging, slow-request warnings, `X-Response-Time-ms`, Prometheus `/api/metrics`. No tracing or runbook yet. |
| NFR-09 | ✅ | Optimistic concurrency (`row_version`) on environments, instances, variables, bookings, issues; 409 with a reload prompt. |
| NFR-10 | ✅ | JSON, CSV, Excel, YAML, .env, ICS, Mermaid, OpenAPI. |
| NFR-11 | 🟡 | pytest (unit/API, PostgreSQL migrate + seed) and Playwright in CI; no separate performance suite. |
| NFR-12 | 🟡 | Stored in UTC, shown in the user's time zone. Multiple calendars not built. |
| NFR-SEC / NFR-ACC | — | Deferred, as directed. Colour is never the only cue on status chips and diagrams. |
