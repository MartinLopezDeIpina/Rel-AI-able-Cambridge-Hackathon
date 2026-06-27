# Offene Punkte / Noch zu finalisieren

## Web-Fallback via Perplexity-Agent  — STATUS: GERUEST, NICHT FINALISIERT

**Zweck.** Wenn ein (indirektes) Zitat lokal nicht aufgeloest werden kann — d. h. die
Quelle ist **nicht im PDF-Korpus** enthalten **und** es gibt **keinen
aussagekraeftigen semantischen Absatz-Treffer** —, soll asynchron ein
Perplexity-Online-Agent die Quelle im Web suchen. Typischer Fall: aeltere Werke
oder unvollstaendige Scans.

**Trigger (in `resolve_citations.py`).** `needs_web = (name_score < NAME_THRESHOLD=75)
and (semantic_score < SEM_UNCERTAIN=0.5)`. Aktivierung nur mit `--web-fallback`.

**Eingabe.** Die 12 Zitate liegen in `citations.txt` (ein Zitat pro Zeile). Standardpfad
ist bereits verdrahtet. **`citations.txt`-Format wird noch finalisiert.**

**Schon implementiert (`web_fallback.py`).**
- Metadaten-Extraktion aus dem Zitat: Fallname (`X v Y`), Jahr, neutral citation
  (z. B. `[1975] UKHL 1`), Gerichts-/Reporter-Kuerzel.
- Prompt-Bau aus den Metadaten (Hinweise fuer den Agenten).
- Asynchroner, nebenlaeufiger Aufruf (`asyncio` + `requests` in Threads), mehrere
  offene Zitate parallel; Concurrency-Limit.
- Sicherer No-Op ohne `PERPLEXITY_API_KEY`.
- Anbindung in `resolve_citations.py` (`--web-fallback`, `--pplx-model`), Ergebnis
  wird je Zitat unter `web_fallback` an die JSON-Ausgabe gehaengt.

**Noch zu finalisieren — TODO.**
- [ ] **Trigger kalibrieren.** `SEM_UNCERTAIN` (Default 0.5) ist korpusabhaengig:
      bge-small liefert fuer fachlich aehnliche Rechtstexte hohe Basis-Kosinuswerte
      (~0.6–0.75 auch ohne echten Treffer), d. h. 0.5 feuert in der Praxis selten.
      Am echten Korpus + echten 12 Zitaten kalibrieren (per `--sem-uncertain` /
      `--name-threshold` einstellbar). Evtl. besseres "kein Treffer"-Signal:
      relativer Abstand Top-1 vs. Top-2 statt absoluter Schwelle.
- [ ] Perplexity-Zugang: `export PERPLEXITY_API_KEY="pplx-..."`.
- [ ] Endpunkt/Modus bestaetigen: synchron `POST /chat/completions` (aktuell) vs.
      Async-Job-API `POST /async/chat/completions` + Polling. Ggf. konkreten
      Perplexity-**Agent** statt Sonar-Modell waehlen.
- [ ] Modellwahl: `sonar-pro` (Default) vs. `sonar-reasoning-pro` / `sonar-deep-research`.
- [ ] `search_domain_filter` auf Rechtsquellen setzen (bailii.org,
      caselaw.nationalarchives.gov.uk, legislation.gov.uk, offizielle Law Reports).
- [ ] Response-/Agent-Ausgabe-Schema mit der echten API verifizieren
      (`choices[].message.content`, `citations`/`search_results`) und sauber parsen.
- [ ] Entscheiden, wie das Web-Ergebnis verwertet wird: nur als Kandidat anzeigen,
      oder Dokument automatisch abrufen + in den Korpus/Index aufnehmen.
- [ ] Rate-Limiting, Kosten und Caching der Web-Antworten.
- [ ] `citations.txt`-Format final festlegen und Metadatenfelder darauf abstimmen.

**Aufruf (sobald Key gesetzt).**
```bash
export PERPLEXITY_API_KEY="pplx-..."
python resolve_citations.py --index index --citations citations.txt --web-fallback --out results.json
```

## Sonstiges
- [ ] Vollstaendigen Index ueber `pdfs/` fertig bauen (laeuft im Hintergrund; 16 Scans
      = ~522 OCR-Seiten). Danach `resolve_citations.py` gegen den echten Index testen.
- [ ] `NAME_THRESHOLD` / Chunking am echten 12-Zitate-Input nachjustieren, sobald dessen
      Format bekannt ist.
