"""Versioned fingerprints and split policy; no learned thresholds or test-set tuning."""

import hashlib
import re

POLICY_VERSION = "corpus-v1"


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def text_keys(text: str) -> tuple[str, str | None]:
    normalized = " ".join(text.casefold().split())
    exact = fingerprint(normalized) if normalized else ""
    tokens = re.findall(r"\w+(?:[.-]\w+)*", normalized)
    # Conservative template family: punctuation/case variation, and numeric slots.
    # Require eight tokens to avoid merging unrelated short findings.
    template = None
    if len(tokens) >= 8:
        template = fingerprint(
            " ".join("<NUMBER>" if re.fullmatch(r"\d+(?:\.\d+)?", t) else t for t in tokens)
        )
    return exact, template


def grouped_split(group_id: str, seed: str) -> str:
    score = int(fingerprint(f"{seed}:{group_id}")[:8], 16) / 2**32
    return "train" if score < 0.7 else "validation" if score < 0.85 else "test"


def faa_period(year: int) -> str:
    if year == 2026:
        return "demo"
    if year == 2025:
        return "test"
    if year == 2024:
        return "validation"
    if 2010 <= year <= 2023:
        return "train"
    return "quarantine"


class UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def root(self, index: int) -> int:
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def union(self, left: int, right: int):
        a, b = self.root(left), self.root(right)
        self.parent[max(a, b)] = min(a, b)
