# Local vendor-independent demo

1. Install `.[dev,english]`. Import the labelled synthetic vendor demo into a separate database using
   `scripts/import_demo.py`, then start Streamlit with `INSPECTRA_DB` pointing to that database.
2. Open Overview: explain active defects versus all mentions, reports versus narratives, and backlog.
3. Open Report explorer: show arbitrary vendor metadata, highlighted evidence, unsupported `flensing`,
   and explicit no-defect/resolved/historical wording. Explain heuristic scores and optional packs.
4. Edit an assertion or span. If boundaries change, rebuild conservative links before confirming them.
   Save a review and demonstrate that Original extraction still preserves automated evidence.
5. Open Defect analysis: show the Pareto distribution and linked material/component heatmaps.
   Distinguish report-level co-occurrence from confirmed relationships.
6. Open Vendor comparison: show inspected/affected report counts and the report-rate denominator.
   Explain that these invented records do not establish a vendor safety ranking.
7. Open Trends: show missing-date counts and LOOM-1 recurrence with reliable vendor/asset/date linkage.
8. Open Review queue: show explicit priority reasons, candidate clauses, workflow status and history.
9. Open Model quality: distinguish historical source classification/silver results from pending human
   generalisation validation. Explain the new held-out vendor/template/industry/time workflow.
10. Export CSV, versioned JSON and HTML. Restart the app and confirm reviews persist in the library.

All demonstration vendors, reports and products are synthetic. A fresh checkout can run without the
large research datasets or optional locally trained classifiers. Missing English syntax models produce
a visible rules-only fallback rather than equivalent-coverage claims.
