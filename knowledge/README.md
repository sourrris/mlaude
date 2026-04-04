# Knowledge Base

These files are behavioral profiles and interest context for Mlaude. They are indexed into the RAG knowledge base and retrieved when relevant to the conversation.

## Structure

```
knowledge/
├── about/
│   ├── profile.md            — who you are, intellectual style
│   └── communication_style.md — how you talk, what you prefer from AI
└── interests/
    ├── physics_astrophysics.md
    ├── history_politics.md
    └── philosophy_science.md
```

## How to Use

**To customize:** Edit any file directly. Add specifics where `[TODO: Personalize]` markers appear.

**To re-index after editing:** In the chat UI, send `"reindex knowledge"` or use the reindex button. Or restart the server — it indexes on startup.

**To add a new domain:** Create a new `.md` file anywhere in this directory. It will be indexed automatically.

## How These Files Are Used

Files in `about/` are tagged `source_type: about` in ChromaDB. They're retrieved with a slightly more lenient similarity threshold — behavioral context is worth injecting even on weaker matches.

Files in `interests/` are tagged `source_type: interest` and appear in a separate "Your Interest Context" section of the system prompt, distinct from factual knowledge.

## Design Principle

These are **behavioral profiles**, not fact dumps. The goal isn't to tell the LLM *that* you're interested in physics — it's to tell it *how you think about physics* so it can engage at the right depth and register.

The `[TODO: Personalize]` sections are where you add specifics that make this yours.
