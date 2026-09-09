# Inspectra entity annotation guide — pilot v1

This guide defines the first human annotation pilot. It applies to privacy-reviewed English
narratives from construction/fire-door, FAA SDR, and PHMSA pipeline reports. Annotate explicit
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

Do not annotate `VENDOR` or `PRODUCT` in this pilot unless a second annotator can apply them
consistently. Do not label source codes or a source-provided document class unless its literal
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
