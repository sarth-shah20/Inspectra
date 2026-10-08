# Synthetic vendor-independent demonstration

All reports, vendors, products, and identifiers here are invented. They demonstrate
software capabilities and cannot establish accuracy on real inspection reports.

Upload `synthetic_reports.csv` with the General terminology pack. Map `Inspection`
to narrative, `Company` to vendor, `InspectionDate` to report date, `ReportNumber`
to report number, and the other matching columns to product/batch/asset.
Date format is `%Y-%m-%d`. Save the mapping as a reusable profile.

Explore the vendor rates (including clean inspection reports), monthly trends,
linked material/component heatmaps, and LOOM-1 recurrence. `flensing` intentionally
has no known category and should remain a review candidate. Add or correct its
spans through review only when supplied evidence supports that decision.

Alternatively run `python scripts/import_demo.py --database /tmp/inspectra-demo.sqlite3`
and launch Streamlit with `INSPECTRA_DB=/tmp/inspectra-demo.sqlite3`.
