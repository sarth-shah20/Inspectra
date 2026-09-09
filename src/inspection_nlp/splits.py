"""Group event versions and exact normalized duplicates before any split."""

import hashlib
from collections import defaultdict

from .schemas import Record


def assign_splits(
    records: list[Record], seed: str = "inspectra-v1", held_out_domain: str | None = None
) -> None:
    parent = list(range(len(records)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, record in enumerate(records):
        keys = [("event", record.source_event_id)]
        if record.clean_text:
            keys.append(("text", " ".join(record.clean_text.casefold().split())))
        for key in keys:
            if key in seen:
                parent[root(i)] = root(seen[key])
            else:
                seen[key] = i
    groups = defaultdict(list)
    for i in range(len(records)):
        groups[root(i)].append(records[i])
    for group in groups.values():
        # A connected duplicate in the held-out domain also stays out of training.
        if held_out_domain and any(r.domain == held_out_domain for r in group):
            split = "test"
        else:
            key = min(r.source_event_id for r in group)
            score = int(hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()[:8], 16) / 2**32
            split = "train" if score < 0.8 else "validation" if score < 0.9 else "test"
            if held_out_domain and split == "test":
                split = "validation"
        for record in group:
            record.split = split
