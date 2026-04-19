from __future__ import annotations

from pathlib import Path

import pytest

from mlaude import retrieval


@pytest.mark.asyncio
async def test_hybrid_retrieval_returns_scored_file_excerpt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(retrieval, "INDEX_DIR", tmp_path)

    async def fake_embed_texts(self, *, base_url: str, embedding_model: str, texts: list[str]):  # noqa: ARG001
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "orbital mechanics" in lowered:
                vectors.append([1.0, 0.0])
            elif "cooking recipes" in lowered:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([0.8, 0.2])
        return vectors

    monkeypatch.setattr(retrieval.LocalRetrievalIndex, "_embed_texts", fake_embed_texts)

    index = retrieval.LocalRetrievalIndex()
    await index.upsert_file(
        file_id="file-a",
        title="Orbital Mechanics",
        source="orbital.md",
        text="# Basics\nOrbital mechanics explains transfer windows and delta-v budgets.",
        base_url="http://127.0.0.1:11434",
        embedding_model="nomic-embed-text",
    )
    await index.upsert_file(
        file_id="file-b",
        title="Recipes",
        source="food.md",
        text="# Pasta\nCooking recipes focus on sauces and timing.",
        base_url="http://127.0.0.1:11434",
        embedding_model="nomic-embed-text",
    )

    results = await index.search(
        query="orbital mechanics transfer window",
        base_url="http://127.0.0.1:11434",
        embedding_model="nomic-embed-text",
        allowed_file_ids={"file-a", "file-b"},
    )

    assert results
    assert results[0]["title"] == "Orbital Mechanics"
    assert results[0]["source_kind"] == "file_excerpt"
    assert results[0]["retrieval_score"] >= results[0]["score"] - 0.001


@pytest.mark.asyncio
async def test_rerank_evidence_prefers_semantic_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(retrieval, "INDEX_DIR", tmp_path)

    async def fake_embed_texts(self, *, base_url: str, embedding_model: str, texts: list[str]):  # noqa: ARG001
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "latest launch manifest" in lowered:
                vectors.append([1.0, 0.0])
            elif "local mission note" in lowered:
                vectors.append([0.9, 0.1])
            else:
                vectors.append([0.1, 0.9])
        return vectors

    monkeypatch.setattr(retrieval.LocalRetrievalIndex, "_embed_texts", fake_embed_texts)

    index = retrieval.LocalRetrievalIndex()
    reranked = await index.rerank_evidence(
        query="latest launch manifest",
        base_url="http://127.0.0.1:11434",
        embedding_model="nomic-embed-text",
        documents=[
            {
                "document_id": "local:1",
                "file_id": "a",
                "title": "Local Mission Note",
                "source": "mission.md",
                "source_kind": "file_excerpt",
                "section": "Summary",
                "content": "Local mission note with prep tasks.",
                "preview": "Local mission note with prep tasks.",
                "score": 0.6,
                "retrieval_score": 0.6,
            },
            {
                "document_id": "web:1",
                "file_id": None,
                "title": "Latest Launch Manifest",
                "source": "https://example.com/manifest",
                "source_kind": "web_page",
                "section": "Fetched Page",
                "content": "Latest launch manifest with fresh schedule updates.",
                "preview": "Latest launch manifest with fresh schedule updates.",
                "score": 0.5,
                "retrieval_score": 0.5,
            },
        ],
    )

    assert reranked
    assert reranked[0]["title"] == "Latest Launch Manifest"
