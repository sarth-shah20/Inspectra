# Inspectra model and extraction card

## Current software

The default extractor is a vendor-independent generic rule pipeline with optional English syntax
coverage. The syntax model is the official `en_core_web_sm` 3.8.0, trained for general English
language analysis, not material-defect detection. When unavailable, the UI explicitly identifies
rules-only coverage. Arbitrary vendor identities and English industry identifiers are supported.

Generic rules/configurations and optional terminology packs identify evidence and assertion cues.
Contextual rules expand component coverage and explicit material phrases. Typed findings link only
unambiguous local evidence. Unknown categories and unsupported clauses require review. Neither
parsing success nor configurable terminology demonstrates generalisation accuracy.

Scores (regex/rule/contextual/NER) are fixed heuristic scores, not calibrated probabilities.
Review priorities use explicit linked report wording and are not engineering risk estimates.

## Provisional NER

`silver-ner-v1` was trained on AI-assisted labels. Its stored entity F1 is approximately 0.953 on
that provisional label process, not human-reviewed vendor reports. It is opt-in and may be absent
from a clone. Hybrid threshold policy v2 consistently filters all candidates and retains rules over
overlapping NER spans. Its provisional inclusion threshold is 0.5; no probability calibration is claimed.
`provisional_hybrid_calibration_v2.json` supersedes the earlier hybrid calibration report. Changes to
the generic contextual core mean historical provisional scores must retain their recorded scope.

## Stored source-specific classifiers

| Artifact | Task | Train / validation / test | Test macro-F1 | Weighted-F1 |
| --- | --- | ---: | ---: | ---: |
| fire-door-tfidf-v1 | Eight fire-door classes | 2,107 / 679 / 682 | 0.7833 | 0.8568 |
| faa-part-condition-tfidf-v1 | 14 FAA PartCondition labels | 56,611 / 44,663 / 42,454 | 0.7541 | 0.8420 |
| phmsa-cause-tfidf-v1 | Seven PHMSA cause labels | 2,797 / 614 / 599 | 0.6607 | 0.7887 |

These existing results were not retrained or re-evaluated during dashboard completion. Fire door
uses word/character TF-IDF and Logistic Regression selected on validation data. FAA/PHMSA use
source-specific word TF-IDF baselines. Structured target fields remain excluded from narrative inputs.
Their frozen source/split/checksum provenance remains in individual artifact reports.

They require explicitly selecting a compatible taxonomy and do not classify arbitrary industries,
rank vendors, or establish entity extraction, calibration, transfer, or engineering-risk accuracy.

## Human validation status

**Pending.** No representative, privacy-reviewed, independently double-annotated and adjudicated
vendor-report gold set was supplied for this implementation. The new workflow supports validation
without claiming it has occurred. Training selects fixed 10/20-epoch candidates only on validation
partitions; test evaluation is separate. Fixed labels count unsupported test labels as misses.

Required measurements: entity/relationship/assertion precision and recall, per-vendor/template/
industry/time transfer, review routing, parser failures, processing time and error analysis.
Source permissions/codebooks, human privacy review, broader paraphrase checks, and sufficient
independent evaluation groups remain prerequisites. See `generalisation_workflow.md`.
