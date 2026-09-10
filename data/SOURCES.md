# Local source manifest

Audit date: 2026-09-09. Download dates are unknown; do not infer them from file modification
times. Machine-generated paths, column lists, row counts, and SHA-256 checksums are in
`reports/source_audit.json`, reproduced with `python scripts/audit_sources.py`.
Raw and derived narrative data are excluded from version control. No source records are
bundled for redistribution. Tests use explicitly synthetic examples, not gold annotations.

| Family | Authoritative location | Local version | Terms status |
| --- | --- | --- | --- |
| Fire door | https://figshare.com/articles/dataset/27281139 | training/validation/test XLSX; English-only local variant | Licence and upstream version correspondence unverified; do not redistribute |
| FAA SDR | https://www.faa.gov/av-info/download_SDR | 2011, 2013, 2015–2017, 2019–2020, 2023–2026 annual CSVs | Official download page verified 2026-09-09; exact redistribution terms and codebooks pending |
| PHMSA | https://www.phmsa.dot.gov/data-and-statistics/pipeline/pipeline-safety-data-report-index | Seven local current/legacy TXT subsets; see audit paths | Official index verified 2026-09-09; exact redistribution terms pending |

The Figshare page could not be retrieved during implementation. No licence is inferred from
public availability. The licence audit gate is **not complete**. FAA and PHMSA code values
remain unexpanded; official versioned code dictionaries must be verified before adding
code-based mappings. PHMSA field-definition PDFs exist alongside the downloaded TXT files
but have not yet been reconciled field by field.

## Transformations and field allowlists

- Fire door: `English` is the sole narrative; `Classification_English` stays in structured
  source fields. `Apartments` is required but not copied into model text. Korean columns
  are optional. Since no source ID column exists, workbook stem and physical row identify
  each original row. Preserve original supplied split and mark English as source-provided.
- FAA: `Discrepancy` alone is model input. `OperatorControlNumber` is the event/source ID;
  `DifficultyDate` is retained as a source date string. `PartCondition`, `PartName`, and
  `ComponentName` stay separate from input. Optional unrelated columns are not copied.
- PHMSA current: `NARRATIVE` alone is input; group by `REPORT_NUMBER`. Retain
  `LOCAL_DATETIME`/`REPORT_TYPE`; keep `CAUSE`, `CAUSE_DETAILS`, `SYSTEM_PART_INVOLVED`, and
  `MATERIAL_INVOLVED` separately when populated.
- PHMSA legacy: dedicated mapping uses `RPTID`, `IDATE`, `NARRATIVE`, with `CAUSE`,
  `CAUSE_TEXT`, and `CAUSE_DETAILS_TEXT` separate. TXT files decode as Windows-1252.
- All: NFKC Unicode normalization and whitespace collapse precede pattern redaction for
  emails, North American phones, common street addresses, and decimal coordinates. This
  is a first-pass filter, not anonymization certification. Raw files are the protected
  source of original narratives; exports omit a raw-text copy.

Pilot selection is first 250 rows per file, explicitly unsuitable for reported model metrics.
Full-source audit currently covers counts, empty text, schemas, and within-file event repeats;
class balance, text-length distributions, cross-file duplicates, and PII coverage remain pending.

## Full-corpus derived snapshot

`prepare_corpus.py` produces an immutable local snapshot using policy `corpus-v1`. Source
checksums and output checksums are frozen in its manifest. Annual FAA reporting-file year
is used for temporal assignment; 2026 is explicitly demo-only. Supplied fire-door splits
are preserved, with a separate duplicate-safe experiment assignment. Original/supplemental
PHMSA events are grouped globally by source event identifier. Template fingerprints mask
numeric slots and punctuation in longer narratives; they are a conservative heuristic.

`quality_report.json` now records full-corpus label/word-length distributions, redaction flags,
empty-text exclusions, grouping statistics, and split/sample coverage. Redaction flags
measure pattern matches, not the sensitivity or recall of a privacy detector. All derived
narratives and assignment tables remain local and ignored by Git. Redistribution terms
and human privacy review remain unresolved.

## Verification update — 2026-09-10

- **FAA SDR:** The FAA’s official download page lists annual SDR CSVs and describes them as
  reports submitted by operators and repair stations concerning aircraft malfunctions, failures,
  and defects. It includes the local reporting years and was checked on 2026-09-10.
  FAA’s published SDR submission instructions define `OperatorControlNumber`,
  `DifficultyDate`, `RegistryNNumber`, and `SubmitterTypeCode`; the local `PartCondition`,
  `PartName`, and `ComponentName` fields are preserved as source fields and excluded from the
  narrative model input. FAA’s published Internet-use policy says information on its public
  website is public information that may be copied or distributed. Attribute the FAA and retain
  source URLs and access dates; do not infer a separate open-data licence or redistribute
  narratives without completing privacy review.
- **PHMSA:** PHMSA’s official incident-data page says each report ZIP contains a data file and
  a field/column-description file. Its failure-cause guidance names the top-level cause families
  represented in this project, including corrosion, excavation damage, natural-force damage,
  other outside-force damage, material/weld failure, equipment failure, and incorrect operation.
  The report index says operator-submitted data are publicly available. Attribute PHMSA and
  retain source URLs and access dates; do not infer a Creative Commons licence or redistribute
  narratives without completing privacy review.
- **Fire door:** The local dataset refers to Figshare article `27281139`, but the item metadata
  and item-specific reuse licence could not be retrieved reliably on 2026-09-10. Its licence,
  citation, version correspondence, and redistribution permission remain **unverified**. Keep
  this raw and derived narrative data local until the article owner’s item-specific licence is
  recorded.

Official references checked on 2026-09-10:

- FAA SDR downloads: https://www.faa.gov/av-info/download_SDR
- FAA SDR submission instructions: https://sdrs.faa.gov/Documents/Instructions%20for%20Single%20Submission.pdf
- FAA public-information policy: https://www.faa.gov/documentlibrary/media/order/faa_order_1370.79a.pdf
- PHMSA incident data and field-description files: https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data
- PHMSA report index: https://www.phmsa.dot.gov/data-and-statistics/pipeline/pipeline-safety-data-report-index
- PHMSA failure causes: https://www.phmsa.dot.gov/incident-reporting/accident-investigation-division/pipeline-failure-causes

This completes official-source and code-family verification for the included FAA and PHMSA
fields. It does not resolve the fire-door item licence or certify any narrative for sharing.
