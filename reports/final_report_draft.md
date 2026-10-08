# Inspectra final report draft

Inspectra is implemented as a local dashboard for English vendor inspection reports across industries.
Generic ingestion accepts arbitrary vendors and mapped table columns. Optional construction, aviation
and pipeline terminology packs and source classifiers remain research/task-specific additions.

Evidence retains document structure and normalized offset provenance. Generic spaCy rules and a pinned
English syntax model produce evidence-linked defect findings with assertions, optional categories,
explicit severity, and conservative component/material/action associations. Unfamiliar clauses and
ambiguous links remain visible for review. Explicit no-defect statements differ from unsupported extraction.

A local SQLite library preserves automated runs and append-only human corrections. Seven dashboard pages
cover overview, report review, defects, vendors, trends, review queue and model quality. Shared filters,
chart drill-downs, denominator-safe report rates and reviewed/original CSV/JSON/HTML exports are implemented.
Review priorities use explicit evidence; recurrence requires reliable metadata and chronology.

The research snapshot and stored classification artifacts remain separate. Historical provisional
AI-assisted entity scores do not establish human accuracy. Earlier hybrid threshold and holdout label
intersection limitations are addressed in the new runtime and evaluation tooling; historical reports
retain their original scope and must not be presented as current generalisation evidence.

The human-validation workflow now supports blinded privacy-reviewed batches, two independent annotations,
adjudication, frozen vendor/template/industry/temporal partitions, validation-only model selection, fixed
label evaluation, and parser/perturbation benchmarks. Actual human-validated transfer accuracy remains
pending representative reports and adjudicated labels. Synthetic tests/demos establish software behaviour
only. OCR, multilingual extraction, hosted team access and certified engineering risk are outside scope.
