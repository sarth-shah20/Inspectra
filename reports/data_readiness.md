# Full-corpus data readiness

Automated preparation covers all **705,851** local source records. This is a cleaned local
research snapshot, not a human-reviewed gold dataset or an approved public release.

| Source | Cleaned records | Selected training representatives |
| --- | ---: | ---: |
| FAA SDR | 690,332 | 75,000 |
| Fire door | 4,212 | 2,034 |
| PHMSA | 11,307 | 3,443 |

Training representatives belong to separate source-specific experiments. FAA uses the
older-year temporal training partition, fire door uses the safe supplied training split,
and PHMSA uses grouped training. Do not pool these files for held-out-domain evaluation.

## Cleaning and grouping

Unicode/whitespace normalization, explicit source encodings, pattern privacy redaction,
narrative feature allowlists, canonical schema validation, and immutable source provenance
are applied to the full corpus. **121 empty narratives** and **6 narratives with no remaining
alphabetic content** are retained with exclusion reasons and excluded from model partitions.
This is not an English-language detector; abbreviated, multilingual, or low-information
narratives may still need review.

Event, exact-text, and conservative numeric-slot/punctuation template grouping produce
**667,358 connected groups**; the largest contains **713 records**. Records remain in the
cleaned archive; grouping prevents identified duplicate families from crossing evaluation
splits. Only training selection chooses one representative per group/domain, and it
excludes conflicting source labels.

## Frozen experiment policies

The assignment table contains separate columns for each experiment:

- Grouped 70/15/15: 466,857 train, 99,656 validation, 99,586 test, 39,625 demo-only,
  and 127 excluded rows. Row proportions vary with group size.
- FAA temporal: annual reporting files through 2023 train; 2024 validation; complete
  2025 test. Partial 2026 is never used in model training or evaluation. Families crossing
  temporal periods are quarantined instead of being reassigned into later evaluation years.
- Fire-door official: supplied assignments are retained. The safe variant quarantines
  **743 rows** in groups crossing those supplied splits. It retains 2,107 train,
  679 validation, and 682 test rows before source-label conflict filtering/training sampling.
  State these exclusions when comparing with results based on the original supplied split.
- Held-out domain: construction, aviation, and pipeline each have a separate experiment;
  any connected group containing the held-out domain stays out of training. Evaluate
  shared human-annotated entity labels, not incompatible source classifications.

FAA training sampling is proportional across condition/year strata with deterministic
hash ranking and a 75,000-record cap. It preserves approximate candidate proportions,
not class balance. Very rare strata may receive no samples. Label counts and selection
coverage are recorded in the local quality report.

## Reproduction and verification

Run `python scripts/prepare_corpus.py` in the project environment. Existing snapshot paths
are never overwritten. Frozen artifacts live under `data/processed/corpus-v1/` and remain
ignored by Git. `manifest.json` records source and artifact checksums and policy version.
Use `python scripts/verify_corpus.py` to check hashes, split/group isolation, every canonical
JSONL/Parquet record, and membership of the training sample.

No training or accuracy evaluation was performed during this milestone. Test narratives
were not inspected to tune the dictionaries or grouping policy; diagnostics use aggregate
metadata only.

## Remaining gates

- Human privacy review: regex redaction can miss sensitive information and over-redact.
- Source licence and authoritative codebook verification.
- Broader near-duplicate/paraphrase analysis and vendor/report-style holdouts.
- Preferred latest/final PHMSA event selection (current representative is deterministic,
  not guaranteed to be the final submission).
- Human annotation pilot, adjudication, and frozen gold entity test labels.
- Source-specific baseline training and per-class/domain/temporal evaluation.

Automated preparation is complete once snapshot verification passes. These remaining
items must not be represented as completed or as evidence of generalization accuracy.

## Verified result

Independent verification **passed** for all 705,851 canonical records and all 80,477
training-sample records. Raw source checksums were unchanged, artifact checksums matched,
assignment policies and group isolation passed, and the complete JSONL/Parquet payloads
matched. Machine-readable evidence is saved in `reports/corpus_verification.json`.
