"""Conservative first-pass redaction; human privacy review remains required."""

import re
import unicodedata

_PATTERNS = [
    r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
    r"(?<!\w)(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}(?!\w)",
    r"(?<![\w.])-?\d{1,3}\.\d{4,}\s*[,;/]\s*-?\d{1,3}\.\d{4,}(?!\d)",
    r"\b(?:latitude|longitude|lat|lon|long)\s*[:=]?\s*-?\d{1,3}\.\d+",
    (
        r"\b\d{1,6}\s+(?:[\w.-]+\s+){1,5}(?:street|st|road|rd|avenue|ave|"
        r"boulevard|blvd|lane|ln|drive|dr|court|ct|way)\b\.?"
    ),
]
REDACTORS = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def prepare_text(text: str) -> tuple[str, bool]:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    sensitive = False
    for pattern in REDACTORS:
        text, count = pattern.subn("[REDACTED]", text)
        sensitive |= count > 0
    return text, sensitive


def prepare_evidence(text: str) -> tuple[str, str, list[int], bool]:
    """Preserve structural whitespace; map normalized characters to redacted evidence."""
    evidence = unicodedata.normalize('NFKC', text).replace('\r\n', '\n').replace('\r', '\n')
    sensitive = False
    for pattern in REDACTORS:
        evidence, count = pattern.subn('[REDACTED]', evidence)
        sensitive |= bool(count)
    evidence = evidence.strip()
    chars, offsets = [], []
    for match in re.finditer(r'\S+|\s+', evidence):
        value = match.group()
        if value.isspace():
            chars.append(' ')
            offsets.append(match.start())
        else:
            chars.extend(value)
            offsets.extend(range(match.start(), match.end()))
    offsets.append(len(evidence))
    return evidence, ''.join(chars), offsets, sensitive
