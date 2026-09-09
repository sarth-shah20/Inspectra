# Inspectra

Inspectra is a domain-adaptive text mining project for construction/fire-door inspections,
aviation service difficulties, and pipeline incident narratives. The implementation follows
`PROJECT_IMPLEMENTATION_PLAN.md`. The current implementation provides source ingestion, document uploads, a configurable
regex/spaCy EntityRuler baseline, and a source-specific fire-door classifier. Statistical NER remains pending.

## Run locally

Python 3.11+ is required (tested with Python 3.12).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/python scripts/audit_sources.py
.venv/bin/python scripts/prepare_data.py
.venv/bin/python scripts/run_rules.py
.venv/bin/python scripts/train_fire_door.py
.venv/bin/streamlit run app/streamlit_app.py
```

Downloaded files belong under `data/raw/`, which remains immutable and ignored by Git.
The pilot command reads at most 250 rows from each source file. It writes local JSONL,
Parquet, and an audit manifest under `data/processed/pilot/`. These outputs are ignored by
Git and require human privacy review before sharing. Parquet contains searchable scalar
columns plus a `record_json` column with the complete canonical record.

The audit command scans the whole corpus and writes only aggregate counts, source column
names, and SHA-256 checksums to `reports/source_audit.json`. It does not export narratives.

## Generalization by design

- Source adapters populate one shared Pydantic contract. Structured categories remain
  separate from narrative model input; source categories are not token-level gold labels.
- PHMSA current and legacy schemas have separate mappings. Event versions and exact
  normalized duplicate narratives form connected groups before split assignment.
- Deterministic grouped splits use a fixed seed. Original fire-door split names remain
  metadata; pilot splits deliberately replace them to prevent exact-duplicate leakage.
- Run `scripts/prepare_data.py --held-out-domain pipeline --output data/processed/holdout-pipeline`
  to reserve pipeline groups for testing. Repeat for construction or aviation. Connected
  duplicates from other domains also move to test to prevent contamination.
- Split assignments are reproducible for a fixed corpus. Freeze the manifest before any
  experiment: adding records that bridge groups can change assignments.
- No extraction result is assumed to be mapped. Records start as `review_required`.

The first-N pilot validates plumbing only: it is not stratified or representative. Near
unique wording, report templates, vendor grouping, temporal holdouts, adapter ablation, and
abstention accuracy still need dedicated evaluation. Do not report the pilot as evidence
of generalization or use its test rows to tune dictionaries.

## Data and limitations

See [source provenance](data/SOURCES.md) and [progress](reports/progress.md).
The local fire-door files have **three English columns**, unlike the five-column description
in the plan. Both variants are supported. PHMSA text uses explicit Windows-1252 decoding.
FAA CSV uses UTF-8 with optional BOM. Empty narratives are retained with an exclusion reason;
future training code must filter them out.

Raw narrative text remains in the original files rather than being copied into exports.
Model and display text share the same normalized, redacted string so future evidence offsets
refer to the displayed text. Pattern-based privacy redaction is incomplete and can over-redact;
all records carry `privacy_review=pending`. Source identifiers remain local for traceability.

Learned classification/NER models, human annotations, and dashboard analytics are pending. No OCR, universal accuracy claim, certified
engineering risk assessment, or vendor safety ranking is provided.


## Extract a document

Open Streamlit, choose General or a domain, and upload PDF, DOCX, CSV, XLSX, TSV/TXT,
or paste a narrative. For tables, specify the exact narrative column; all other columns
are excluded from extraction. Enable the tabular-TXT option for PHMSA-style files and
select `cp1252` for those downloaded files. Click **Extract evidence**, inspect the spans
and assertions, and export CSV/JSON. Changing input or domain clears previous results.

PDF parsing creates one record per page and rejects any page without extractable text
(including blank pages); mixed scanned/text files are not silently truncated. DOCX
paragraphs and simple tables are read in body order. XLSX uses the first worksheet.
Uploads are limited to 20 MiB and tables to 10,000 rows. Complex layouts and nested tables
are not guaranteed. Source-specific dataset ingestion remains a separate CLI path.

The packaged YAML files under `src/inspection_nlp/configs/` separate shared concepts from
construction, aviation, and pipeline terminology. General mode does not infer a domain.
The baseline emits measurements, ISO-shaped dates, configured vocabulary, and local
assertion cues. It does not yet cover every canonical entity label. Confidence numbers
are fixed rule scores, not calibrated probabilities. Severity is extracted from explicit
words only; no review-priority score is computed.

Every matched defect remains `review_required`; no defect match produces `unmapped`.
This conservative routing is not a validated abstention classifier. Assertion cues use
bounded clause context and can fail on complex coordination or distant corrective actions.
CSV contains one row per entity (or a blank entity row for unmatched records), while JSON
retains canonical provenance and source metadata. HTML evidence is escaped before rendering.

`run_rules.py` runs generic/domain ablation on the local pilot and writes local canonical
outputs to `data/processed/rules/`. The aggregate `reports/rules_smoke.json` proves processing
coverage only. Do not interpret match-count increases as improvements in accuracy. No
rules were tuned on pilot test narratives and no gold evaluation has been performed.

## Fire-door classification baseline

`scripts/train_fire_door.py` trains a word/character TF-IDF plus multinomial logistic
regression model for the eight supplied fire-door document classes. It trains on the
duplicate-safe supplied training partition, selects six fixed hyperparameter candidates
using validation macro-F1, and evaluates the supplied duplicate-safe test partition once.
The saved local artifact is `models/fire-door-tfidf-v1/model.joblib`; its reproducibility
metadata sits beside it. The report records all validation candidates and test predictions.

The completed `fire-door-tfidf-v1` run selected `C=3.0` with balanced class weights. Its
sealed duplicate-safe test score is macro-F1 **0.7833** and weighted-F1 **0.8568** across
682 records. It used 2,107 training and 679 validation records. These results apply only
to this source taxonomy and split: they are not entity-extraction, calibration, domain-transfer,
or engineering-risk performance. The dashboard exposes this classifier only under Construction;
its raw score is not a calibrated probability and unfamiliar terminology still requires review.

## FAA and PHMSA source baselines

`scripts/train_source_baseline.py faa` and `scripts/train_source_baseline.py phmsa` train
separate word-TF-IDF (1–2 gram) Logistic Regression baselines. They use `clean_text` only:
FAA uses `Discrepancy` and PHMSA uses `NARRATIVE`; neither source target field is included in
the text. Each task has a controlled label list selected from training/validation support before
testing, a single fixed `C=1`, balanced-class configuration, and one representative per consistent
duplicate/event group.

The completed FAA experiment covers 14 PartCondition labels, uses the temporal split through 2023
for training, 2024 validation, and 2025 testing. It scored macro-F1 **0.7541** and weighted-F1
**0.8420** on 42,454 test representatives (56,611 train; 44,663 validation). The PHMSA experiment
covers seven common cause classes under the grouped split and scored macro-F1 **0.6607** and
weighted-F1 **0.7887** on 599 test representatives (2,797 train; 614 validation).

These are source-specific, source-provided document labels. They are not comparable label spaces,
do not evaluate extracted entity spans, and do not establish cross-domain performance, calibrated
confidence, serviceability, or engineering risk. Post-run metric recomputation was used only to
verify saved artifacts; it did not alter labels, features, parameters, or thresholds.

## Annotation pilot

The annotation policy is in `reports/annotation_guide.md`. It defines explicit evidence spans,
assertion attributes, difficult cases, a two-annotator calibration subset, and agreement reporting.
`scripts/export_annotation_batch.py` deterministically samples near-equal source-label strata from
the frozen, training-eligible groups. It deliberately refuses to export narrative text until a
separate file of privacy-reviewed record IDs is supplied:

```bash
.venv/bin/python scripts/export_annotation_batch.py \
  --privacy-reviewed-record-ids data/annotations/privacy_reviewed_ids.txt
```

That review file is intentionally not created by the pipeline. Candidate text must be reviewed by
an authorized person before annotation. Exported candidates are marked `source_candidate`, never
gold; keep them separate from corrected annotations and model predictions.

After completed or adjudicated human labels are available, import them without overwriting an
existing artifact:

```bash
.venv/bin/python scripts/import_annotations.py --input data/annotations/adjudicated.jsonl
```

The importer validates evidence text, strict spaCy token boundaries, and non-overlapping spans.
It writes `gold.spacy` for NER and a separate assertion/provenance sidecar. It rejects incomplete
or automated annotations; source labels and rule predictions cannot silently become gold spans.

## Dashboard review and analytics

After extraction, the dashboard shows editable entity rows, validates their evidence spans, and
saves a human-reviewed replacement set to `data/annotations/reviews.jsonl`. It does not modify
raw data, processed records, automated output, or source labels. Corrected entities are marked
with `extraction_method=human` and confidence 1.0 to represent provenance, not calibration.

The same page summarizes entity counts, review-required/unmapped records for the current input,
and the saved source-classification test metrics. These charts describe uploaded/extracted text;
they do not imply a safety rate, vendor ranking, population rate, or engineering-risk estimate.

## Full-corpus preparation and frozen experiments

```bash
.venv/bin/python scripts/prepare_corpus.py
.venv/bin/python scripts/verify_corpus.py
```

The full-corpus command streams every supported local source through the cleaning adapters,
indexes metadata in SQLite, and writes `data/processed/corpus-v1/`. It refuses to overwrite
an existing snapshot. A failed/interrupted directory has no frozen manifest; use a new
`--output` path for a new run. The immutable raw files remain the source of unredacted text.

Outputs:

- `cleaned.jsonl` and `cleaned.parquet`: all canonical source records, including excluded
  records with explicit reasons. `split` is deliberately unset because assignments vary
  by experiment. Join by `record_id` to the frozen assignment table.
- `assignments.parquet`: connected group ID, grouped split, FAA temporal split, original
  fire-door split, safe fire-door split, three held-out-domain splits, sample membership,
  and exclusion reason. Treat `excluded`, `quarantine`, `demo`, and `not_applicable` as
  ineligible for train/validation/test in that experiment.
- `training_sample.jsonl`: separate source-specific experiment candidates, each marked
  `split=train` with its experiment in metadata. Filter by `domain` and `experiment`;
  **do not concatenate these into a shared NER training set**. Source labels are not gold
  span annotations. FAA selection is capped at 75,000 representatives by default.
- `quality_report.json`: length, label, redaction, duplicate, split, and sample distributions.
- `manifest.json`: frozen status, raw checksums, output checksums, seed, and policy version.
- `index.sqlite`: local metadata index for diagnostics, not an approved public export.

Policy `corpus-v1` differs intentionally from the old plumbing pilot:

1. Connected groups link event IDs, exact normalized text, and conservative template keys.
   Template keys ignore punctuation/case and mask numeric slots in narratives with at least
   eight tokens. This can overgroup examples and does not catch arbitrary paraphrases or
   word substitutions. No threshold is learned from test labels.
2. General grouped splits use 70/15/15 proportions by deterministic group hash. Actual
   row proportions depend on group sizes. Partial FAA 2026 rows remain demo-only.
3. FAA temporal evaluation uses annual source-file year: through 2023 for training,
   2024 for validation, complete 2025 for testing, and 2026 for demos. Groups that span
   these periods are quarantined from this experiment. File year is reporting year,
   not necessarily the incident's `DifficultyDate` year.
4. Fire-door official assignments are preserved unchanged in their own column. Connected
   groups appearing in multiple supplied splits are quarantined in the safe variant;
   the remaining records retain their original assignments. Report this exclusion when
   comparing classifier metrics with published results.
5. Each held-out-domain assignment sends connected groups containing that domain to test;
   other groups go to train/validation. These are separate experiments, not interchangeable
   with source-specific classification splits. Partial-year/empty rows stay ineligible.
6. Supervised training selection excludes missing targets and groups with conflicting
   source labels. It uses one deterministic representative per group/domain. FAA candidates
   are sampled proportionally across condition/year strata using a fixed hash and
   largest-remainder quotas; this is not class balancing and very rare strata may be omitted.

Automated cleaning does not establish that text is anonymous or correctly labelled. Privacy
review, source terms, vendor holdouts, broader near-duplicate analysis, preferred final/latest
PHMSA selection, and human-verified gold spans remain necessary before final evaluation.
Do not tune rules on any frozen test text or use the old plumbing pilot for reported metrics.
