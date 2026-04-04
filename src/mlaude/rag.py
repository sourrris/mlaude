"""RAG knowledge base — ChromaDB + Ollama nomic-embed-text (v2 pipeline)."""

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

# Cosine distance thresholds — LOWER = more similar, HIGHER = more lenient (allows weaker matches)
# Behavioral/about chunks: 0.55 — worth injecting even on weaker signal
# Factual/general chunks: 0.45 — only inject when clearly relevant
_THRESHOLD_BEHAVIORAL = 0.55
_THRESHOLD_DEFAULT = 0.45


def _detect_source_type(relative_path: str) -> str:
    """Infer source type from the file's directory within the knowledge base."""
    parts = Path(relative_path).parts
    if not parts:
        return "general"
    top = parts[0].lower()
    if top == "about":
        return "about"
    if top in ("interests", "interest"):
        return "interest"
    if top in ("behavior", "behaviour"):
        return "behavior"
    return "general"


def _chunk_markdown_v2(text: str, source: str, source_type: str) -> list[dict]:
    """Split markdown into chunks with heading hierarchy preserved as context prefix.

    Every chunk is prefixed with its page title and section heading so that
    chunks retrieved out of context still tell the LLM where they came from.
    Format: "[{source_type}] {page_title} > {section_heading}\n\n{content}"
    """
    chunks = []

    # Extract top-level # heading as page title
    title_match = re.match(r"^#\s+(.+)$", text.strip(), re.MULTILINE)
    page_title = title_match.group(1).strip() if title_match else Path(source).stem.replace("_", " ").title()

    # Split on ## headings
    sections = re.split(r"\n(?=## )", text)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Extract ## heading for this section
        section_heading_match = re.match(r"^##\s+(.+)$", section, re.MULTILINE)
        if section_heading_match:
            section_heading = section_heading_match.group(1).strip()
        else:
            section_heading = ""

        prefix = f"[{source_type}] {page_title}"
        if section_heading:
            prefix = f"{prefix} > {section_heading}"

        # If section is too long, split on double newlines
        words = section.split()
        if len(words) > CHUNK_MAX_TOKENS:
            paragraphs = re.split(r"\n{2,}", section)
            current = ""
            for para in paragraphs:
                combined = f"{current}\n\n{para}" if current else para
                if len(combined.split()) > CHUNK_MAX_TOKENS and current:
                    chunks.append({
                        "text": f"{prefix}\n\n{current.strip()}",
                        "source": source,
                        "source_type": source_type,
                    })
                    current = para
                else:
                    current = combined
            if current.strip():
                chunks.append({
                    "text": f"{prefix}\n\n{current.strip()}",
                    "source": source,
                    "source_type": source_type,
                })
        else:
            chunks.append({
                "text": f"{prefix}\n\n{section}",
                "source": source,
                "source_type": source_type,
            })

    return chunks


def _doc_id(source: str, idx: int) -> str:
    """Deterministic chunk ID."""
    return hashlib.md5(f"{source}:{idx}".encode()).hexdigest()[:12]


def _adaptive_n(query: str) -> int:
    """Return number of chunks to retrieve based on query complexity."""
    if len(query.split()) > 20 or query.count("?") > 1:
        return 7
    return 4


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
            source_type = _detect_source_type(relative)
            text = path.read_text()
            chunks = _chunk_markdown_v2(text, relative, source_type)
            all_chunks.extend(chunks)

        if not all_chunks:
            return 0

        ids = [_doc_id(c["source"], i) for i, c in enumerate(all_chunks)]
        documents = [c["text"] for c in all_chunks]
        metadatas = [{"source": c["source"], "source_type": c["source_type"]} for c in all_chunks]

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

    def query_v2(self, text: str, conversation_context: str | None = None) -> list[dict]:
        """Return relevant chunks with source_type metadata.

        Builds a composite query from the current message + recent conversation context
        (catches cases like "what about the thermodynamics angle?" where prior turn
        establishes the topic). Applies per-source-type thresholds.

        Each dict: {"text": str, "source": str, "source_type": str, "score": float}
        Lower score = more similar (ChromaDB cosine distance).
        """
        if self.collection.count() == 0:
            return []

        composite_query = text
        if conversation_context:
            composite_query = f"{text} {conversation_context}"

        n = _adaptive_n(text)

        try:
            results = self.collection.query(
                query_texts=[composite_query],
                n_results=min(n, self.collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning("RAG query failed: %s", e)
            return []

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        chunks = []
        for doc, meta, dist in zip(docs, metas, distances):
            if not doc:
                continue
            source_type = meta.get("source_type", "general")
            threshold = _THRESHOLD_BEHAVIORAL if source_type in ("about", "behavior") else _THRESHOLD_DEFAULT
            if dist <= threshold:
                chunks.append({
                    "text": doc,
                    "source": meta.get("source", "?"),
                    "source_type": source_type,
                    "score": dist,
                })

        return chunks

    def query(self, text: str, n: int = 5) -> list[dict]:
        """Backwards-compatible query. Delegates to query_v2."""
        return self.query_v2(text)
