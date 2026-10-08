# Vendor-independent completion checklist

## Software completed

- [x] Arbitrary English vendor/industry inputs; no dataset membership or vendor allowlist.
- [x] Batch machine-readable parsing, explicit mappings/profiles/aliases, report grouping and date validation.
- [x] Structural evidence text, redaction and normalized offset mapping.
- [x] Generic rules plus pinned optional English syntax coverage and versioned terminology packs.
- [x] Explicit no-defect evidence, unsupported review candidates and unavailable-model fallback.
- [x] Consistent hybrid threshold policy, model routing and artifact/cache provenance.
- [x] Typed findings, conservative relationships, optional categories and human corrections.
- [x] Immutable SQLite runs, append-only revisions, original/effective views, backups and legacy imports.
- [x] Explicit-evidence priorities, workflow status and reliably linked recurrence.
- [x] Seven purpose-specific pages, shared filters, chart drill-downs and correct report-rate denominators.
- [x] Reviewed/original filtered CSV, versioned JSON and escaped HTML exports.
- [x] Labelled synthetic cross-industry demonstrations and reproducible setup.
- [x] Privacy-gated annotation/evaluation, fixed labels, leakage checks and validation-only NER selection tooling.
- [x] Tests isolate temporary databases; fresh setup and real-browser chart interaction verified.
- [x] Each verified implementation increment committed; commit messages have at most two lines and no AI attribution.

## External validation still required

- [ ] Representative vendor reports across unseen vendors, templates, industries and time periods.
- [ ] Source permissions/codebooks and human privacy review for intended research/use.
- [ ] Two independent annotations, agreement measurement, adjudication and versioned gold sets.
- [ ] Sufficient independent groups for train/validation/test and held-out experiments.
- [ ] Actual human-validated entity/assertion/relationship/transfer metrics and error analysis.
- [ ] Broader paraphrase/template audit beyond conservative automated grouping.

Software capability is demonstrated; unrestricted real-world accuracy is not claimed. English-only,
machine-readable inputs, local single-user operation and review priorities remain the explicit scope.

Final verification: **93 tests pass** in both the existing environment and a clean installation
with the English model. Lint and dependency checks pass; browser chart selection was exercised.
