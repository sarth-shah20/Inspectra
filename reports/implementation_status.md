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
