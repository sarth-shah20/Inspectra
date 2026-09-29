# Inspectra final report draft

Inspectra processes machine-readable inspection narratives from construction, aviation, and pipeline
sources through a canonical schema, conservative redaction, connected-group split policies, and
domain-configurable extraction. It provides transparent rule extraction, source-specific document
classification, editable review records, and an optional provisional hybrid NER view.

The frozen snapshot and aggregate analytics cover all downloaded records. FAA evaluation is temporal;
PHMSA evaluation is group-safe; fire-door evaluation quarantines cross-split duplicate groups. The
consolidated evaluation table is `reports/provisional_evaluation_summary.json`.

Entity metrics are provisional because their references are AI-assisted annotations. Held-out-domain
results vary materially, so no generalized or human-validated NER claim is made. The dashboard is an
offline research aid, not a compliance, safety-risk, or certification system.
