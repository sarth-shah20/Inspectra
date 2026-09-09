# Implementation progress

## Current status

The data foundation and rules dashboard are implemented. Full-corpus automated cleaning,
duplicate/template grouping, frozen experiment assignments, and source-specific training
sampling are now implemented. See `reports/data_readiness.md` for measured counts and
remaining readiness gates. Earlier milestone sections below are historical snapshots.


## First milestone — 2026-09-09

- [x] Package scaffold, reproducible dependency snapshot, lint/test commands, Streamlit shell.
- [x] Canonical record/entity schemas with display-evidence validation.
- [x] Fire-door English/bilingual XLSX, FAA CSV, PHMSA current/legacy TXT adapters.
- [x] Explicit narrative feature allowlists, checksums, source rows, schema mappings.
- [x] First-pass privacy redaction; local outputs marked for human privacy review.
- [x] Event and exact-text connected-group splits; held-out-domain option.
- [x] Local bounded pilot exported as JSONL and Parquet.
- [x] Full-source structural/count audit command.
- [ ] Complete source licence and codebook verification (Phase 1 gate remains open).
- [ ] Full statistical audit, stratified sampling, temporal/vendor/near-duplicate safeguards.
- [ ] PDF/DOCX/generic upload adapters (Phase 2 gate remains open).
- [ ] Generic rules + configurable domain adapters, assertion handling, fire-door classifier.
- [ ] Annotation pilot, adjudication, frozen human-verified gold evaluation sets.

The dashboard is a shell with a normalization preview, not an extraction demo. No training
or accuracy evaluation has been performed. Regression examples are generated test fixtures.
The milestone does not establish domain transfer performance.

Next implementation increment: complete the remaining parsers and data-audit checks, then
build the deterministic shared extraction baseline with separate domain configurations and
assertion regression tests before any learned NER training.

## Validation results

- 15 tests pass, including the Streamlit shell and both fire-door schema variants.
- Ruff checks pass.
- Full local audit: 4,212 fire-door; 690,332 FAA; 11,307 PHMSA rows before deduplication.
- Pilot: 4,914 records (750 construction, 2,750 aviation, 1,414 pipeline).
- JSONL/Pydantic and Parquet payload round-trips verified for every pilot record.
- Event and exact-text split isolation verified across the entire pilot.
- Observed differences from the plan: fire-door files have three English columns;
  PHMSA requires Windows-1252 decoding. Both are recorded in loader schema metadata.

## Second milestone — document ingestion and deterministic extraction

- [x] PDF, DOCX, selected-column CSV/XLSX/TSV/TXT, and pasted text adapters.
- [x] Clear rejection of textless PDF pages; tests for document and table parsing.
- [x] Shared regex/spaCy EntityRuler baseline with packaged domain YAML dictionaries.
- [x] Local assertion cues for present, negated, possible, historical, and resolved evidence.
- [x] Unmapped/review routing; uncalibrated confidence identified in record metadata and UI.
- [x] Streamlit upload, preview, extraction, evidence highlighting, and CSV/JSON downloads.
- [x] Generic/domain ablation smoke test across all 4,914 pilot records.

Phase 1 licence/codebook work and the remaining Phase 2 audit/sampling checks stay open.
Phase 3 is partial: extraction is visible end to end, but the fire-door classifier and
manually verified baseline metrics remain pending. Assertion handling is heuristic,
not a learned or evaluated contextual model. Neither domain adaptation quality nor
unfamiliar-term abstention accuracy has been established.

Second-milestone validation: **38 tests passed**, Ruff checks passed, and all 4,914
extracted pilot records passed canonical schema/evidence-offset validation. Dashboard
regressions cover extraction and clearing stale results when the domain changes.
The dependency snapshot includes the installed PDF/DOCX and spaCy dependencies.


## Third milestone — full-corpus preparation and frozen assignments

- [x] Streamed all 705,851 downloaded records through cleaning and provenance adapters.
- [x] Full word-length, source-label, redaction, exclusion, and duplicate distributions.
- [x] Event/exact-text/template connected groups with 70/15/15 grouped assignments.
- [x] Supplied fire-door splits preserved; separate safe variant quarantines cross-split groups.
- [x] FAA temporal assignments: older years train, 2024 validation, 2025 test, 2026 demo-only.
- [x] Three held-out-domain assignment variants with connected-group isolation.
- [x] Deterministic training sampling: 75,000 FAA, 2,034 construction, 3,443 pipeline.
- [x] Frozen manifest and JSONL/Parquet artifacts; independent verification command.
- [x] 43 regression tests pass; Ruff checks pass.

127 unusable narratives remain traceable but are excluded from model partitions. The safe
fire-door experiment quarantines 743 records in groups crossing the supplied splits.
These are data-quality findings, not model performance results.

The full corpus was cleaned once. An interrupted export was regenerated from the validated,
completed SQLite index; raw ingestion and split selection were retained. No frozen manifest
existed at interruption, and finalization refuses to rewrite an already-frozen snapshot.
Sampling queries now precompute label-conflict groups and index condition/year strata.

Pending: human privacy review, source terms/codebooks, broader near-duplicate and vendor
holdout analysis, latest/final PHMSA selection, gold annotations, and trained baselines.

Final third-milestone verification passed across all 705,851 canonical records and 80,477
training samples, including raw/artifact checksums, assignment policies, group isolation,
and complete JSONL/Parquet agreement. See `reports/corpus_verification.json`.

## Fourth milestone — fire-door classification baseline

- [x] Source-specific TF-IDF word/character Logistic Regression baseline.
- [x] Duplicate-safe supplied fire-door splits; source class never enters narrative input.
- [x] Six fixed candidate configurations selected only by validation macro-F1.
- [x] Immutable local model artifact, metadata, candidate report, and sealed test predictions.
- [x] Dashboard construction-mode document classification panel.

The selected model (`C=3.0`, balanced classes) achieved macro-F1 0.7833 and weighted-F1
0.8568 over 682 duplicate-safe test records, after selection on 679 validation records.
It trained on 2,107 records. The model reload and independent test recomputation matched
the saved report exactly. Results are source-specific classification metrics, not NER,
calibration, held-out-domain, or risk-assessment results. Statistical NER and gold entity
annotation remain pending.

## Fifth milestone — FAA and PHMSA source baselines

- [x] Controlled 14-label FAA PartCondition and seven-label PHMSA cause tasks.
- [x] Text-only source inputs with target-field exclusion and one representative per consistent group.
- [x] Fixed word-TF-IDF Logistic Regression configuration, frozen before validation/test scoring.
- [x] Temporal FAA and grouped PHMSA model artifacts, reports, and independent reload verification.

FAA test performance: macro-F1 0.7541, weighted-F1 0.8420, 42,454 test representatives.
PHMSA test performance: macro-F1 0.6607, weighted-F1 0.7887, 599 test representatives.
Both are source-specific document-classification baselines, not NER or transfer metrics.
See `reports/model_card.md` for model inputs, split policies, and limitations.

## Sixth milestone — annotation pilot groundwork

- [x] Entity label, boundary, assertion, and adjudication guide.
- [x] Deterministic per-domain/source-label candidate stratification from training-eligible groups.
- [x] Privacy gate: annotation text cannot export without an external reviewed-ID manifest.
- [ ] Human privacy review, two-annotator calibration, adjudication, and gold entity annotations.

The annotation exporter has intentionally not been run against the downloaded narratives because
no reviewed-ID manifest exists. It creates candidates only after a human authorizes their text for
the annotation workflow. This does not create gold data or entity-level metrics.

## Seventh milestone — dashboard review and analytics

- [x] Editable evidence table with offset/overlap validation.
- [x] Append-only human correction store separate from raw and automated data.
- [x] Current-input entity/review analytics and saved baseline evaluation display.
- [x] 49 tests pass, including correction and summary logic.

The dashboard currently summarizes the uploaded/extracted records only. Persistent reviewed data
is not yet imported into a versioned gold annotation set, and source-wide analytics/correction
history pages remain pending.

## Eighth milestone — annotation import readiness

- [x] Validated completed/adjudicated JSONL import to spaCy `DocBin`.
- [x] Separate assertion/provenance sidecar for spans.
- [x] Rejection of incomplete annotations, bad evidence, invalid token boundaries, and overlaps.
- [x] 51 tests pass.

No human-reviewed candidate batch or gold annotation artifact exists yet. This importer is only
infrastructure for the privacy-reviewed, double-annotated pilot.
