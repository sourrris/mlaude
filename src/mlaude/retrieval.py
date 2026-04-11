from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from mlaude.settings import INDEX_DIR, MAX_SEARCH_RESULTS, ensure_app_dirs


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
SECTION_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "what",
    "which",
    "is",
    "are",
    "be",
    "about",
    "from",
}


@dataclass
class ChunkRecord:
    document_id: str
    file_id: str
    title: str
    source: str
    section: str
    chunk_index: int
    text: str
    preview: str


def _tokenize(value: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(value)
        if token and token.lower() not in STOPWORDS
    ]


def _heading_sections(text: str, fallback_title: str) -> list[tuple[str, str]]:
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return [(fallback_title, text)]

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = match.group(1).strip()
        sections.append((heading, text[start:end].strip()))
    return sections or [(fallback_title, text)]


def _chunk_section(
    *,
    file_id: str,
    title: str,
    source: str,
    section_name: str,
    text: str,
) -> list[ChunkRecord]:
    paragraphs = [segment.strip() for segment in re.split(r"\n{2,}", text) if segment.strip()]
    chunks: list[ChunkRecord] = []
    current: list[str] = []
    chunk_index = 0

    for paragraph in paragraphs:
        candidate = "\n\n".join([*current, paragraph]).strip()
        if len(candidate) > 1400 and current:
            value = "\n\n".join(current).strip()
            chunks.append(
                ChunkRecord(
                    document_id=f"{file_id}:{chunk_index}",
                    file_id=file_id,
                    title=title,
                    source=source,
                    section=section_name,
                    chunk_index=chunk_index,
                    text=value,
                    preview=value[:280],
                )
            )
            chunk_index += 1
            current = [paragraph]
        else:
            current.append(paragraph)

    if current:
        value = "\n\n".join(current).strip()
        chunks.append(
            ChunkRecord(
                document_id=f"{file_id}:{chunk_index}",
                file_id=file_id,
                title=title,
                source=source,
                section=section_name,
                chunk_index=chunk_index,
                text=value,
                preview=value[:280],
            )
        )

    if not chunks and text.strip():
        chunks.append(
            ChunkRecord(
                document_id=f"{file_id}:0",
                file_id=file_id,
                title=title,
                source=source,
                section=section_name,
                chunk_index=0,
                text=text.strip(),
                preview=text.strip()[:280],
            )
        )

    return chunks


class LocalRetrievalIndex:
    def __init__(self) -> None:
        ensure_app_dirs()
        self.index_path = INDEX_DIR / "chunks.json"
        self._chunks: list[ChunkRecord] = []
        self._load()

    def _load(self) -> None:
        if not self.index_path.exists():
            self._chunks = []
            return

        payload = json.loads(self.index_path.read_text())
        self._chunks = [ChunkRecord(**chunk) for chunk in payload.get("chunks", [])]

    def _persist(self) -> None:
        payload = {"chunks": [asdict(chunk) for chunk in self._chunks]}
        self.index_path.write_text(json.dumps(payload, indent=2))

    def upsert_file(self, *, file_id: str, title: str, source: str, text: str) -> int:
        self._chunks = [chunk for chunk in self._chunks if chunk.file_id != file_id]

        built_chunks: list[ChunkRecord] = []
        for section_name, section_text in _heading_sections(text, title):
            built_chunks.extend(
                _chunk_section(
                    file_id=file_id,
                    title=title,
                    source=source,
                    section_name=section_name,
                    text=section_text,
                )
            )

        self._chunks.extend(built_chunks)
        self._persist()
        return len(built_chunks)

    def remove_file(self, file_id: str) -> None:
        self._chunks = [chunk for chunk in self._chunks if chunk.file_id != file_id]
        self._persist()

    def search(
        self,
        *,
        query: str,
        allowed_file_ids: set[str] | None = None,
        limit: int = MAX_SEARCH_RESULTS,
    ) -> list[dict]:
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        candidates = [
            chunk
            for chunk in self._chunks
            if allowed_file_ids is None or chunk.file_id in allowed_file_ids
        ]
        scored: list[tuple[float, ChunkRecord]] = []
        for chunk in candidates:
            haystack_terms = _tokenize(f"{chunk.title} {chunk.section} {chunk.text}")
            if not haystack_terms:
                continue

            overlap = sum(1 for term in query_terms if term in haystack_terms)
            if overlap == 0:
                continue

            phrase_bonus = 0.35 if query.lower() in chunk.text.lower() else 0.0
            title_bonus = 0.15 if any(term in chunk.title.lower() for term in query_terms) else 0.0
            density = overlap / max(len(set(haystack_terms)), 1)
            score = overlap + phrase_bonus + title_bonus + math.sqrt(density)
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)

        merged: list[dict] = []
        seen: set[str] = set()
        for score, chunk in scored:
            if len(merged) >= limit:
                break
            merge_key = f"{chunk.file_id}:{chunk.section}"
            if merge_key in seen:
                continue
            sibling_chunks = [
                candidate
                for _, candidate in scored
                if candidate.file_id == chunk.file_id and candidate.section == chunk.section
            ]
            sibling_chunks.sort(key=lambda candidate: candidate.chunk_index)
            full_text = "\n\n".join(candidate.text for candidate in sibling_chunks)
            merged.append(
                {
                    "document_id": chunk.document_id,
                    "file_id": chunk.file_id,
                    "title": chunk.title,
                    "source": chunk.source,
                    "section": chunk.section,
                    "content": full_text[:3200],
                    "preview": full_text[:280],
                    "score": round(score, 3),
                }
            )
            seen.add(merge_key)

        return merged
