# Env Management

Two tools in one app:

- **Integration Flow Explorer**: pick an upstream and a downstream system and see the integration path
  between them (hops, gateways, protocols, queues) highlighted on a layered architecture diagram.
- **Environments**: manage environments (dev, staging, prod…) and their configuration variables.

| Layer | Stack |
| ----- | ----- |
| Frontend | React 18 + TypeScript, Vite, React Flow (`@xyflow/react`), MUI, TanStack Query, Zustand, html-to-image + jsPDF |
| Backend | Python, FastAPI, SQLAlchemy 2 + Alembic, Pydantic, openpyxl |
| Storage | PostgreSQL (SQLite for local / pilot) |
| Tests / CI | pytest, Playwright, GitHub Actions |
| Hosting | Cloudflare Pages (frontend) · Render (backend) · Supabase (PostgreSQL) |

**Deployment:** `qa` branch → QA, `main` branch → production, via GitHub Actions. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.flows.seed            # create tables + load the sample dataset (optional)
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173 (proxies /api to :8000)
```

API docs: http://localhost:8000/docs

With Docker (PostgreSQL + backend + nginx-served UI on http://localhost:8080):

```bash
docker compose up --build
docker compose exec backend python -m app.flows.seed
```

## Integration Flow Explorer

### Data model

The Excel workbook is the initial source of truth, normalised into:

| Entity | Key attributes |
| ------ | -------------- |
| **System** | id, name (unique), type (`upstream`, `downstream`, `gateway`, `queue_manager`, `mainframe`), optional layer override, domain, owner, environment, notes |
| **Integration** | id, name, journey, upstream_id, downstream_id, pattern (`sync`/`async`), primary protocol, status, verified_by, last_verified, notes |
| **Hop** | integration_id, sequence (1..n, no gaps), from_system, to_system, protocol (`REST`, `SOAP`, `MQ`, `FILE`, `MFT`), direction (`request`/`reply`), queue name, queue manager, notes |
| **Component detail** | system_id, gateway tier (e.g. DataPower tier), endpoint, queue references, notes |

An integration is an ordered list of hops; one upstream/downstream pair can have several integrations (one per journey).

### Excel template

Download it from **Data → Empty template** (or `GET /api/template`). Sheets: `README`, `Systems`, `Integrations`,
`Hops`, `ComponentDetails` (optional). The template has dropdowns for enums and cross-sheet dropdowns for
system/integration ids, to prevent bad data at the source. `backend/sample_data/` contains the template and a
filled sample.

### Features

| Requirement | Where |
| ----------- | ----- |
| FR-1 searchable upstream/downstream, downstream filtered to valid pairs | Flow Explorer, `GET /api/pairs` |
| FR-2 journey / pattern / protocol filters | Flow Explorer |
| FR-3 highlight path, dim the rest | Diagram |
| FR-4 several matching integrations, switchable | "Matching integrations" list |
| FR-5 numbered hops, protocol-labelled, colour-coded edges | Diagram + hop list |
| FR-6 request vs reply | Reply edges are thinner with an open arrow and "↩ reply" label; Both / Request / Reply toggle |
| FR-7 details of a clicked node or edge | Details panel |
| FR-8 step-by-step narrative from the hops | "Step by step" section (generated server-side) |
| FR-9 layered layout with zoom, pan and fit to screen | Channels → API gateway → Integration tier → Messaging → Core systems |
| FR-10 free exploration | Click any system with no flow selected: neighbours highlighted, connections listed |
| FR-11 Excel upload with validation by sheet/row/column | Data → Import (validate first, then import) |
| FR-12 download dataset as Excel or JSON | Data page, `GET /api/export?format=xlsx\|json` |
| FR-13 version history and rollback | Data → Version history |
| FR-14 in-app editing of systems, integrations and hops | Data → Systems / Integrations |
| FR-15 export PNG / SVG / PDF and deep links | Export / Copy link on the diagram, e.g. `/flows?from=Polisy&to=Billing&journey=renewal` |

Validation rules:
- **Errors** block an import or edit: invalid values, unknown references, duplicate ids or names, duplicate or
  missing hop sequence numbers, integrations without hops.
- **Warnings** are reported but accepted: orphan systems; a hop that doesn't start where the previous one ended;
  a request path that doesn't start at the upstream or end at the downstream; MQ hops without a queue name.

Every import, edit and rollback stores a full snapshot as a new version and is written to the audit log
(who, what, when). A rollback is itself a new version, so it can be undone.

### API

| Endpoint | Purpose |
| -------- | ------- |
| `GET /api/systems?type=` | Systems, filterable by type |
| `GET /api/pairs?upstream=` | Valid upstream/downstream pairs (with filters) |
| `GET /api/integrations?from=&to=&journey=&pattern=&protocol=` | Matching integrations with ordered hops and narrative; `from`/`to` accept ids or names |
| `GET /api/graph` | Base architecture: systems, aggregated edges, integration summaries |
| `GET /api/flow-config` | Protocol colours/line styles, layer order, system type styles |
| `POST /api/import?dry_run=` | Upload Excel; returns a validation report (maintainer) |
| `GET /api/export?format=` · `GET /api/template` | Dataset as Excel/JSON · empty template |
| `GET /api/imports` · `POST /api/imports/{id}/rollback` | Version history · rollback (maintainer) |
| `POST/PUT/DELETE /api/systems`, `/api/integrations` | In-app editing (maintainer) |
| `GET /api/audit` · `GET /api/me` | Audit log (maintainer) · current user and roles |

### Configuration-driven styling

`backend/app/flows/flow_config.json` defines layer order, the default layer per system type, and protocol colours
and dash patterns. Point `FLOW_CONFIG_PATH` at your own copy to change them without a rebuild. Protocols are
distinguished by colour, line pattern and text label, so colour is never the only cue.

### Performance

Measured with 300 systems / 400 integrations / 2,000 hops:
- the backend answers path queries in under 10 ms (asserted in `tests/test_flows_performance.py`);
- the production UI renders a selected path in about 0.55 s.

## Security and roles

- **Roles:** *viewer* (explore, export, view history) and *maintainer* (import, edit, roll back, audit log,
  change environments).
- **`AUTH_MODE=dev`** (default) runs every request as `DEV_USER` with `DEV_ROLES`. For local use only.
- **`AUTH_MODE=header`** is for SSO. Put the app behind your platform gateway or an auth proxy such as
  oauth2-proxy (OIDC or SAML). It forwards the user and groups in `X-Forwarded-User` / `X-Forwarded-Groups`.
  Groups in `MAINTAINER_GROUPS` get the maintainer role. If `VIEWER_GROUPS` is empty, any authenticated user
  can view. In this mode the backend must only be reachable through that gateway, because it trusts those
  headers.
- **Data:** only metadata is stored (names, endpoints, queue names). The template and UI warn against putting
  credentials or payload data in.

See `backend/.env.example` for all settings.

## Tests

```bash
cd backend && pytest                                     # API, validation, import/export, rollback, roles, perf
cd frontend && npm run typecheck && npx playwright test  # e2e: starts a seeded backend + Vite on ports 8001/5174
```

CI (`.github/workflows/ci.yml`) runs pytest, a migrate-and-seed against PostgreSQL, the frontend build and
Playwright. Pushes to `qa` / `main` run the same checks and then deploy (`.github/workflows/deploy.yml`).

## Decisions taken on the open questions

1. **Master data:** Excel stays the import format, and in-app edits are versioned alongside imports.
   Export → edit in Excel → re-import is a supported round trip, so either can be the master.
2. **Authoritative sequence diagrams:** not available yet. Each integration has `verified_by` /
   `last_verified`; the UI flags flows that were never verified or were verified more than 12 months ago.
3. **Environments:** one dataset per deployment, with `environment` recorded on each system. Separate SIT/UAT/PROD
   datasets would need a dataset dimension (not built).
4. **Hosting:** internal only; Docker images plus SSO via the existing gateway.
5. **DataPower tiers and MQ hub:** modelled as distinct nodes (type `gateway` / `queue_manager`) so hops can pass
   through them. Tier details live in component details, and the `layer` column places each tier in the right
   band.

## Environments (variables)

Environments hold key/value variables; secret values are masked in the UI and can be exported as `.env`.
Note that values are stored in plain text, so this part is not suitable for production credentials until
encryption at rest is added.
