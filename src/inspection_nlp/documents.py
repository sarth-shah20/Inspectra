"""User-document adapters: one record per page, document, or selected table row."""

import csv
import hashlib
import io
from pathlib import Path

from .preprocessing import prepare_text
from .schemas import Domain, Record

NO_OCR = (
    "This version supports machine-readable PDFs only. "
    "Scanned documents require OCR and are outside the project scope."
)
MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 10000


def _record(
    text: str,
    name: str,
    digest: str,
    index: int,
    domain: Domain,
    text_column: str = "text",
    metadata: dict | None = None,
) -> Record:
    cleaned, sensitive = prepare_text(text)
    return Record(
        record_id=f"upload:{digest[:16]}:{index}",
        source_dataset="user_upload",
        source_record_id=str(index),
        source_event_id=f"upload:{digest}:{index}",
        source_document=Path(name).name,
        source_sha256=digest,
        source_row=index + 2,
        domain=domain,
        schema_version="upload_v1",
        source_column_mapping={"clean_text": text_column},
        clean_text=cleaned,
        display_text=cleaned,
        contains_sensitive_fields=sensitive,
        document_metadata={"privacy_review": "pending", **(metadata or {})},
    )


def parse_document(
    data: bytes,
    filename: str,
    *,
    domain: Domain = "general",
    text_column: str | None = None,
    encoding: str = "utf-8-sig",
    tabular_txt: bool = False,
) -> list[Record]:
    if len(data) > MAX_BYTES:
        raise ValueError("Upload exceeds the 20 MiB limit.")
    digest = hashlib.sha256(data).hexdigest()
    suffix = Path(filename).suffix.lower()
    segments: list[tuple[str, int, dict]] = []
    if suffix == ".pdf":
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                raise ValueError("Password-protected PDFs are not supported.")
            for index, page in enumerate(document):
                text = page.get_text(sort=True)
                if not text.strip():
                    # Reject mixed scanned/text files rather than silently omit pages.
                    raise ValueError(f"Page {index + 1}: {NO_OCR}")
                segments.append((text, index, {"page": str(index + 1)}))
    elif suffix == ".docx":
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        document = Document(io.BytesIO(data))
        blocks = []
        for item in document.iter_inner_content():
            if isinstance(item, Paragraph):
                blocks.append(item.text)
            elif isinstance(item, Table):
                blocks.extend(" | ".join(cell.text for cell in row.cells) for row in item.rows)
        segments.append(("\n".join(blocks), 0, {}))
    elif suffix in {".csv", ".tsv", ".xlsx"} or (suffix == ".txt" and tabular_txt):
        if not text_column:
            raise ValueError("Select the narrative text column; other columns are not model input.")
        if suffix == ".xlsx":
            from openpyxl import load_workbook

            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            try:
                values = workbook.active.iter_rows(values_only=True)
                headers = list(next(values, ()))
                if headers.count(text_column) != 1:
                    raise ValueError("Narrative column must exist exactly once.")
                column = headers.index(text_column)
                for index, row in enumerate(values):
                    if index >= MAX_ROWS:
                        raise ValueError("Table exceeds the 10,000-row upload limit.")
                    value = row[column]
                    segments.append((str(value) if value is not None else "", index, {}))
            finally:
                workbook.close()
        else:
            stream = io.StringIO(data.decode(encoding), newline="")
            reader = csv.DictReader(stream, delimiter="," if suffix == ".csv" else "\t")
            if not reader.fieldnames or reader.fieldnames.count(text_column) != 1:
                raise ValueError("Narrative column must exist exactly once.")
            for index, row in enumerate(reader):
                if index >= MAX_ROWS:
                    raise ValueError("Table exceeds the 10,000-row upload limit.")
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f"Malformed table row {index + 2}.")
                segments.append((row[text_column], index, {}))
    elif suffix == ".txt":
        segments.append((data.decode(encoding), 0, {}))
    else:
        raise ValueError("Supported formats: PDF, DOCX, CSV, XLSX, TSV, and TXT.")
    records = [
        _record(text, filename, digest, index, domain, text_column or "text", metadata)
        for text, index, metadata in segments
        if text.strip()
    ]
    if not records:
        raise ValueError("No narrative text found in the selected input.")
    return records
