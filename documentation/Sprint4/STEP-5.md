# Step 5 — Finalisierter Citations-Report → `report.json`

**Ziel (Endresultat):** Step 5 erzeugt nach einem `/verify`-Lauf **`app/frontend/report.json`**
— den vollständigen, validierten, frontend-fertigen Verdict-Report über *alle* gefundenen
Zitate. Jedes Pflichtfeld ist befüllt (kein `null`/`""`/`[]` in Pflichtfeldern). Das Frontend
wird nachgeliefert, liest die Datei selbst (Polling) und validiert defensiv nach.
**Frontend-Code ist NICHT Teil von Step 5.**

Vorstufen M1 (Extraktion/Enrichment), M3 (Resolver), M4 (Faithfulness), M5-Orchestrator
(`pipeline_service.verdict_for` → `VerifyResponse`) existieren und sind getestet. Step 5
ergänzt **Mapping + Serialisierung + Persistenz** von `report.json`.

---

## Scope-Abgrenzung: zwei Dateien, zwei Steps

Das Frontend erwartet zwei Artefakte in `app/frontend/`:

| Datei | Inhalt | Entspricht (Frontend) | **Owner** |
|-------|--------|------------------------|-----------|
| `config.json` | Source-/Dokument-Metadaten (`name, uploadedAt, jurisdiction, practiceArea, model, steps[]`) | `MOCK_DOCUMENT` | **Step #2/#3** |
| `report.json` | Citations + Summary | `MOCK_CITATIONS` + Summary | **Step #5** |

> **`config.json` ist NICHT Step 5.** Die Metadaten stammen aus den Quelldokumenten und der
> Pipeline-Instrumentierung — daher ist **Step #2 oder #3** dafür verantwortlich, `config.json`
> nach `app/frontend/` zu schreiben. **Vorerst übersprungen** (kein Blocker für Step 5; das
> Frontend nutzt bis dahin Fallback-Mock-Metadaten). Schema-Vorschlag + Feld-Ownership stehen
> unten im Anhang, damit Step 2/3 das später aufgreifen kann.

---

## Datenfluss (Step 5)

```
PDF / Text
  ├─ M1  extract_enriched_citations            -> list[EnrichedCitation]
  ├─ M3  resolver.resolve  (pro Cite)
  ├─ M4  distortion_service.analyze (pro Cite)
  ├─ M5  pipeline_service.verdict_for           -> CitationVerdict
  │
  ├─ 5.1 zip(EnrichedCitation, CitationVerdict) -> ReportCitation   (Mapping)
  ├─ 5.2 ReportDocument                          (Pydantic, extra="forbid")
  └─ 5.3 atomar schreiben -> app/frontend/report.json
```

`CitationVerdict` allein trägt **nicht** `year`/`court`/`paragraph` — diese kommen aus der
`EnrichedCitation`. Daher behält `verify_enriched` das Enriched-Objekt **neben** dem Verdict
(parallele Liste), damit 5.1 mappen kann.

---

## Schritte

### 5.1 — Mapping `(EnrichedCitation, CitationVerdict)` → `ReportCitation`
Reines Daten-Mapping, keine I/O.

**Status-Mapping** (Backend 3-wertig + `needs_review`  →  Frontend 4-wertig):

| `CitationVerdict.status`                        | `needs_review` | → `status` |
|-------------------------------------------------|:--------------:|------------|
| `DOESNT_EXIST`                                  | (egal)         | `risk`     |
| `EXISTS_MISCHARACTERISED_TAKEN_OUT_OF_CONTEXT`  | (egal)         | `mischar`  |
| `EXISTS_CORRECTLY_APPLIED`                      | `True`         | `review`   |
| `EXISTS_CORRECTLY_APPLIED`                      | `False`        | `verified` |

> `needs_review` stuft nur `verified → review` herab; `mischar`/`risk` bleiben.

**Feld-Mapping** (Quelle → `ReportCitation`):

| Feld            | Typ  | Quelle / Regel |
|-----------------|------|----------------|
| `id`            | str  | `f"c{verdict.id}"` (Regex `^c\d+$`) |
| `caseName`      | str  | `verdict.citation_name` |
| `court`         | str  | `enriched.court_name or enriched.court or "Unknown court"` |
| `year`          | int  | `enriched.year` |
| `citation`      | str  | `verdict.raw` |
| `status`        | enum | s. Status-Mapping |
| `confidence`    | int  | `round(verdict.confidence_score * 100)`, clamp `[0,100]` |
| `holding`       | str  | `verdict.actual_holding` → Fallback bei `risk`: status-Default |
| `howUsed`       | str  | `verdict.associate_claim` → Fallback `enriched.proposition` |
| `reasoning`     | str  | `verdict.explanation` → Fallback bei `verified`: status-Default |
| `summary`       | str  | 1. Satz von `holding`, sonst status-Default |
| `recommendation`| str  | status-Default |
| `issue`         | str  | status-Default |
| `action`        | str  | status-Default |
| `ground`        | str  | `enriched.ground or "Unassigned"` |
| `paragraph`     | int  | 0-basierter Index in Dokumentreihenfolge (`verdict.id - 1`) |
| `supporting`    | str? | optional; weglassen wenn unbekannt |

**Pflicht-Defaults je Status** (Modell *komplett* befüllt — kein Pflichtfeld leer):

| status     | `issue`                          | `action`             | `recommendation` |
|------------|----------------------------------|----------------------|------------------|
| `verified` | `"None"`                         | `"Retain"`           | `"No action required."` |
| `review`   | `"Minor contextual inaccuracy"`  | `"Review paragraph"` | `"Confirm the characterisation before filing."` |
| `mischar`  | `"Authority mischaracterised"`   | `"Revise paragraph"` | `"Reformulate to match the actual holding."` |
| `risk`     | `"Authority cannot be verified"` | `"Remove / verify"`  | `"Remove the citation or verify against a database."` |

LLM-Werte (`explanation`, `actual_holding`) haben Vorrang vor dem Default.

### 5.2 — Validierung gegen Schema
Neue Modelle in `app/schemas/report.py` (`model_config = ConfigDict(extra="forbid")`):

```python
class ReportCitation(BaseModel):        # ein Element von report.json.citations
    id: str                             # ^c\d+$
    caseName: str
    court: str
    year: int
    citation: str
    status: Literal["verified", "review", "mischar", "risk"]
    confidence: int                     # 0..100
    summary: str
    holding: str
    howUsed: str
    reasoning: str
    recommendation: str
    issue: str
    action: str
    ground: str
    paragraph: int
    supporting: str | None = None

class ReportDocument(BaseModel):        # -> report.json
    status: Literal["pending", "complete"]   # Polling-Signal; Backend schreibt "complete"
    generated_at: str                   # ISO-8601 UTC
    summary: dict[str, int]             # verified/review/mischar/risk/total
    citations: list[ReportCitation]     # darf NUR bei status=="pending" leer sein
```

`ReportDocument.model_validate(...)` muss fehlerfrei konstruieren; sonst wird **nicht**
geschrieben (fail-loud).

**Frontend-Validierungsvertrag (von der Frontend-AI vorgegeben).** Das Frontend prüft
defensiv nur eine Teilmenge; das Backend liefert die volle (Super-)Menge:
- Top-Level: `status ∈ {"pending","complete"}`; `citations` ist Array (bei `pending` leer erlaubt).
- Pro Citation **7 Pflichtfelder** (non-empty): `id, caseName, court, year, citation, status, confidence`.
- „Fehlend" = `null` / `undefined` / `""` / `[]`. **Wichtig:** `confidence == 0` ist
  **nicht** fehlend (gültig für `risk`/FABRICATED) — muss als Zahl `0`, nie als `""` raus.
- Die übrigen Felder (`summary, holding, howUsed, reasoning, recommendation, issue,
  action, ground, paragraph`) sind frontseitig **nicht** pflicht, werden vom Backend aber
  trotzdem vollständig befüllt (Akzeptanzkriterium 4) — die UI rendert sie.

### 5.3 — Atomare Persistenz
In Temp-Datei im Zielverzeichnis serialisieren (`json.dumps(..., ensure_ascii=False, indent=2)`),
dann `os.replace(tmp, target)` → atomarer Rename, damit das pollende Frontend nie ein Fragment
liest. Pfad konfigurierbar in `app/core/config.py` (`REPORT_OUTPUT_PATH`).

> **Ablageort — wichtig (zu bestätigen):** Das Frontend (Vite) fetcht `/report.json`,
> wird also aus **`app/frontend/public/`** ausgeliefert. Default daher
> **`app/frontend/public/report.json`** (nicht `app/frontend/report.json`). Siehe
> Intermediary-Check #1.

**Pending-Platzhalter — NICHT nötig (vom Frontend bestätigt).** Das Frontend behandelt eine
fehlende `report.json` (HTTP 404 / Netzwerkfehler) selbst als „noch nicht fertig" und pollt
weiter, ohne Validierungsfehler. Der atomare Write beim Abschluss reicht also. Das Backend
schreibt immer `status: "complete"`; ein `pending`-File ist optional und standardmäßig aus.

**Edge-Case Zero-Citations — ENTSCHIEDEN.** Findet die Extraktion **0 Zitate**, schreibt das
Backend trotzdem den normalen Report (`status: "complete"`, `citations: []`) — **kein**
Sonderfall backend-seitig. Das **Frontend** behandelt `status=="complete"` **&&**
`citations.length===0` als **Validierungsfehler** und zeigt eine sichtbare Fehlermeldung
(nicht nur einen Log-Eintrag). Damit unterscheidet sich „läuft noch" (404, kein Fehler) klar
von „fertig, aber leer" (sichtbarer Fehler). Frontend-Spec: `validateReport` → `valid:false`,
`missing:["citations (empty while complete)"]`; UI rendert eine Error-Message.

### 5.4 — Verdrahtung
`POST /api/citations/verify` baut `VerifyResponse` wie bisher (API-Contract unverändert),
ruft danach `pipeline_service.write_report(verify_response, enriched)` → schreibt
`report.json`. Persistenz ist Seiteneffekt; Schreibfehler werden geloggt, Validierungsfehler
brechen ab (inkonsistenter Report).

---

## Akzeptanzkriterien (für „Annahme")

1. **Datei existiert:** Nach `/verify` liegt `report.json` am `REPORT_OUTPUT_PATH`
   (Default `app/frontend/public/report.json`) vor, valides UTF-8-JSON.
2. **Schema-konform:** `ReportDocument.model_validate_json(file)` läuft fehlerfrei; `extra="forbid"`.
   Top-Level `status == "complete"` bei abgeschlossenem Lauf.
3. **Vollzählig:** `len(citations) == Anzahl extrahierter Zitate` (Szenario: **12**); `id` eindeutig;
   `citations` ist non-empty (außer im optionalen Pending-Platzhalter).
3b. **Frontend-Pflichtfelder:** in **jeder** Citation sind `id, caseName, court, year, citation,
   status, confidence` non-empty nach `isMissing`-Regel (`""`/`null`/`[]` = fehlend; `0` ist OK);
   `confidence` ist eine **Zahl** (auch bei `risk`: `0`, nie `""`).
4. **Komplett befüllt:** jede Citation hat alle Pflichtfelder gesetzt & nicht leer
   (`""`/`null`/`[]` zählen als fehlend; nur `supporting` optional).
5. **Wertebereiche:** `status ∈ {verified,review,mischar,risk}`; `confidence ∈ [0,100]` int;
   `year` int; `id` matcht `^c\d+$`; `paragraph ≥ 0`.
6. **Status-Mapping** durch Tests abgedeckt (insb. `DOESNT_EXIST→risk` mit `confidence==0`;
   `EXISTS_CORRECTLY_APPLIED+needs_review→review`).
7. **Summary konsistent:** `summary.total == len(citations)` und `verified+review+mischar+risk == total`.
8. **Atomar:** Temp + `os.replace`; Leser sieht alt **oder** vollständig neu.
9. **Reproduzierbar:** erneuter Lauf überschreibt sauber; `generated_at` gültiges ISO-8601 (UTC).
10. **Getestet:** Unit-Test serialisiert eine gemischte Verdict-Liste (alle 4 Status) →
    validiert das geschriebene `report.json` gegen `ReportDocument` und prüft 3–7.

**Out of scope:** `config.json` (→ Step #2/#3), Frontend-Rendering, Polling, `config-validator.ts`,
`validation_results.log`, Upload-UI, Styling.

---

## Offene Code-Änderungen (Step 5 — Implementierungs-Checkliste)

- [ ] `app/schemas/report.py` — `ReportCitation`, `ReportDocument` (`extra="forbid"`).
- [ ] `pipeline_service`: `verify_enriched` behält `EnrichedCitation` neben Verdict (parallele Liste).
- [ ] `pipeline_service.to_report(verify_response, enriched) -> ReportDocument` (Mapping 5.1).
- [ ] `pipeline_service.write_report(...)` — atomar nach `REPORT_OUTPUT_PATH`.
- [ ] `app/core/config.py` — `REPORT_OUTPUT_PATH` (Default `app/frontend/public/report.json`),
      optional `EMIT_PENDING_REPORT` (Default aus).
- [ ] `api/endpoints/citations.py` — `write_report(...)` nach dem Build aufrufen.
- [ ] `tests/test_step5_report.py` — Akzeptanzkriterien 1–10 als `pytest.mark.unit`.
- [ ] `tests/contracts.py` — `assert_report_document(...)` + `Step5ReportCase`-Enum.

---

## Anhang — `config.json` (Verantwortung Step #2/#3, vorerst übersprungen)

Nicht Teil von Step 5. Hier nur dokumentiert, damit Step 2/3 es später aufgreifen kann.
**Step #2 oder #3 ist dafür verantwortlich, `app/frontend/public/config.json` zu schreiben**
(Vite-`public/`, vom Frontend als `/config.json` gefetcht). Vorerst übersprungen → Frontend
fällt initial auf `MOCK_DOCUMENT` zurück.

Frontend-fertiges Shape (= `MOCK_DOCUMENT`):

```python
class RunStep(BaseModel):
    t: str                 # ISO-8601
    label: str

class ReportConfig(BaseModel):          # -> config.json
    name: str                           # Quelldokument-/Brief-Dateiname
    uploadedAt: str                     # ISO-8601 UTC
    jurisdiction: str                   # Backend-Default; Frontend-User-Auswahl gewinnt beim Rendern
    practiceArea: str                   # Config-Default ("Commercial Litigation")
    model: str                          # Config-Konstante ("rel{AI}able Verifier v2.4")
    steps: list[RunStep]                # len >= 1; echte Pipeline-Stage-Timestamps
```

**Feld-Ownership (abgestimmt mit Frontend-AI):**

| Feld | Owner | Quelle |
|------|-------|--------|
| `name`, `uploadedAt`, `steps[]` | Backend (Step 2/3) | Dokument-Metadaten + Stage-Timestamps |
| `practiceArea`, `model`         | Backend (Step 2/3) | Config-Defaults/-Konstanten |
| `jurisdiction`                  | **Frontend** (User-Auswahl) | Backend schreibt nur Default, damit `config.json` standalone validiert |

**Hinweis an die Frontend-AI** (komplementäre Client-Validierung, ergänzt die Backend-Garantie):
- **Variante A** (In-Memory-Puffer + „Download `validation_results.log`"-Button). B/C ungeeignet.
- **`""` zählt als fehlend** (wie `null`/`undefined`/`[]`) — deckungsgleich mit Step-5-Kriterium 4.
- `config.json` und `report.json` **getrennt** validieren (zwei Schemata).
