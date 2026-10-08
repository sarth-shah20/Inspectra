"""Explainable workflow priorities and conservative report recurrence."""

from collections import defaultdict
from importlib.resources import files

import yaml

from .metadata import vendor_key
from .schemas import Record


def prioritize(record: Record, enabled: bool = True, rules: dict | None = None) -> Record:
    rules = rules or yaml.safe_load(
        files("inspection_nlp").joinpath("configs/priority.yaml").read_text()
    )
    payload = record.model_dump()
    tiers = []
    for finding in payload["findings"]:
        reasons = []
        assertion = finding["defect"]["assertion"]
        if not enabled:
            tier = "disabled"
            reasons = ["Priority rules disabled"]
        elif assertion in {"negated", "historical", "resolved"}:
            tier = "low"
            reasons = [f"Defect assertion is {assertion}"]
        else:
            tier = "normal"
            reasons = [f"Defect assertion is {assertion}"]
            severities = [
                e["text"].casefold() for e in finding["links"].get("REPORTED_SEVERITY", [])
            ]
            actions = [e["text"].casefold() for e in finding["links"].get("CORRECTIVE_ACTION", [])]
            if any(s in rules["high_severity"] for s in severities):
                tier = "high"
                reasons.append("Explicit linked major/critical/severe wording")
            if any(
                any(term in action for term in rules["urgent_action_terms"]) for action in actions
            ):
                tier = "high"
                reasons.append("Explicit linked urgent corrective action")
        if finding["ambiguous"]:
            reasons.append("Ambiguous evidence associations require review")
        finding.update(priority=tier, priority_reasons=reasons)
        tiers.append(tier)
    scores = {"high": 3, "normal": 2, "low": 1}
    score = max(
        [scores[t] for t in tiers if t in scores]
        + ([2] if record.review_candidates and enabled else []),
        default=0,
    )
    payload["review_priority"] = float(score) if enabled else None
    payload["document_metadata"]["priority_policy"] = (
        str(rules["version"]) if enabled else "disabled"
    )
    return Record.model_validate(payload)


def with_recurrence(records: list[Record]) -> list[Record]:
    grouped = defaultdict(list)
    output = [r.model_copy(deep=True) for r in records]
    for record in output:
        for finding in record.findings:
            finding.recurrence_previous = []
        metadata = record.report_metadata
        vendor = vendor_key(metadata.get("vendor", ""))
        identity = (
            ("asset", metadata["asset_id"])
            if metadata.get("asset_id")
            else ("batch", metadata["batch"])
            if metadata.get("batch")
            else None
        )
        date = metadata.get("report_date") or record.report_date
        if not vendor or not identity or not date:
            record.document_metadata["recurrence_status"] = "insufficient_linkage"
            continue
        record.document_metadata["recurrence_status"] = "linkage_available"
        for finding in record.findings:
            if finding.category and finding.defect.assertion in {"present", "possible"}:
                grouped[(vendor, *identity, finding.category)].append(
                    (date, record.report_id or record.record_id, finding)
                )
    for entries in grouped.values():
        for date, report_id, finding in entries:
            finding.recurrence_previous = sorted(
                {
                    previous.finding_id
                    for before, old_report, previous in entries
                    if before < date and old_report != report_id
                }
            )
    return output
