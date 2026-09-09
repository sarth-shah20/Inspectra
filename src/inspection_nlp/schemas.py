from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Domain = Literal["construction", "aviation", "pipeline", "general"]
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
    text: str
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(gt=0)
    assertion: Literal["present", "negated", "possible", "historical", "resolved"]
    confidence: float = Field(ge=0, le=1)
    extraction_method: Literal["regex", "ruler", "ner", "source", "human"]


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
    entities: list[Entity] = Field(default_factory=list)
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
        for entity in self.entities:
            if self.display_text[entity.evidence_start : entity.evidence_end] != entity.text:
                raise ValueError("Entity evidence must match display_text offsets")
        return self
