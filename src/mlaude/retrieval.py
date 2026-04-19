from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import ollama

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
    tokens: list[str] = field(default_factory=list)
    embedding: list[float] | None = None


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


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _lexical_score(query_terms: list[str], haystack_terms: list[str], *, query: str, title: str, text: str) -> float:
    if not query_terms or not haystack_terms:
        return 0.0

    overlap = sum(1 for term in query_terms if term in haystack_terms)
    if overlap == 0:
        return 0.0

    phrase_bonus = 0.35 if query.lower() in text.lower() else 0.0
    title_bonus = 0.15 if any(term in title.lower() for term in query_terms) else 0.0
    density = overlap / max(len(set(haystack_terms)), 1)
    return overlap + phrase_bonus + title_bonus + math.sqrt(density)


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

    async def _embed_texts(
        self,
        *,
        base_url: str,
        embedding_model: str,
        texts: list[str],
    ) -> list[list[float] | None]:
        if not embedding_model.strip():
            return [None for _ in texts]

        client = ollama.AsyncClient(host=base_url)
        response = await client.embed(model=embedding_model, input=texts)
        embeddings = [list(values) for values in response.embeddings]
        if len(embeddings) != len(texts):
            return [None for _ in texts]
        return embeddings

    async def upsert_file(
        self,
        *,
        file_id: str,
        title: str,
        source: str,
        text: str,
        base_url: str,
        embedding_model: str,
    ) -> int:
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

        embeddings: list[list[float] | None] = [None for _ in built_chunks]
        if built_chunks:
            try:
                embeddings = await self._embed_texts(
                    base_url=base_url,
                    embedding_model=embedding_model,
                    texts=[
                        f"{chunk.title}\n{chunk.section}\n{chunk.text}" for chunk in built_chunks
                    ],
                )
            except Exception:
                embeddings = [None for _ in built_chunks]

        for chunk, embedding in zip(built_chunks, embeddings, strict=False):
            chunk.tokens = _tokenize(f"{chunk.title} {chunk.section} {chunk.text}")
            chunk.embedding = embedding

        self._chunks.extend(built_chunks)
        self._persist()
        return len(built_chunks)

    def remove_file(self, file_id: str) -> None:
        self._chunks = [chunk for chunk in self._chunks if chunk.file_id != file_id]
        self._persist()

    async def search(
        self,
        *,
        query: str,
        base_url: str,
        embedding_model: str,
        allowed_file_ids: set[str] | None = None,
        limit: int = MAX_SEARCH_RESULTS,
    ) -> list[dict]:
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        query_embedding: list[float] | None = None
        try:
            embedded = await self._embed_texts(
                base_url=base_url,
                embedding_model=embedding_model,
                texts=[query],
            )
            query_embedding = embedded[0]
        except Exception:
            query_embedding = None

        candidates = [
            chunk
            for chunk in self._chunks
            if allowed_file_ids is None or chunk.file_id in allowed_file_ids
        ]

        scored: list[tuple[float, float, float, ChunkRecord]] = []
        for chunk in candidates:
            haystack_terms = chunk.tokens or _tokenize(f"{chunk.title} {chunk.section} {chunk.text}")
            lexical = _lexical_score(
                query_terms,
                haystack_terms,
                query=query,
                title=chunk.title,
                text=chunk.text,
            )
            semantic = (
                _cosine_similarity(query_embedding, chunk.embedding)
                if query_embedding is not None and chunk.embedding is not None
                else 0.0
            )
            if lexical <= 0 and semantic < 0.15:
                continue

            score = lexical * 0.65 + max(semantic, 0.0) * 2.5
            scored.append((score, lexical, semantic, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)

        merged: list[dict] = []
        seen: set[str] = set()
        for score, lexical, semantic, chunk in scored:
            if len(merged) >= limit:
                break
            merge_key = f"{chunk.file_id}:{chunk.section}"
            if merge_key in seen:
                continue

            sibling_chunks = [
                candidate
                for _, _, _, candidate in scored
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
                    "source_kind": "file_excerpt",
                    "section": chunk.section,
                    "content": full_text[:3200],
                    "preview": full_text[:280],
                    "query": query,
                    "score": round(score, 3),
                    "retrieval_score": round(score, 3),
                    "lexical_score": round(lexical, 3),
                    "semantic_score": round(semantic, 3),
                    "fetched_at": None,
                    "extract_status": "complete",
                }
            )
            seen.add(merge_key)

        return merged

    async def rerank_evidence(
        self,
        *,
        query: str,
        documents: list[dict],
        base_url: str,
        embedding_model: str,
        limit: int = MAX_SEARCH_RESULTS,
    ) -> list[dict]:
        if not documents:
            return []

        query_terms = _tokenize(query)
        query_embedding: list[float] | None = None
        document_embeddings: list[list[float] | None] = [None for _ in documents]

        try:
            embeddings = await self._embed_texts(
                base_url=base_url,
                embedding_model=embedding_model,
                texts=[query, *[
                    f"{document.get('title', '')}\n{document.get('section', '')}\n{document.get('content', '')}"
                    for document in documents
                ]],
            )
            query_embedding = embeddings[0]
            document_embeddings = embeddings[1:]
        except Exception:
            query_embedding = None
            document_embeddings = [None for _ in documents]

        reranked: list[dict] = []
        for index, document in enumerate(documents):
            haystack = f"{document.get('title', '')} {document.get('section', '')} {document.get('content', '')}"
            haystack_terms = _tokenize(haystack)
            lexical = _lexical_score(
                query_terms,
                haystack_terms,
                query=query,
                title=document.get("title", ""),
                text=document.get("content", ""),
            )
            semantic = (
                _cosine_similarity(query_embedding, document_embeddings[index])
                if query_embedding is not None and document_embeddings[index] is not None
                else 0.0
            )
            prior = float(document.get("retrieval_score", document.get("score", 0.0)) or 0.0)
            freshness_bonus = 0.1 if document.get("source_kind") == "web_page" else 0.0
            score = lexical * 0.45 + max(semantic, 0.0) * 2.1 + prior * 0.35 + freshness_bonus
            if score <= 0:
                continue
            reranked.append(
                {
                    **document,
                    "score": round(score, 3),
                    "retrieval_score": round(score, 3),
                    "lexical_score": round(lexical, 3),
                    "semantic_score": round(semantic, 3),
                }
            )

        reranked.sort(key=lambda item: item["score"], reverse=True)

        deduped: list[dict] = []
        seen: set[str] = set()
        for document in reranked:
            dedupe_key = (
                document.get("file_id")
                or document.get("source")
                or document.get("document_id")
            )
            if dedupe_key in seen:
                continue
            seen.add(str(dedupe_key))
            deduped.append(document)
            if len(deduped) >= limit:
                break

        return deduped
