# Frontend interactions ↔ backend

How each UI interaction should drive the backend and update state. This is the
**spec** for wiring the Lovable UI (`app/frontend/src`) to the FastAPI backend;
the wiring itself is not done yet (see "Gaps to close"). Data contract today lives
in `src/lib/mock-citations.ts` (`Citation`); the backend shapes are in
`app/schemas/citation.py`.

## End-to-end journey

```
/  (Landing)
  ├─ Upload a file (UploadZone)        ─┐
  ├─ Paste text (to add)               ─┤→ POST /api/citations/verify
  └─ "Try Demo" (sample doc)           ─┘        │ (pending)
        │                                         ▼
   AnalysisProgress (real pending state)   DocumentReport
        │                                         │
        ▼                                         ▼
/dashboard  ── ExecutiveSummary · CitationTable · CitationCards · DocumentPreview
        │           └─ row/card click → AnalysisDrawer (per-citation detail)
        ▼
/report  (partner report) ── Print / Export PDF (window.print)
```

## Per-interaction map

| Where | Trigger | Backend call | State / cache | UI result |
|---|---|---|---|---|
| `UploadZone` | drop / browse a file | `POST /api/citations/verify` (multipart `file`) | react-query mutation; store `documentName` | show `AnalysisProgress`, then go to `/dashboard` |
| Landing paste box *(to add)* | paste text + submit | `POST /api/citations/verify` (`{ "text": ... }`) | same mutation | same |
| "Try Demo" | click | bundled sample `DocumentReport` (or `/verify` on a fixture) | seed cache/store | go to `/dashboard` |
| `AnalysisProgress` | mount while request pending | — (reflects the in-flight `/verify`) | `isPending` | spinner; on resolve → `onDone()` |
| `/dashboard` mount | route load | read cached `DocumentReport` | react-query cache (or store) | render summary + table + cards |
| `CitationTable` / `CitationCard` | row/card click | — | local `selected` / `drawer` | open `AnalysisDrawer`, highlight in `DocumentPreview` |
| `AnalysisDrawer` | open | — | selected `Citation` | show holding / how-used / issue / action |
| `JurisdictionFilter` | change | — (client filter for now) | `analysis-store.jurisdiction` | filter list |
| `/report` | navigate | read same `DocumentReport` | cache/store | partner-ready report; `window.print()` to export |

## States

`idle` → `uploading` → `analysing` (request **pending**) → `success` (render report)
or `error` (toast via `sonner` + retry). `empty` = report has 0 citations
(show "no citations found"). Today `AnalysisProgress` is a **fake timer**
(`MESSAGES`/`TICK_MS`); it must become the real pending state of the `/verify`
mutation.

## Status mapping (backend → UI)

The UI's four statuses (`mock-citations.ts` `CitationStatus`) map from the
backend `Classification` (`app/schemas/citation.py`):

| Backend | UI status |
|---|---|
| `EXISTS_CORRECTLY_APPLIED` | `verified` |
| `EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT` | `mischar` |
| `DOESNT_EXIST` | `risk` |
| any verdict with `needs_review = true` | `review` |

`confidence` (UI 0–100 int) = `Classification.confidence * 100`. Surface
`used_semantic_fallback` (the resolver used the semantic fallback, lower
certainty) as a small badge in `AnalysisDrawer`.

## Gaps to close later (not in this commit)

1. `UploadZone.onFile` must pass the **`File`** object, not just `file.name`.
2. Add a paste-text entry on the landing page (the backend `/verify` accepts `{text}`).
3. Replace `mock-citations` imports in the dashboard/report components with the
   live `DocumentReport` (via react-query cache or the zustand store).
4. Make `AnalysisProgress` reflect the real `/verify` request instead of a timer.
5. Add a typed API client `src/lib/api.ts` + the backend↔`Citation` mapper above.
6. Dev wiring: Vite proxy `/api → http://localhost:8000` (see `routes.md`).
