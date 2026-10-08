# Local report library

The application stores local reports in `data/local/inspectra.sqlite3`, excluded from Git.
Set `INSPECTRA_DB` to choose another database. Extraction runs and review revisions are
append-only. A changed extraction configuration starts a separate run; reviews apply only
to their original run. Dashboards can select original or latest reviewed evidence.

Before upgrading a database, stop application writes and create a new backup using
`Library(path).backup(destination)` from `inspection_nlp.storage`. SQLite's backup API
creates a consistent snapshot. Restore by closing the app and replacing its database
with the backup. Do not copy a database during an active write.

Schema version zero initializes version one. Newer unsupported versions are rejected;
future schema migrations must preserve originals and receive migration tests.
Legacy JSONL files are never overwritten. Imports are idempotent; unmatched reviews are
retained in the `imports` table and do not change any report.
