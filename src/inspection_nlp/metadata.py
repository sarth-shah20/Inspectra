"""Explicit user mappings; metadata never becomes narrative model input."""

import json
from datetime import UTC, datetime
from pathlib import Path

FIELDS = ("vendor", "report_number", "report_date", "product", "batch", "asset_id")


def vendor_key(value: str, aliases: dict[str, str] | None = None) -> str:
    key = " ".join(value.split()).casefold()
    normalized = {
        " ".join(k.split()).casefold(): " ".join(v.split()).casefold()
        for k, v in (aliases or {}).items()
    }
    return normalized.get(key, key)


def normalize_metadata(values: dict, date_format: str | None = None) -> dict[str, str]:
    unknown = set(values) - set(FIELDS)
    if unknown:
        raise ValueError(f"Unknown metadata fields: {sorted(unknown)}")
    result = {
        k: " ".join(str(v).split()) for k, v in values.items() if v is not None and str(v).strip()
    }
    if result.get("report_date"):
        try:
            date = datetime.strptime(result["report_date"], date_format or "%Y-%m-%d").replace(
                tzinfo=UTC
            )
        except ValueError as exc:
            raise ValueError(
                "Report date is ambiguous or invalid; select its date format."
            ) from exc
        result["report_date"] = date.date().isoformat()
    return result


def load_profiles(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save_profile(path: Path, name: str, profile: dict) -> None:
    if not name.strip():
        raise ValueError("Enter a profile name")
    profiles = load_profiles(path)
    profiles[name.strip()] = profile
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(profiles, indent=2))
    temporary.replace(path)
