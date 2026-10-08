from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Domain = str
Split = Literal["train", "validation", "test"]


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Literal[
        "VENDOR",
        "PRODUCT",
        "COMPONENT",
        "MATERIAL",
        "DEFECT",
        "LOCATION",
        "MEASUREMENT",
        "INSPECTION_METHOD",
        "REPORTED_SEVERITY",
        "CAUSE",
        "CORRECTIVE_ACTION",
        "DATE",
    ]
    text: str = Field(min_length=1)
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(gt=0)
    assertion: Literal["present", "negated", "possible", "historical", "resolved"]
    confidence: float = Field(ge=0, le=1)
    extraction_method: Literal["regex", "ruler", "ner", "source", "human", "contextual"]


class Finding(BaseModel):
    finding_id: str
    defect: Entity
    category: str | None = None
    links: dict[str, list[Entity]] = Field(default_factory=dict)
    ambiguous: bool = False
    priority: Literal["high", "normal", "low", "disabled"] = "normal"
    priority_reasons: list[str] = Field(default_factory=list)
    recurrence_previous: list[str] = Field(default_factory=list)


class ReviewCandidate(BaseModel):
    text: str = Field(min_length=1)
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(gt=0)
    reason: str


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str
    source_dataset: str
    source_record_id: str
    source_event_id: str
    source_document: str
    source_sha256: str
    source_row: int = Field(ge=2)
    domain: Domain
    schema_version: str
    source_column_mapping: dict[str, str]
    report_status: str | None = None
    report_date: str | None = None
    clean_text: str
    display_text: str
    structured_source_fields: dict[str, str] = Field(default_factory=dict)
    document_metadata: dict[str, str] = Field(default_factory=dict)
    report_id: str = ""
    report_metadata: dict[str, str] = Field(default_factory=dict)
    metadata_provenance: dict[str, str] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    absence_statements: list[ReviewCandidate] = Field(default_factory=list)
    review_candidates: list[ReviewCandidate] = Field(default_factory=list)
    clean_to_display: list[int] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    relations: list[dict] = Field(default_factory=list)
    reported_severity: str | None = None
    review_priority: float | None = None
    assertion_status: str = "unknown"
    mapping_status: Literal["mapped", "unmapped", "review_required"] = "review_required"
    contains_sensitive_fields: bool = False
    label_origin: Literal["human", "source", "weak", "generated"] = "source"
    split: Split | None = None

    @model_validator(mode="after")
    def check_evidence(self):
        if self.clean_to_display:
            if len(self.clean_to_display) != len(self.clean_text) + 1:
                raise ValueError("Invalid normalized offset map length")
            if self.clean_to_display != sorted(self.clean_to_display) or self.clean_to_display[
                -1
            ] != len(self.display_text):
                raise ValueError("Invalid normalized offset map bounds")
        for entity in [*self.entities, *self.review_candidates, *self.absence_statements]:
            if self.display_text[entity.evidence_start : entity.evidence_end] != entity.text:
                raise ValueError("Entity evidence must match display_text offsets")
        evidence_keys = {
            (e.label, e.evidence_start, e.evidence_end, e.text, e.assertion) for e in self.entities
        }
        for finding in self.findings:
            if finding.defect.label != "DEFECT":
                raise ValueError("Finding must reference a defect")
            for label, evidence in finding.links.items():
                if label not in {
                    "COMPONENT",
                    "MATERIAL",
                    "MEASUREMENT",
                    "REPORTED_SEVERITY",
                    "CAUSE",
                    "CORRECTIVE_ACTION",
                    "INSPECTION_METHOD",
                    "LOCATION",
                }:
                    raise ValueError("Unsupported relationship label")
                if any(e.label != label for e in evidence):
                    raise ValueError("Relationship label must match evidence")
            for e in [
                finding.defect,
                *(item for evidence in finding.links.values() for item in evidence),
            ]:
                if (
                    e.label,
                    e.evidence_start,
                    e.evidence_end,
                    e.text,
                    e.assertion,
                ) not in evidence_keys:
                    raise ValueError("Finding evidence must reference this record")
        return self
