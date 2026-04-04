"""RAG knowledge base — ChromaDB + Ollama nomic-embed-text."""

import hashlib
import logging
import re
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

from mlaude.config import CHROMADB_DIR, EMBEDDING_MODEL, KNOWLEDGE_DIR, OLLAMA_URL

logger = logging.getLogger("mlaude")

COLLECTION_NAME = "knowledge"
CHUNK_MAX_TOKENS = 500  # approximate, split on sections/paragraphs
RELEVANCE_THRESHOLD = 0.45  # cosine distance — lower is more similar, discard above this


def _chunk_markdown(text: str, source: str) -> list[dict]:
    """Split markdown text into chunks by ## headings or double newlines."""
    chunks = []

    # Split on ## headings first
    sections = re.split(r"\n(?=## )", text)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # If a section is too long, split on double newlines
        words = section.split()
        if len(words) > CHUNK_MAX_TOKENS:
            paragraphs = re.split(r"\n{2,}", section)
            current = ""
            for para in paragraphs:
                if len((current + "\n\n" + para).split()) > CHUNK_MAX_TOKENS and current:
                    chunks.append({"text": current.strip(), "source": source})
                    current = para
                else:
                    current = f"{current}\n\n{para}" if current else para
            if current.strip():
                chunks.append({"text": current.strip(), "source": source})
        else:
            chunks.append({"text": section, "source": source})

    return chunks


def _doc_id(source: str, idx: int) -> str:
    """Deterministic ID for a chunk."""
    h = hashlib.md5(f"{source}:{idx}".encode()).hexdigest()[:12]
    return f"{h}"


class KnowledgeBase:
    def __init__(self):
        CHROMADB_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(CHROMADB_DIR))
        self.ef = OllamaEmbeddingFunction(
            url=OLLAMA_URL,
            model_name=EMBEDDING_MODEL,
        )
        self.collection = self.client.get_or_create_collection(
            COLLECTION_NAME, embedding_function=self.ef
        )

    def index_all(self) -> int:
        """Index all .md files from KNOWLEDGE_DIR. Returns count of chunks indexed."""
        if not KNOWLEDGE_DIR.exists():
            return 0

        md_files = list(KNOWLEDGE_DIR.rglob("*.md"))
        if not md_files:
            logger.info("No knowledge files found in %s", KNOWLEDGE_DIR)
            return 0

        # Clear existing collection and re-index
        try:
            self.client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            COLLECTION_NAME, embedding_function=self.ef
        )

        all_chunks: list[dict] = []
        for path in md_files:
            relative = str(path.relative_to(KNOWLEDGE_DIR))
            text = path.read_text()
            chunks = _chunk_markdown(text, relative)
            all_chunks.extend(chunks)

        if not all_chunks:
            return 0

        ids = [_doc_id(c["source"], i) for i, c in enumerate(all_chunks)]
        documents = [c["text"] for c in all_chunks]
        metadatas = [{"source": c["source"]} for c in all_chunks]

        # ChromaDB has a batch limit, upsert in batches of 100
        batch_size = 100
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            self.collection.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )

        logger.info("Indexed %d chunks from %d files", len(all_chunks), len(md_files))
        return len(all_chunks)

    def query(self, text: str, n: int = 5) -> list[dict]:
        """Return top-n relevant chunks with source and distance score.

        Each dict: {"text": str, "source": str, "score": float}
        Lower score = more similar (ChromaDB cosine distance).
        """
        if self.collection.count() == 0:
            return []
        try:
            results = self.collection.query(
                query_texts=[text],
                n_results=min(n, self.collection.count()),
                include=["documents", "metadatas", "distances"],
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            return [
                {"text": doc, "source": meta.get("source", "?"), "score": dist}
                for doc, meta, dist in zip(docs, metas, distances)
                if doc and dist <= RELEVANCE_THRESHOLD
            ]
        except Exception as e:
            logger.warning("RAG query failed: %s", e)
            return []
