# Inspectra dataset card

## Snapshot

`corpus-v1` is a local, immutable cleaned research snapshot of 705,851 records: 690,332 FAA SDR,
4,212 fire-door, and 11,307 PHMSA records. It stores checksums, canonical JSONL/Parquet records,
connected duplicate/event groups, and experiment assignments. Raw and derived narratives remain
ignored by Git.

## Intended use and restrictions

Use for local research, reproducible baseline development, and demonstration. Do not treat report
volume as safety risk, publish narrative text without completing privacy review, or infer that
source-specific labels are cross-domain entity truth. FAA and PHMSA official provenance is recorded
in `data/SOURCES.md`; the fire-door item-specific licence is unresolved.

## Splits

FAA uses older years through 2023 for training, 2024 validation, 2025 test, and 2026 demo-only.
Fire-door uses safe supplied splits. PHMSA uses event-connected grouped splits. Aggregate coverage
is in `reports/source_wide_analytics.json`.

## Labels

Source classification labels remain source-specific. Entity labels in the provisional set are
AI-assisted spans only and are not gold annotations or human-validated evidence.
