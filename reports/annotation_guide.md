# Inspectra entity annotation guide — vendor pilot v2

This guide defines the first human annotation pilot. It applies to privacy-reviewed English
vendor reports across industries. Construction/fire-door, FAA SDR, and PHMSA are optional research sources. Annotate explicit
evidence only. Do not infer engineering status, compliance, vendor identity, severity, a cause,
or a corrective action that the narrative does not state.

## Entity labels

| Label | Mark when the text explicitly names | Examples |
| --- | --- | --- |
| `COMPONENT` | A physical part or assembly | `door closer`, `fuel pump`, `weld` |
| `MATERIAL` | A material | `steel`, `polyethylene` |
| `DEFECT` | A condition, failure, damage, or deficiency | `crack`, `corroded`, `frame gap` |
| `LOCATION` | A physical location of a finding | `left hinge`, `station 14` |
| `MEASUREMENT` | A value and its unit | `3 mm`, `200 psi` |
| `INSPECTION_METHOD` | A stated inspection/discovery method | `visual inspection` |
| `REPORTED_SEVERITY` | Severity wording supplied by the report | `critical`, `minor` |
| `CAUSE` | An explicitly stated cause | `excavation damage` |
| `CORRECTIVE_ACTION` | A stated repair or action | `replaced`, `repair required` |
| `DATE` | A date written in the narrative | `2024-01-02` |

Annotate `VENDOR` and `PRODUCT` only when their role is explicit; both annotators must apply the same boundary and role rules. Do not label source codes or a source-provided document class unless its literal
wording is present in the narrative.

## Span boundaries and overlap

Use the smallest complete phrase. Include units with measurements. For `fuel pump crack`, label
`fuel pump` as `COMPONENT` and `crack` as `DEFECT`. Do not overlap spans because the initial spaCy
NER format cannot represent overlaps. If a nested label is unavoidable, retain the label that best
answers the finding question and record the decision in adjudication notes.

## Assertion status

Every `DEFECT` must receive one of these attributes:

- `present`: `crack found`
- `negated`: `no crack observed`
- `possible`: `possible leak`
- `historical`: `previous corrosion`
- `resolved`: `crack was repaired`

Assertion status describes the report wording, not an annotator’s judgement. A resolved or negated
defect remains an annotated span; its status prevents it being counted as an active finding.

## Difficult cases

- `failed to find a crack`: annotate `crack` as `DEFECT`, `negated`.
- `crack repaired and valve leaking`: annotate both defects; `crack` is `resolved`, `leaking` is
  `present`.
- `cause unknown`: do not label `unknown` as `CAUSE`; only label a stated cause phrase.
- `inspect the valve`: label no `CORRECTIVE_ACTION` unless the text states an action to address a
  finding, such as `valve was replaced`.
- `severe corrosion`: label `severe` as `REPORTED_SEVERITY` only if the report uses it as severity;
  label `corrosion` as `DEFECT`.

## Pilot workflow and agreement

1. Privacy-review candidate text and remove/decline any unsuitable record.
2. Two annotators independently label the shared 40-record calibration subset.
3. Adjudicate disagreements, update this guide, and version the decision log.
4. Each annotator labels the remaining pilot records independently.
5. Double-annotate the eventual test partition. Report strict and overlap entity agreement,
   adjudication rate, and common disagreement types.

The initial target is 75–100 records per domain, stratified by source class/cause. A candidate
batch is not gold data. Keep exported candidates, human annotations, weak labels, and model
predictions in distinct versioned locations.

## Vendor metadata and relationships

Confirm explicit vendor/supplier identity, report date/ID, product, batch and asset metadata.
Do not infer a vendor from an arbitrary organisation mention. Mark missing metadata unknown.
Vendor and product spans are permitted only when their role is explicit in the report.

For every DEFECT create a finding with the defect evidence reference. Annotate component,
material, measurement, severity, method, cause, action and location links only when supported.
Explicitly leave ambiguous links empty and mark the finding ambiguous. Preserve unknown
terminology without forcing categories. Independently annotate unsupported inspection/action
clauses as review candidates; these are not confirmed defects.

## Human gold workflow

Use `scripts/generalisation.py batch` with an external approved-record-ID file to export
blinded library candidates. Preserve structural evidence text and its offsets. Each candidate
requires two independent annotator IDs, an adjudicator, annotation version and final status
`adjudicated` before evaluation. Ordinary single-reviewer app corrections are not gold data.

Freeze separate vendor, template, industry and temporal manifests using the `split` command.
Connected report/event/template families must stay together. Vendor splits group all records
from each normalized vendor; groups bridging vendors stay out of training if any is held out.
Temporal families crossing cutoffs are quarantined. Exact/numeric templates plus conservative
token overlap are safeguards, not a complete paraphrase detector.

Train with the `train` command only after adjudication; it selects between fixed 10/20-epoch
candidates on validation data. Run `evaluate` once on the sealed test partition and version
the output. The fixed label set includes test-only labels so unsupported labels count as misses.
Never adjust terminology, thresholds or model settings using test errors.
