# Routes — frontend pages ↔ backend API

Maps the UI's TanStack Start routes to the FastAPI endpoints they (will) call.
Frontend routes exist today (`src/routes/*`); the backend endpoints are specified
here and in `documentation/Sprint1/integration-plan.md` (§5) and are **not built
yet**.

## Frontend routes (file-based, `src/routes/`)

| File | URL | Purpose | Data it needs |
|---|---|---|---|
| `index.tsx` | `/` | Landing + `UploadZone` (+ paste, "Try Demo") | none until submit; then kicks off `/api/citations/verify` |
| `dashboard.tsx` | `/dashboard` | Main analysis view: ExecutiveSummary, CitationTable, CitationCards, DocumentPreview, AnalysisDrawer | the `DocumentReport` from `/verify` |
| `report.tsx` | `/report` | Partner-ready report (print/export) | same `DocumentReport` |
| `__root.tsx` | — | App shell (QueryClientProvider, error/404 boundaries) | — |

Notes: `routeTree.gen.ts` is auto-generated — don't hand-edit. `react-query`'s
`QueryClient` is already provided in `__root.tsx` / `router.tsx`, so use a query
for the report and a mutation for `/verify`.

## Backend API (to build — see integration-plan §5/§6)

Base prefix `/api` (from `Settings.api_prefix`). New router
`app/api/endpoints/citations.py`, registered in `app/api/router.py`.

| Method & path | Request | Response | Purpose |
|---|---|---|---|
| `GET /health` | — | `{ "status": "ok" }` | liveness (exists) |
| `POST /api/citations/extract` | `multipart file` **or** `{ "text": "…" }` | `list[EnrichedCitation]` | regex + LLM extraction only (fast, debuggable) |
| `POST /api/citations/verify` | `multipart file` **or** `{ "text": "…" }` | `DocumentReport` | **headline** — extract → resolve → judge → classify |

`DocumentReport` (proposed): `{ source, summary{total, verified, mischaracterised, out_of_context, non_existent}, citations: CitationReport[] }`.
`CitationReport` = `EnrichedCitation` + resolution fields + `AnalysisDict` + `Classification`.

## Backend `CitationReport` → frontend `Citation` (`src/lib/mock-citations.ts`)

| UI field | Source |
|---|---|
| `id` | `EnrichedCitation.id` (stringified) |
| `caseName` | `full_case_name` ?? `case_name` |
| `court` | `court_name` ?? `court` |
| `year` | `year` |
| `citation` | `raw` |
| `holding` | `AnalysisDict.plain_language_holding` |
| `howUsed` | `relevant_text` (?? `proposition`) |
| `summary` / `reasoning` | from `premise_summary` / verdict `reason` |
| `status` | from `Classification` (see `interactions.md` mapping) |
| `confidence` | `Classification.confidence * 100` |
| `issue` / `action` / `recommendation` | derived from verdict + `premise_summary` |
| `paragraph` | citation position in the document (optional) |

## Dev wiring

The frontend dev server (Vite) and the API (uvicorn, `:8000`) are separate origins.
Either:
- **Vite dev proxy** (recommended for dev): proxy `/api → http://localhost:8000`
  in `vite.config.ts`, so the SPA calls same-origin `/api/...`; or
- **Serve the built SPA from FastAPI** (single origin for the demo): mount the
  `vite build` output as static files.

Without one of these, add CORS middleware to FastAPI for the Vite origin.
