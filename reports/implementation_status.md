# Vendor-independent implementation progress

Software implementation is separate from human-validated accuracy.

- Stage 1: repaired review saving, dynamic spans, evidence preview, defect counts, and stale-state handling.
- Stage 2: added arbitrary industry identifiers, metadata mappings/profiles, batch parsing, report grouping, and structural evidence offsets. Tests cover unfamiliar vendors and formats.
- Stage 3: added pinned English syntax model, contextual component coverage, optional versioned YAML packs, unsupported-clause candidates, and visible rules-only fallback. Verified unfamiliar textile terminology and degraded mode.
- Stage 4: unified hybrid thresholds, fixed mixed assertions, made source-taxonomy classification explicit, and generated provisional_hybrid_calibration_v2.json. The older calibration and derived provisional summary are superseded for hybrid comparisons. No human accuracy claim.
- Stage 5: added typed defect findings, clause-local evidence links, ambiguous association handling, relationship corrections, generic categories, and assertion regressions. All links are validated against record evidence.
- Stage 6: SQLite schema v1 stores immutable extraction runs and review revisions, latest effective views, idempotent legacy imports (unmatched preserved), and consistent backups. Restart and transaction tests pass.
- Stage 7: configurable explicit-evidence priority tiers, visible reasons, separate review workflow statuses, and recurrence restricted to vendor + asset/batch + category + chronology. Verified no unsupported criticality.
- Stage 8: seven Streamlit pages share metadata/finding filters, Plotly drill-downs, denominator-safe vendor rates, linked heatmaps, monthly outcomes, recurrence, review backlog, and separate research/model artifacts. All pages render in interaction tests.
- Stage 9: versioned JSON, additive CSV, escaped standalone HTML, filtered reviewed/original exports, pinned chart/model dependencies, and synthetic cross-industry demo/import instructions. Full suite: 81 tests pass; synthetic import verified.
- Stage 10: added privacy-gated blinded batches, two-annotator gold validation, fixed-label scoring, vendor/template/industry/time partitions, conservative leakage checks, validation-only NER selection, parser timing/errors, and perturbation checks. Synthetic integration tests exercise all four extraction comparisons. Real human accuracy remains pending.
- Stage 11 verification increment: fingerprints invalidate changed model/pack caches; explicit unfamiliar materials and compound components are supported; chart selections also scope exports; UI tables use readable report identities. 90 tests and lint pass. Fresh installation, dependency check, demo import, and real-browser chart selection verified.
- Final extraction check: explicit no-defect statements are distinguished from unsupported/missing extraction, with preserved evidence and no inferred clean-report verdict.
- Spreadsheet metadata check: native Excel dates normalize to ISO dates without requiring string-format selection; ambiguous string dates still require explicit formats.
- Final verification: 93 tests pass in both the existing environment and a clean `.[dev,english]` installation; lint and dependency checks pass. Upload/extraction, review, restart, analytics and export flows are covered. Real-browser chart selection narrows evidence correctly. Current documentation separates software completion, synthetic capabilities, historical metrics and pending human validation.
