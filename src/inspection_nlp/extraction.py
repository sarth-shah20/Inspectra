"""Transparent, uncalibrated rules baseline. No source labels used as features."""

import hashlib
import re
from functools import lru_cache
from importlib.resources import files

import spacy
import yaml

from .artifacts import artifact_fingerprint
from .contextual import contextual_components, english_model, unmatched_clauses
from .findings import with_findings
from .schemas import Entity, Record

DOMAINS = {"general", "construction", "aviation", "pipeline"}
MEASUREMENT = re.compile(
    r"(?<!\w)\d+(?:\.\d+)?\s*(?:(?:µm|μm|um|mm|cm|km|inches|inch|psi|kPa|MPa|bar|°C|°F|ft|m|kg|mg|g|N|kN|Nm|rpm|V|mV|A|mA)\b|%(?!\w))",
    re.IGNORECASE,
)
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
BOUNDARY = re.compile(r"[.!?;]|\b(?:but|however|although)\b", re.IGNORECASE)


def pipeline(domain: str, pack_paths: tuple[str, ...] = ()):
    from pathlib import Path

    signatures = tuple(artifact_fingerprint(Path(path)) for path in pack_paths)
    return _pipeline(domain, pack_paths, signatures)


@lru_cache(maxsize=8)
def _pipeline(domain: str, pack_paths: tuple[str, ...], signatures: tuple[str, ...]):
    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler", config={"phrase_matcher_attr": "LOWER"})
    resources = [files("inspection_nlp").joinpath("configs/generic.yaml")]
    if domain in DOMAINS - {"general"}:
        resources.append(files("inspection_nlp").joinpath(f"configs/domains/{domain}.yaml"))
    from pathlib import Path

    resources.extend(Path(path) for path in pack_paths)
    patterns, versions = [], []
    config_hash = hashlib.sha256()
    for resource in resources:
        content = resource.read_text()
        config_hash.update(content.encode())
        config = yaml.safe_load(content)
        if (
            not isinstance(config, dict)
            or not isinstance(config.get("entities"), dict)
            or not config.get("version")
        ):
            raise ValueError("Terminology packs require version and entities")
        versions.append(str(config["version"]))
        for label, terms in config["entities"].items():
            if (
                label not in Entity.model_fields["label"].annotation.__args__
                or not isinstance(terms, list)
                or any(not isinstance(t, str) for t in terms)
            ):
                raise ValueError(f"Invalid terminology label or terms: {label}")
            patterns.extend({"label": label, "pattern": term} for term in terms)
    ruler.add_patterns(patterns)
    return nlp, "+".join(versions) + ":" + config_hash.hexdigest()


def assertion(text: str, start: int, end: int) -> str:
    """Local clause cues; bounded heuristic rather than syntactic assertion model."""
    before = BOUNDARY.split(text[:start])[-1].lower()
    after = BOUNDARY.split(text[end:])[0].lower()
    # Limit scope at another coordinated clause with its own explicit subject/verb.
    after = re.split(r"\b(?:and|or)\b", after)[0]
    before = " ".join(before.split()[-6:])
    after = " ".join(after.split()[:6])
    if re.search(
        r"\b(?:failed to (?:find|detect|observe)|no|without|neither|denies)\b", before
    ) or re.match(r"\s*(?:was |is |were )?(?:not (?:found|observed|detected)|absent)\b", after):
        return "negated"
    if re.search(r"\b(?:possible|possibly|suspected|may|might|potential)\b", before) or re.match(
        r"\s*(?:was |is )?(?:suspected|possible)\b", after
    ):
        return "possible"
    if re.search(r"\b(?:previous|previously|historical|history of)\b", before):
        return "historical"
    if re.search(r"\b(?:repaired|resolved|rectified|corrected)\s*$", before) or re.match(
        r"\s*(?:(?:has|have) been |was |were |is )?(?:repaired|resolved|rectified|corrected)\b",
        after,
    ):
        return "resolved"
    return "present"


def extract(
    record: Record,
    *,
    use_domain: bool = True,
    contextual: bool = True,
    pack_paths: tuple[str, ...] = (),
) -> Record:
    domain = record.domain if use_domain else "general"
    nlp, version = pipeline(domain, pack_paths)
    text = record.display_text
    candidates = []
    for pattern, label in [(MEASUREMENT, "MEASUREMENT"), (DATE, "DATE")]:
        for match in pattern.finditer(text):
            candidates.append((match.start(), match.end(), label, "regex", 0.95))
    for span in nlp(text).ents:
        if (
            span.label_ == "DEFECT"
            and span.text.lower() == "failed"
            and re.match(r"\s+to\s+(?:find|detect|observe)\b", text[span.end_char :], re.IGNORECASE)
        ):
            continue
        candidates.append((span.start_char, span.end_char, span.label_, "ruler", 0.75))
    entities = []
    for start, end, label, method, confidence in candidates:
        if any(start < e.evidence_end and end > e.evidence_start for e in entities):
            continue
        entities.append(
            Entity(
                label=label,
                text=text[start:end],
                evidence_start=start,
                evidence_end=end,
                assertion=assertion(text, start, end),
                confidence=confidence,
                extraction_method=method,
            )
        )
    parser = english_model() if contextual else None
    from .contextual import contextual_materials

    for start, end, label, method, score in contextual_materials(text, entities, parser):
        if not any(start < e.evidence_end and end > e.evidence_start for e in entities):
            entities.append(
                Entity(
                    label=label,
                    text=text[start:end],
                    evidence_start=start,
                    evidence_end=end,
                    assertion="present",
                    confidence=score,
                    extraction_method=method,
                )
            )
    for start, end, label, method, score in contextual_components(text, entities, parser):
        if not any(start < e.evidence_end and end > e.evidence_start for e in entities):
            entities.append(
                Entity(
                    label=label,
                    text=text[start:end],
                    evidence_start=start,
                    evidence_end=end,
                    assertion="present",
                    confidence=score,
                    extraction_method=method,
                )
            )
    entities.sort(key=lambda e: e.evidence_start)
    defects = [e for e in entities if e.label == "DEFECT"]
    assertions = {e.assertion for e in defects}
    payload = record.model_dump()
    metadata = dict(record.document_metadata)
    metadata.update(
        extractor_version="generic-context-v2+" + version,
        extraction_mode="contextual" if parser is not None else "rules_only",
        english_model="en_core_web_sm:3.8.0" if parser is not None else "unavailable_or_disabled",
        english_model_sha256=artifact_fingerprint(parser.path)
        if parser is not None and parser.path
        else "unavailable",
        confidence_kind="uncalibrated_rule_score",
        review_reason="Vocabulary coverage and assertion scope require human review",
    )
    review_candidates = unmatched_clauses(text, entities)
    payload.update(
        entities=[e.model_dump() for e in entities],
        document_metadata=metadata,
        review_candidates=review_candidates,
        mapping_status="review_required" if defects or review_candidates else "unmapped",
        assertion_status=next(iter(assertions)) if len(assertions) == 1 else "unknown",
        reported_severity=None,
        quality_flags=list(
            dict.fromkeys(
                [
                    *record.quality_flags,
                    *(["rules_only_coverage"] if contextual and parser is None else []),
                ]
            )
        ),
    )
    # Severity is explicit evidence only, never inferred from defect type.
    severity = [
        e.text for e in entities if e.label == "REPORTED_SEVERITY" and e.assertion == "present"
    ]
    if severity:
        payload["reported_severity"] = "; ".join(dict.fromkeys(severity))
    return with_findings(Record.model_validate({**payload, "findings": [], "relations": []}))
