# Inspectra baseline model card

This card describes the completed deterministic extraction rules and source-specific document
classification baselines. It does not describe a trained NER model; no human-verified entity
training or test set exists yet.

| Experiment | Task | Train / validation / test | Test macro-F1 | Test weighted-F1 |
| --- | --- | ---: | ---: | ---: |
| `fire-door-tfidf-v1` | Eight supplied fire-door classes | 2,107 / 679 / 682 | 0.7833 | 0.8568 |
| `faa-part-condition-tfidf-v1` | 14 controlled FAA `PartCondition` labels | 56,611 / 44,663 / 42,454 | 0.7541 | 0.8420 |
| `phmsa-cause-tfidf-v1` | Seven controlled PHMSA `CAUSE` labels | 2,797 / 614 / 599 | 0.6607 | 0.7887 |

## Inputs and learning method

Fire door uses word and character TF-IDF with multinomial Logistic Regression. It chose from six
fixed configurations by validation macro-F1 and then initially evaluated the test set once. FAA
and PHMSA use word TF-IDF 1–2 grams with a fixed `C=1`, balanced-class Logistic Regression model.
FAA model text is only `Discrepancy`; PHMSA model text is only `NARRATIVE`; fire-door model text is
only source-provided English text. Structured source labels are never concatenated into model text.

The data snapshot is `corpus-v1`. Exact-event, exact-text, and conservative template duplicate
families are grouped. Fire-door uses the supplied split after quarantining groups that cross it.
FAA is year-aware: through 2023 train, 2024 validation, 2025 test, and partial 2026 demo-only.
PHMSA uses the grouped split. Every saved model records the frozen manifest checksum and class counts.

Saved-model evaluation was independently recomputed from the frozen snapshot to verify artifact
integrity. Those recomputations did not select parameters, change thresholds, or inspect errors to
modify the models.

## Intended use and limits

Use these models as transparent academic baselines and optional dashboard aids for their named
source taxonomy. They do not classify arbitrary inspection reports, determine compliance, certify
engineering risk, or rank vendors. Scores are not calibrated probabilities. An unfamiliar term or
low-confidence outcome requires review. The datasets are source-specific; comparable cross-domain
classification scores do not exist.

The rule baseline extracts a limited configured vocabulary plus measurements/dates and uses local
heuristics for negation, possibility, historical, and resolved language. Its rule scores are not
calibrated. It has no gold entity-level precision, recall, F1, transfer, or abstention result.

Remaining work: human privacy review; licences/codebooks; annotation guide and double-annotated
gold entities; statistical NER and hybrid evaluation; calibrated abstention; held-out-domain entity
evaluation; error analysis; corrections workflow; and analytics.
