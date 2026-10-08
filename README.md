# Inspectra

Inspectra is a local Streamlit dashboard for extracting and reviewing material-defect evidence
from English vendor inspection reports across industries. Vendor names and industry identifiers
are unrestricted. The generic spaCy pipeline accepts new vendors without dataset-specific code;
optional terminology packs improve coverage for specialised wording.

**Software capability and accuracy are separate.** Extraction uses rules, English syntax, and an
optional provisional NER model. Accuracy on representative unseen vendors has not been established.
Unfamiliar or ambiguous evidence remains visible for review. Review priorities are workflow aids;
the application does not certify engineering risk, compliance, or serviceability.

## Install and run

Python 3.11 or newer is required. From the cloned repository:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,english]'
streamlit run app/streamlit_app.py
```

The `english` extra installs the official pinned `en_core_web_sm` 3.8.0 syntax model.
The model provides grammar/noun-phrase analysis; it is not a trained material-defect classifier.
Without it, the application explicitly shows reduced rules-only coverage. All core analysis runs
locally without network access after dependencies/models are installed. Optional local source
classifiers and silver NER artifacts are ignored by Git and may be absent in a fresh checkout.

`requirements-lock.txt` records the original research environment plus the pinned English model
and Plotly addition. Use it when reproducing stored source-classification artifacts; broad package
ranges in `pyproject.toml` support a fresh installation of the current dashboard.

## Add reports

Upload machine-readable PDF, DOCX, TXT, CSV, TSV or XLSX, or paste English narrative text.
Files have a 20 MiB limit; tables have a 10,000-row limit. Password-protected PDFs and textless
pages are rejected with visible messages. OCR and complex-layout reconstruction are outside scope.
Batch uploads report individual failures without discarding successfully parsed reports.

Choose General for the generic workflow. Construction, Aviation and Pipeline are optional
terminology packs, not a vendor allowlist. Enter any other industry identifier if useful.

For tables, select the narrative column and optionally map vendor, report number/date, product,
batch and asset columns. Explicit column mappings work with arbitrary column names. Other columns
are not model input. Save mappings as named profiles. For document uploads/pasted text, enter
report metadata manually. Select a date format for ambiguous dates. Vendor aliases require an
explicit mapping; similar names are never automatically merged. An arbitrary organisation mention
is not sufficient to identify a vendor.

PDF pages share a report identity. Table rows are independent reports unless an explicit report
number groups them. Evidence retains paragraph/table/page structure; `clean_to_display` maps
normalised text positions to displayed evidence. Evidence is Unicode-normalised and conservatively
redacted; offsets refer to that displayed text, not the original file bytes. Pattern redaction still
requires human privacy review before external annotation or sharing.

## Dashboard pages

| Page | Purpose |
| --- | --- |
| Overview | Reports, active defects, affected reports, backlog and explicit severity |
| Report explorer | Ingestion, metadata, highlighted evidence and corrections |
| Defect analysis | Defect mentions, Pareto distribution and linked component/material heatmaps |
| Vendor comparison | Vendor mentions and affected-report rates with numerator/denominator |
| Trends | Monthly outcomes, undated-report count and reliable recurrence |
| Review queue | Priority reasons, unsupported clauses, workflow status and backlog age |
| Model quality | Artifact versions, research metrics and future human-validation results |

Shared filters apply to vendor, industry, report dates, material, component, defect, assertion and
review status. Metadata filters define the inspected-report denominator. Defect filters narrow
findings while retaining that denominator. Click supported charts to narrow their evidence tables
and finding exports. Unknown metadata and unlinked evidence remain visible.

Affected-report rate is the number of distinct reports containing **present** defect findings divided
by all filtered inspected reports for that vendor. It is not a defective-item rate or safety ranking.
Defect-frequency charts count mentions under the selected assertions, including negated/historical
mentions when those assertions are selected. Vendor reporting volume and inspection sampling differ.

Heatmaps labelled linked use evidence relationships. Report-level co-occurrence is displayed separately
and does not establish a material/component–defect association. Undated reports are excluded from
monthly charts and counted explicitly. Recurrence requires the same vendor, asset/batch, category and
a strictly earlier date in a different report; unavailable linkage does not mean no recurrence.

## Extraction and review

The generic core recognises configured defects, measurements, dates, material wording, severity,
methods and actions. English syntax adds associated component phrases beyond component dictionaries.
Explicit material cues such as “made of” can retain unfamiliar material names. Unsupported
inspection/action clauses are review candidates, not automatically confirmed defects. Explicit
no-defect statements are recorded separately from “no supported defect extracted.”

Each defect finding retains its assertion and original evidence, with conservative clause-local links.
Multiple possible associations remain unlinked/ambiguous. Categories are optional; unfamiliar defects
can remain uncategorized. Scores are heuristic inclusion scores, not calibrated correctness probabilities.

The review editor supports additions, removals, boundary changes, assertion changes and explicit
relationship corrections. Offsets must identify valid non-overlapping evidence spans. When adding or
changing defect boundaries, clear “Use edited relationships” to rebuild conservative links, then review
those links. Changes are append-only revisions; the original extraction remains available.
Workflow status (`pending`, `in_progress`, `reviewed`) is separate from textual assertion
(`present`, `possible`, `negated`, `historical`, `resolved`). App corrections alone are not gold labels.

Priority rules are versioned in `src/inspection_nlp/configs/priority.yaml`. Unresolved defects receive
high priority only from explicitly linked major/critical/severe wording or urgent corrective action.
Present/possible defects and unsupported review candidates receive normal priority; negated/historical/
resolved defects receive low priority. Disable priorities in the sidebar if unnecessary.

Provisional NER is opt-in, uses an explicit 0.5 heuristic threshold, and does not claim calibrated
confidence. Rules/contextual evidence takes precedence over overlapping NER spans. Source-specific
classifiers require explicitly selecting a compatible taxonomy; their scores do not measure generic
vendor-report extraction. Model and terminology fingerprints preserve run provenance and invalidate
caches when artifacts change.

## Optional terminology packs

Create a YAML file with a version and supported entity labels, then add its local path in the sidebar:

```yaml
version: textile-v1
entities:
  COMPONENT: [warp guide, loom spindle]
  DEFECT: [fraying, yarn slippage]
```

Pack labels use the existing canonical entity vocabulary. Terms must be strings. Packs augment the
generic pipeline and do not require application code changes. Keep evaluation test terminology sealed;
never tune dictionaries on test errors. Normalized categories live in a separate versioned configuration.

## Persistence and exports

The default library is `data/local/inspectra.sqlite3`; use `INSPECTRA_DB` to select another path.
Content hashes deduplicate identical reports, while configuration/model changes create separate runs.
Latest reviewed findings drive the default views; the Original extraction toggle exposes automated output.
Run timing does not create duplicate runs. Local databases, mappings, annotations and model artifacts
remain excluded from Git. See [local library procedures](reports/local_library.md) for backups, restore
and schema compatibility. Legacy JSONL review imports are idempotent and preserve unmatched entries.

CSV preserves the original entity columns and adds report metadata, finding links, priority reasons and
version provenance. Formula-like strings are neutralised. UI JSON uses the versioned
`inspectra-export-v2` envelope; the Python `export_json()` default retains the legacy record-list shape.
Standalone HTML escapes supplied text and includes highlighted evidence and report-rate denominators.
Exports follow the selected original/reviewed view and shared/chart finding filters. Denominator reports
with no matching finding remain in the export with empty selected findings.

## Synthetic demonstration

```bash
python scripts/import_demo.py --database /tmp/inspectra-demo.sqlite3
INSPECTRA_DB=/tmp/inspectra-demo.sqlite3 streamlit run app/streamlit_app.py
```

The [vendor demo](samples/vendor_demo/README.md) contains invented vendors and reports spanning textile,
electronics and medical-device assembly wording. It demonstrates recurrence, explicit severity, clean/
resolved/historical mentions, missing dates and unsupported terminology. It cannot establish real accuracy.
Original construction/aviation/pipeline samples remain available as additional synthetic demonstrations.

## Generalisation validation

[The validation workflow](reports/generalisation_workflow.md) provides privacy-gated blinded annotation
batches, two-annotator/adjudication checks, immutable vendor/template/industry/time manifests,
validation-only NER selection, sealed test evaluation and parser benchmarks.

Metrics include fixed-label entity precision/recall/F1, assertion errors, relationship performance,
review routing, per-group slices, processing time, parser failures and perturbation checks. Test-only
labels remain in the denominator. Conservative exact/numeric-template and token-overlap grouping
requires additional human inspection for paraphrases. Human results stay pending until suitable reports
and adjudicated annotations exist. No accuracy or generalisation result is inferred from synthetic tests.

## Verify and develop

```bash
python -m pytest -q
ruff check src scripts tests app
```

Tests isolate their databases. They cover parsers, redaction/offsets, arbitrary vendors, unavailable
models, custom packs, assertions, relationships, priority rules, recurrence, SQLite transactions,
review revisions, filtered rates/exports, every dashboard page, and gold-evaluation leakage checks.
Commit every verified implementation increment with at most two message lines and no AI attribution.

## Research provenance

The historical `corpus-v1` snapshot covers FAA SDR, fire-door and PHMSA research records. It remains
separate from uploaded reports and is not required to use the dashboard. See [dataset card](reports/dataset_card.md),
[model card](reports/model_card.md), [source register](data/SOURCES.md) and
[historical research commands](reports/research_workflows.md). Source permissions/codebooks and privacy
review remain external validation prerequisites. Older provisional hybrid/holdout reports are archived
results; use versioned replacements and never treat them as current human-validated accuracy.
