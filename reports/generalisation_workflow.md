# Generalisation validation workflow

Software support for unrestricted English vendor reports is implemented. Actual performance
across unseen vendors, templates, industries, and dates remains unmeasured until representative
privacy-reviewed reports have two independent annotations and adjudication.

## Prepare candidates

Run from the project environment. Put approved library record IDs (one per line) in an external
text file after privacy review. Export a fresh, blinded candidate batch:

```bash
python scripts/generalisation.py batch --database data/local/inspectra.sqlite3 --approved-ids approved_ids.txt --output data/annotations/vendor_candidates_v1.jsonl
```

Each JSONL row has `record` (canonical evidence and report metadata), `entities`, `findings`,
`review_candidates`, `privacy_reviewed`, `group_id`, and annotation provenance. Model predictions
are removed. Independently annotate before adjudication; save human versions separately.
Final rows require `annotation_source: human`, `annotation_status: adjudicated`, two distinct
`annotator_ids`, `adjudicator_id`, and `annotation_version`. Use Entity schema fields, human
extraction method, and evidence offsets into `record.display_text`. Every defect must have a
Finding entry, including findings explicitly left unlinked. Single app corrections are not gold.

## Freeze experiments

Choose holdouts before reviewing model outputs. Prepare separate immutable manifests:

```bash
python scripts/generalisation.py split --input data/annotations/vendor_gold_v1.jsonl --mode vendor --holdout "unseen supplier" --output data/annotations/vendor_manifest_v1.json
python scripts/generalisation.py split --input data/annotations/vendor_gold_v1.jsonl --mode industry --holdout textile --output data/annotations/industry_manifest_v1.json
python scripts/generalisation.py split --input data/annotations/vendor_gold_v1.jsonl --mode temporal --train-end 2025-12-31 --validation-end 2026-06-30 --output data/annotations/temporal_manifest_v1.json
```

`--mode template --holdout <template_id>` holds out templates listed in candidate batches.
`--mode grouped` provides a grouped baseline. Report/event families, normalized numeric
text templates, and conservative token overlap stay together. Vendor splits additionally
group vendor identities. Cross-period groups are quarantined. These heuristics do not replace
manual checks for paraphrases and report templates. Small batches may not support all three
partitions; collect more independent groups rather than weakening leakage checks.

## Train and evaluate

```bash
python scripts/generalisation.py train --input data/annotations/vendor_gold_v1.jsonl --manifest data/annotations/vendor_manifest_v1.json --model models/vendor-gold-v1 --report reports/vendor_training_v1.json
python scripts/generalisation.py evaluate --input data/annotations/vendor_gold_v1.jsonl --manifest data/annotations/vendor_manifest_v1.json --model models/vendor-gold-v1 --output reports/vendor_evaluation_v1.json
```

Training fixes the complete label set and selects 10/20 epochs only on validation data.
It never scores test data. Evaluation verifies annotation/manifests and rejects model
training/selection IDs overlapping test IDs. Omitting `--model` evaluates rules/contextual
coverage and explicitly records NER/hybrid as unavailable. Models without training lineage
are flagged unverified, never treated as proof of isolation.

Outputs include entity and per-label precision/recall/F1, joint assertion performance,
assertion confusion, relationship performance, missed-defect review routing, per-vendor/
industry/template/year slices, processing times, failures, and perturbation checks.
Test-only labels remain in denominators. Version output filenames and do not tune on test errors.
The Model quality page can display these versioned reports.

## Parser coverage

Create a JSON manifest of `{ "path": "...", "privacy_reviewed": true, "settings": {...} }`
entries, using parser keyword arguments in `settings`. Run:

```bash
python scripts/generalisation.py parsers --manifest parser_manifest.json --output reports/parser_benchmark_v1.json
```

Include supported layouts and expected rejections; outputs record timing and errors by format,
without exporting narrative text. Synthetic tests verify machinery only, never accuracy claims.
