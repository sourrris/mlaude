# Blueprint: Behavioral Identity + RAG v2
**Project:** mlaude  
**Objective:** Add behavioral/personality identity elements about the user (interests: history, politics, physics, philosophy, science, astrophysics) using SOUL.md + structured knowledge base + enhanced RAG — without fine-tuning the LLM.  
**Constraint:** No LLM fine-tuning (hardware limitation). Everything runs through prompt engineering, structured knowledge files, and smarter retrieval.  
**Base branch:** `main`  
**Status:** DRAFT — 2026-04-04

---

## Architecture Overview

```
SOUL.md (behavioral identity)
    ↓
knowledge/ templates (interest/about seed files) → ~/.mlaude/knowledge/ (RAG-indexed)
    ↓
Enhanced RAG (conversation-aware retrieval + source routing)
    ↓
Hierarchical prompt injection (behavior / interests / factual in separate named sections)
    ↓
Memory schema (tracks interests, discussion style, knowledge depth)
```

The core idea: without fine-tuning, you replicate behavioral adaptation by (1) richly describing how the user thinks/talks in SOUL.md, (2) storing interest-domain profiles in the RAG knowledge base so the LLM has context when those topics arise, (3) improving retrieval so the right chunks surface at the right time, and (4) structuring the system prompt so behavioral context is clearly separated from factual knowledge.

---

## Steps

```
Step 1  Step 2  Step 3   ← parallel: can be done simultaneously
  ↓       ↓       ↓
          Step 4  ← depends on Steps 1, 2, 3 merged
```
Note: Step 2 has a soft dependency on Step 1 for tone consistency in knowledge files. Technically parallel but recommended order is 1 before 2.

| Step | Name | Branch | Files Touched | Depends On | Model |
|------|------|--------|---------------|-----------|-------|
| 1 | SOUL.md Behavioral Overhaul | `feature/soul-behavioral-identity` | `SOUL.md` | — | default |
| 2 | Knowledge Templates + RAG v2 | `feature/knowledge-templates-rag-v2` | `knowledge/` dir, `rag.py`, `config.py`, `server.py`, `observer.py` | — (soft: do after Step 1 for tone consistency) | opus |
| 3 | Memory Schema Expansion | `feature/memory-schema-interests` | `memory.py`, `tools/memory_tool.py` | — | default |
| 4 | Prompt Architecture v2 | `feature/prompt-architecture-v2` | `llm.py`, `server.py` | Steps 1, 2, 3 merged | opus |

---

## Step 1 — SOUL.md Behavioral Overhaul

### Context brief
`SOUL.md` is loaded at every request as the LLM's system prompt identity. It currently has 37 lines of generic description. This step rewrites it into a rich behavioral document that captures:
- Who Mlaude is responding *to* (not just what it is)
- How the user talks about intellectual topics — their register, depth expectations, conversational rhythm
- Domain markers for the user's interest areas
- Anti-patterns the LLM must avoid
- Response format preferences

No code changes. SOUL.md is read by `llm.py:load_system_prompt()` which does `SOUL_PATH.read_text()`.

### Task list
1. Open `SOUL.md` and understand current structure
2. Rewrite with the following sections:
   - `## Identity` — what Mlaude is, running locally on their MacBook
   - `## The User` — brief profile: intellectually curious, comfortable across physics/history/philosophy/politics/science/astrophysics; expects depth, not surface summaries; talks casually about complex topics
   - `## How They Talk` — uses first principles, likes tracing ideas back, comfortable with nuance, doesn't need definitions of common terms, will push back if something is oversimplified
   - `## Conversation Style` — direct exchange, not lecture format; they'll ask follow-ups; OK to say "I don't know"; debates are welcome; no moralizing
   - `## Domains of Interest` — list each domain with a short behavioral note (e.g., "Physics & Astrophysics: they think in models and mechanisms, not just facts; expects engagement with the underlying math/structure when relevant")
   - `## Response Format` — concise by default, can go long when depth is warranted; no bullet lists for conceptual discussions; code blocks for code; no "Great question!" openers
   - `## Capabilities` — tools available (web_search, update_memory), RAG knowledge base, memory persistence
   - `## Tool Use Rules` — existing when-to-search / when-to-remember logic, kept intact
3. Keep total file under 150 lines — this is injected into every request; token budget matters

### Verification
- Visually inspect the new SOUL.md for tone consistency
- Start `mlaude` and ask a physics question — verify response doesn't over-explain basics
- Ask a history/politics question — verify it engages at intellectual peer level
- `uv run mlaude` (Ollama must be running with `qwen2.5:14b-instruct-q4_K_M`)

### Exit criteria
- SOUL.md covers all 6 interest domains with behavioral notes
- Token budget: new SOUL.md is ≤150 lines / ~1500 tokens
- No regression in generic chat capability

### Rollback
`git checkout HEAD -- SOUL.md`

---

## Step 2 — Knowledge Templates + RAG Pipeline v2

### Context brief
This step does two things that are tightly coupled: (1) create the interest/behavioral knowledge files that get indexed into ChromaDB, and (2) upgrade the RAG pipeline to retrieve them better.

**Knowledge file strategy:** Files live in `knowledge/` at repo root (version-controlled templates). On startup, `server.py` copies any files from `knowledge/` to `~/.mlaude/knowledge/` that don't already exist (never overwrites user edits). ChromaDB indexes everything in `~/.mlaude/knowledge/`.

**RAG v2 improvements:**
- **Conversation-aware composite query**: build retrieval query from `current message + last 2 turns` (catches context from prior exchanges, e.g., "what about the thermodynamics angle?" when previous turn was about stellar formation)
- **Better chunking**: preserve heading hierarchy as context prefix on every chunk (prevents chunks that start mid-section with no context)
- **Source-type tagging**: chunks get metadata `source_type: behavior | interest | about | general` based on which subdirectory the file is in
- **Adaptive result count**: `n=3` for short/simple queries, `n=7` for compound/multi-topic queries (heuristic: count `?` marks and word count)
- **Threshold tuning**: `behavior/` and `about/` chunks use threshold `0.55` (more lenient — behavioral context is worth injecting even on weaker signal); factual chunks stay at `0.45`

**File structure to create:**
```
knowledge/                    ← repo root (templates, committed to git)
├── about/
│   ├── profile.md            ← who the user is, background, interests overview
│   └── communication_style.md ← how they talk, discussion preferences
└── interests/
    ├── physics_astrophysics.md
    ├── history_politics.md
    └── philosophy_science.md
```

Each file is intentionally a **behavioral profile**, not a fact dump. The goal is: when these chunks are retrieved and injected into the system prompt, the LLM knows *how the user thinks about this domain*, not just that the domain exists.

### Task list

**Knowledge files (create these first):**

1. Create `knowledge/about/profile.md`:
   - Who they are (engineer/technical background, self-directed learner)
   - Cross-domain intellectual style
   - What they find interesting vs what bores them
   - Leave deliberate `[TODO: fill in]` placeholders for personal details

2. Create `knowledge/about/communication_style.md`:
   - Direct communication, no pleasantries
   - Comfortable with ambiguity and open questions
   - Appreciates when the AI admits uncertainty
   - Likes analogies and mental models, not definitions
   - Expects the AI to push back if the user's framing is wrong
   - Dislikes: over-qualification, hedging, excessive caveats

3. Create `knowledge/interests/physics_astrophysics.md`:
   - Interest areas: quantum mechanics, general relativity, cosmology, black holes, stellar physics, entropy/thermodynamics
   - Engagement style: thinks in mechanisms and models; interested in "why" not just "what"
   - Comfortable with equations being mentioned (doesn't need full derivations)
   - Finds connections between physics and philosophy of science interesting
   - Leave `[TODO: add specific papers/concepts you're working through]`

4. Create `knowledge/interests/history_politics.md`:
   - Interest areas: geopolitics, political theory, historical causality, empire cycles, modern history
   - Engagement style: likes systemic analysis over surface narrative
   - Interested in how incentives/power structures shape outcomes
   - Not interested in partisan framing
   - Leave `[TODO: add specific eras, regions, or thinkers you follow]`

5. Create `knowledge/interests/philosophy_science.md`:
   - Interest areas: philosophy of science, epistemology, metaphysics, rationalism vs empiricism, consciousness
   - Engagement style: comfortable with abstract reasoning; likes tracing implications
   - Interested in how science and philosophy interact
   - Leave `[TODO: add specific philosophers or problems you're exploring]`

6. Create `knowledge/README.md` — explains the structure and how to customize

**Code changes:**

7. Update `config.py`:
   - Add `KNOWLEDGE_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"`

8. Update `server.py` lifespan function:
   - After `ensure_dirs()`, call a new `_copy_knowledge_templates()` function
   - `_copy_knowledge_templates()`: iterate `KNOWLEDGE_TEMPLATES_DIR.rglob("*.md")`, copy each to `~/.mlaude/knowledge/<relative_path>` only if it doesn't exist yet (never overwrite)
   - Log how many templates were copied

9. Rewrite `rag.py` with RAG v2:

   a. **`_chunk_markdown_v2(text, source, source_type)`**: improved chunker
      - Extract the top-level `# heading` if present and store as `page_title`
      - For each `## section`: store section heading as a prefix on every sub-chunk
      - Format: `[source_type] {page_title} > {section_heading}\n\n{chunk_content}`
      - This way every chunk has context about where it came from
      
   b. **`_detect_source_type(relative_path)`**: 
      - `about/` → `"about"`
      - `interests/` → `"interest"`
      - `behavior/` → `"behavior"` (for future use)
      - everything else → `"general"`

   c. Update `RagChunk` in `observer.py` to add `source_type: str = "general"` field, and update `to_ws_payload()` to include `source_type` in chunk dicts. (Moved here from the old task 11 so `server.py` can immediately use it when creating `RagChunk` objects.)

   d. **`_adaptive_n(query)`**:
      - `len(query.split()) > 20` or `query.count("?") > 1` → return 7
      - else → return 4

   d. **`KnowledgeBase.index_all()`**: update to:
      - Pass `source_type` to `_chunk_markdown_v2`
      - Store `source_type` in chunk metadata alongside `source`
      - Keep batch upsert logic

   e. **`KnowledgeBase.query_v2(text, conversation_context=None)`**:
      - Build composite query: `text + (" " + conversation_context if conversation_context else "")`
      - `n = _adaptive_n(text)`
      - Run ChromaDB query with `include=["documents", "metadatas", "distances"]`
      - Post-filter by source type (note: ChromaDB cosine distance — **lower = more similar, higher threshold = more lenient / allows weaker matches**):
        - `behavior` and `about` chunks: pass if `dist <= 0.55` (more lenient — behavioral context worth injecting on weaker signal)
        - all other chunks: pass if `dist <= 0.45` (stricter — factual chunks only when clearly relevant)
      - Return list of dicts: `{"text", "source", "source_type", "score"}`

   f. Keep old `KnowledgeBase.query()` for backwards compat, have it call `query_v2(text)`

   g. Update `RELEVANCE_THRESHOLD = 0.45` at module level (still used as default fallback)

10. Update `server.py` message handler:
    - Build `conversation_context` from last 2 turns of `history` before calling RAG:
      ```python
      recent = [m["content"] for m in history[-4:] if m["role"] in ("user", "assistant")][-4:]
      conv_ctx = " ".join(recent[-2:]) if len(recent) >= 2 else None
      ```
    - Call `kb.query_v2(content, conversation_context=conv_ctx)` instead of `kb.query(content)`
    - Update `RagChunk(...)` construction to include `source_type=c.get("source_type", "general")` (RagChunk now has this field from task 9c above)

### Verification
```bash
# Start server
uv run mlaude

# Check that knowledge templates were copied
ls ~/.mlaude/knowledge/about/
ls ~/.mlaude/knowledge/interests/

# Check indexing log
# Should see: "Indexed N chunks from 5 files"

# Test conversation-aware retrieval via trace:
# 1. Ask "Tell me about quantum entanglement"
# 2. Follow up: "How does that relate to Bell's theorem?"
# 3. Check the trace panel — RAG should show chunks from physics_astrophysics.md
```

### Exit criteria
- 5 knowledge template files created in `knowledge/` directory
- Templates copied to `~/.mlaude/knowledge/` on first startup (not on restart if already present)
- `query_v2` returns `source_type` metadata per chunk
- Conversation context from prior turns is included in composite retrieval query
- Observer trace shows `source_type` per chunk

### Rollback
```bash
git checkout HEAD -- src/mlaude/rag.py src/mlaude/config.py src/mlaude/server.py
rm -rf knowledge/
# ~/.mlaude/knowledge/ files are user data — don't auto-delete
```

---

## Step 3 — Memory Schema Expansion

### Context brief
`memory.py` manages `~/.mlaude/MEMORY.md` — a structured markdown file injected into every system prompt. Currently has 7 sections covering identity, communication style, work/projects, preferences, people, habits, and notes.

This step adds 3 new sections specifically for intellectual/behavioral tracking:
- `Intellectual Interests` — specific topics, questions, or concepts the user has mentioned caring about
- `Discussion Preferences` — how they like to engage on ideas (discovered over time, e.g., "prefers Socratic discussion for philosophy", "wants code examples for programming concepts")
- `Knowledge Depth` — topics where the user has demonstrated deep knowledge (so the LLM doesn't over-explain)

Also: add `delete_memory_fact(section, fact)` to allow removing outdated facts, and improve duplicate detection to be case-insensitive.

The `update_memory` tool already exists in `tools/` — the new sections just need to be added to `VALID_SECTIONS` and `_DEFAULT_MEMORY`.

### Task list
1. Open `src/mlaude/memory.py`
2. Add to `_DEFAULT_MEMORY`:
   ```
   ## Intellectual Interests
   
   ## Discussion Preferences
   
   ## Knowledge Depth
   ```
3. Add to `VALID_SECTIONS`:
   ```python
   "Intellectual Interests",
   "Discussion Preferences", 
   "Knowledge Depth",
   ```
4. Improve `update_memory` duplicate detection: normalize whitespace and lowercase before comparing (`fact_line.lower().strip()` vs `existing.lower()`)
5. Add `delete_memory_fact(section: str, fact: str) -> str`:
   - Find the section
   - Remove the line `- {fact}` (case-insensitive match)
   - Return status message
6. Export `delete_memory_fact` from module
7. Open `src/mlaude/tools/memory_tool.py` (the `UpdateMemoryTool` class):
   - Update the `description` field to mention the 3 new valid sections: "Intellectual Interests, Discussion Preferences, Knowledge Depth" (so the LLM knows when to use them)
   - Update the `enum` list in the tool's `parameters` schema to include the 3 new sections — this is critical: the schema enum is built from `VALID_SECTIONS` at import time, but only if it's dynamically built. Check if it's hardcoded; if so, add the new sections there too.
   - Add a `DeleteMemoryFactTool` class in the same file using the same `Tool` base pattern: name=`delete_memory_fact`, description, parameters with `section` (enum of VALID_SECTIONS) and `fact` (string)
   - Register `DeleteMemoryFactTool()` in `server.py` lifespan alongside `UpdateMemoryTool()`
8. Check that existing `~/.mlaude/MEMORY.md` files won't be broken: `ensure_memory()` only writes if file doesn't exist, so existing files are safe. New sections will be absent in old files — that's OK, `update_memory` handles missing sections gracefully.

### Verification
```bash
# Run the app
uv run mlaude
# In chat: "Remember that I find quantum field theory fascinating"
# Should call update_memory with section=Intellectual Interests
# Check ~/.mlaude/MEMORY.md to see the new entry
```

### Exit criteria
- 3 new sections in `VALID_SECTIONS` and `_DEFAULT_MEMORY`
- `delete_memory_fact` implemented and exported
- Improved duplicate detection (case-insensitive)
- Existing `~/.mlaude/MEMORY.md` files are not corrupted

### Rollback
`git checkout HEAD -- src/mlaude/memory.py`  
`~/.mlaude/MEMORY.md` is user data — don't touch it.

---

## Step 4 — Prompt Architecture v2

### Context brief
This is the integration step. `llm.py:load_system_prompt()` currently concatenates SOUL + memory + RAG chunks + datetime as flat sections separated by `---`. After Steps 1–3, the RAG chunks now carry `source_type` metadata and there are richer memory sections. This step restructures `load_system_prompt()` to:

1. Inject RAG chunks in **named sections by source type**, not as one block
2. Put behavioral/interest context *before* factual knowledge (higher position in context window = higher attention from LLM)
3. Add a lightweight **topic signal** to the system prompt: if interest chunks were retrieved, prepend "Topics relevant to this conversation: {domains}" — helps the LLM know which behavioral lens to apply
4. Trim low-value content: if no memory has been written yet (default empty template), skip the memory section entirely rather than injecting an empty skeleton

The change is confined to `llm.py` (`load_system_prompt` function signature needs `rag_context` to carry `source_type`). `server.py` already passes `rag_chunks` — just needs to pass the enriched format from Step 2.

**This step depends on Steps 1, 2, 3 being merged** so the new SOUL.md, knowledge chunks with source_type, and new memory sections are all in place.

### Task list
1. Open `src/mlaude/llm.py`, read `load_system_prompt()`
2. Rewrite `load_system_prompt(rag_context=None)`:
   ```
   parts = [soul.strip()]
   
   # Memory — only inject if non-empty (has actual facts beyond section headings)
   if memory has content beyond section headers:
       parts.append("--- About You (Your Memory) ---\n{memory}")
   
   # RAG context — split by source_type
   if rag_context:
       behavior_chunks = [c for c in rag_context if c.get("source_type") in ("about", "behavior")]
       interest_chunks = [c for c in rag_context if c.get("source_type") == "interest"]
       general_chunks  = [c for c in rag_context if c.get("source_type") == "general"]
       
       # Inject in priority order: behavioral first
       if behavior_chunks:
           texts = "\n\n".join(c["text"] for c in behavior_chunks)
           parts.append(f"--- Context About You ---\n{texts}")
       
       if interest_chunks:
           texts = "\n\n".join(c["text"] for c in interest_chunks)
           parts.append(f"--- Your Interest Context ---\n{texts}")
       
       if general_chunks:
           texts = "\n\n".join(c["text"] for c in general_chunks)
           parts.append(f"--- Relevant Knowledge ---\n{texts}")
   
   parts.append(f"Current date and time: {now}")
   return "\n\n".join(parts)
   ```
3. Add `_memory_has_content(memory_text)` helper:
   - Returns True if the memory has any `- ` bullet lines (i.e., actual facts written)
   - Returns False if it's only the empty section template
4. Keep backwards compat: `rag_context` can be `list[dict]` or `None`; dicts may or may not have `source_type` (default to `"general"` if absent)
5. Update the docstring for `load_system_prompt` to describe the new section structure
6. Open `src/mlaude/server.py` — verify `rag_chunks` from `kb.query_v2()` pass `source_type` into `load_system_prompt()`. No changes needed if Step 2 was done correctly (the query already returns `source_type`).

### Verification
```bash
uv run mlaude
# Ask: "What's your take on Penrose's views on consciousness?"
# Expected: 
# - RAG retrieves from philosophy_science.md (source_type=interest)
# - "Your Interest Context" section appears in system prompt
# - Response engages with philosophical depth, not a Wikipedia summary
# Check trace panel: rag.chunks should show source_type for each chunk
```

### Exit criteria
- `load_system_prompt()` injects chunks in 3 named sections (behavioral/interest/general)
- Memory section is skipped if no facts have been written
- Behavioral/interest chunks appear before general knowledge in prompt
- `source_type` is preserved end-to-end from RAG query → chunk → system prompt section

### Rollback
`git checkout HEAD -- src/mlaude/llm.py`

---

## Invariants (verified after every step)

- `uv run mlaude` starts without error
- WebSocket `/ws` accepts messages and returns streaming tokens
- Existing sessions load correctly from SQLite
- `GET /api/status` returns 200
- MEMORY.md is not corrupted

---

## Open Questions / Future Steps

These are **not in scope** for this blueprint but are the logical next steps:

1. **Topic auto-detection** — classify incoming message domain (physics/history/etc.) and dynamically prepend a domain-specific behavioral modifier. Would be a new `personality.py` module.
2. **HyDE retrieval** — for complex questions, generate a "hypothetical answer" and use its embedding for retrieval (better semantic match than using the raw question).
3. **Interest file editing UI** — a tab in the web UI to edit `~/.mlaude/knowledge/` files directly, with `reindex` button.
4. **Populate the interest files** — the `[TODO]` placeholders in Step 2's templates need to be filled with the user's actual content. This is the user's job, not the LLM's.

---

## Mutation Protocol

If this plan needs changes mid-execution:

- **Split a step**: Insert a new row in the Steps table, update dependency column, add full step spec.
- **Skip a step**: Mark as `SKIPPED` in the Steps table, note the reason.
- **Reorder**: Update dependency column and re-check all downstream deps.
- **Abandon**: Mark entire plan `ABANDONED` with reason and date. Create a new plan.

All mutations must be recorded in this file with a `[CHANGED: date, reason]` annotation.
