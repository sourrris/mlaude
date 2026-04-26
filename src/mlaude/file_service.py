from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mlaude.models import StoredFile, new_id
from mlaude.retrieval import LocalRetrievalIndex
from mlaude.settings import FILES_DIR, MAX_FILE_READ_CHARS, ensure_app_dirs

try:  # pragma: no cover - optional runtime dependency
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional runtime dependency
    PdfReader = None

try:  # pragma: no cover - optional runtime dependency
    from docx import Document
except Exception:  # pragma: no cover - optional runtime dependency
    Document = None


TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".csv",
    ".yaml",
    ".yml",
    ".html",
    ".css",
    ".sql",
    ".log",
}


def safe_title(filename: str) -> str:
    stem = Path(filename).stem or filename
    return re.sub(r"[_-]+", " ", stem).strip().title() or "Untitled File"


def extract_text(
    *,
    filename: str,
    content_type: str | None,
    raw_bytes: bytes,
) -> str:
    suffix = Path(filename).suffix.lower()

    if suffix in TEXT_EXTENSIONS:
        return raw_bytes.decode("utf-8", errors="replace")

    if suffix == ".pdf" and PdfReader is not None:
        reader = PdfReader(io.BytesIO(raw_bytes))
        return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)

    if suffix == ".docx" and Document is not None:
        document = Document(io.BytesIO(raw_bytes))
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()

    if suffix == ".csv":
        text = raw_bytes.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        return "\n".join(", ".join(row) for row in reader)

    if content_type == "application/json":
        payload = json.loads(raw_bytes.decode("utf-8", errors="replace"))
        return json.dumps(payload, indent=2)

    return raw_bytes.decode("utf-8", errors="replace")


def serialize_file(record: StoredFile) -> dict:
    return {
        "id": record.id,
        "session_id": record.session_id,
        "scope": record.scope,
        "filename": record.filename,
        "title": record.title,
        "content_type": record.content_type,
        "byte_size": record.byte_size,
        "chunk_count": record.chunk_count,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def read_file_excerpt(
    record: StoredFile,
    *,
    start_char: int = 0,
    num_chars: int = MAX_FILE_READ_CHARS,
) -> dict:
    text = Path(record.text_path).read_text() if Path(record.text_path).exists() else ""
    start = max(0, start_char)
    end = min(len(text), start + max(1, num_chars))
    return {
        "file_id": record.id,
        "file_name": record.filename,
        "start_char": start,
        "end_char": end,
        "content": text[start:end],
        "preview": text[start:end][:400],
    }


async def save_upload(
    *,
    db_session: AsyncSession,
    upload: UploadFile,
    scope: str,
    session_id: str | None,
    retrieval_index: LocalRetrievalIndex,
    llm_base_url: str,
    embedding_model: str,
) -> StoredFile:
    ensure_app_dirs()
    file_id = new_id()
    directory = FILES_DIR / file_id
    directory.mkdir(parents=True, exist_ok=True)

    raw_bytes = await upload.read()
    original_name = upload.filename or "untitled.txt"
    original_path = directory / original_name
    original_path.write_bytes(raw_bytes)

    try:
        extracted = extract_text(
            filename=original_name,
            content_type=upload.content_type,
            raw_bytes=raw_bytes,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}") from exc

    text_path = directory / "extracted.txt"
    text_path.write_text(extracted)

    record = StoredFile(
        id=file_id,
        session_id=session_id,
        scope=scope,
        filename=original_name,
        title=safe_title(original_name),
        content_type=upload.content_type,
        byte_size=len(raw_bytes),
        storage_path=str(original_path),
        text_path=str(text_path),
        chunk_count=0,
    )
    record.chunk_count = await retrieval_index.upsert_file(
        file_id=record.id,
        title=record.title,
        source=record.filename,
        text=extracted,
        base_url=llm_base_url,
        embedding_model=embedding_model,
    )

    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record


async def get_file_or_404(db_session: AsyncSession, file_id: str) -> StoredFile:
    record = await db_session.scalar(select(StoredFile).where(StoredFile.id == file_id))
    if record is None:
        raise HTTPException(status_code=404, detail="File not found")
    return record
