"use client";

import { useEffect, useState } from "react";
import { RefreshCcw, Save } from "lucide-react";

import { discoverModels, getModelSettings, updateModelSettings } from "@/lib/api";
import type { ModelSettings } from "@/lib/types";

export function ModelSettingsPanel() {
  const [form, setForm] = useState<ModelSettings>({
    provider: "LM Studio",
    llm_base_url: "http://127.0.0.1:1234",
    default_chat_model: "gemma4:e4b",
    default_embedding_model: "text-embedding-nomic-embed-text-v1.5",
    temperature: 0.2,
  });
  const [models, setModels] = useState<string[]>([]);
  const [health, setHealth] = useState<string>("Loading runtime…");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await getModelSettings();
        if (!cancelled) {
          const discoveredModels = response.models ?? response.health.models ?? [];
          setForm({
            ...response.settings,
            default_chat_model:
              discoveredModels.includes(response.settings.default_chat_model)
                ? response.settings.default_chat_model
                : discoveredModels[0] || response.settings.default_chat_model,
          });
          setModels(discoveredModels);
          setHealth(
            response.health.running
              ? response.health.embedding_model_available
                ? `Connected. ${discoveredModels.length} model(s) discovered.`
                : `Connected, but ${response.settings.default_embedding_model} is not available locally.`
              : response.health.error || "LLM runtime is unavailable."
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function refreshModels() {
    const nextModels = await discoverModels(form.llm_base_url);
    setModels(nextModels);
    if (!nextModels.includes(form.default_chat_model) && nextModels[0]) {
      setForm((current) => ({ ...current, default_chat_model: nextModels[0] }));
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      const response = await updateModelSettings(form);
      const discoveredModels = response.models ?? response.health.models ?? [];
      setModels(discoveredModels);
      setHealth(
        response.health.running
          ? response.health.embedding_model_available
            ? `Connected. ${discoveredModels.length} model(s) discovered.`
            : `Connected, but ${response.settings.default_embedding_model} is not available locally.`
          : response.health.error || "LLM runtime is unavailable."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex h-full min-h-screen flex-col px-4 py-4 lg:px-5 lg:py-5">
      <div className="panel-surface mx-auto flex w-full max-w-5xl flex-1 flex-col rounded-[2rem] px-6 py-6">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
            LLM Runtime
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[color:var(--text-main)]">
            Local model configuration
          </h1>
          <p className="mt-3 text-sm leading-7 text-[color:var(--text-soft)]">
            This workspace exposes local LLM runtime settings (Ollama, LM Studio, etc.). Model discovery,
            fallback handling, and the default chat and embedding models all live here.
          </p>
        </div>

        <div className="mt-8 grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
          <section className="panel-card rounded-[1.5rem] p-5">
            <div className="grid gap-5">
              <label className="grid gap-2">
                <span className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                  Provider
                </span>
                <select
                  value={form.provider}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      provider: event.target.value,
                    }))
                  }
                  className="rounded-2xl border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] px-4 py-3 outline-none"
                >
                  <option value="ollama">Ollama</option>
                  <option value="lm-studio">LM Studio</option>
                </select>
              </label>

              <label className="grid gap-2">
                <span className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                  LLM Base URL
                </span>
                <input
                  value={form.llm_base_url}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      llm_base_url: event.target.value,
                    }))
                  }
                  className="rounded-2xl border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] px-4 py-3 outline-none"
                />
              </label>

              <label className="grid gap-2">
                <span className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                  Default Chat Model
                </span>
                <select
                  value={form.default_chat_model}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      default_chat_model: event.target.value,
                    }))
                  }
                  data-testid="settings-model-select"
                  className="rounded-2xl border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] px-4 py-3 outline-none"
                >
                  {models.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </label>

              <label className="grid gap-2">
                <span className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                  Default Embedding Model
                </span>
                <select
                  value={form.default_embedding_model}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      default_embedding_model: event.target.value,
                    }))
                  }
                  data-testid="settings-embedding-model-select"
                  className="rounded-2xl border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] px-4 py-3 outline-none"
                >
                  {models.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </label>

              <label className="grid gap-2">
                <span className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                  Temperature
                </span>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.1"
                  value={form.temperature}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      temperature: Number(event.target.value),
                    }))
                  }
                  className="rounded-2xl border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] px-4 py-3 outline-none"
                />
              </label>

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => void refreshModels()}
                  className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-soft)] bg-white px-4 py-2 text-sm text-[color:var(--text-main)]"
                >
                  <RefreshCcw size={14} />
                  Refresh Models
                </button>
                <button
                  type="button"
                  onClick={() => void handleSave()}
                  disabled={saving}
                  data-testid="settings-save-button"
                  className="inline-flex items-center gap-2 rounded-full bg-[color:var(--accent)] px-4 py-2 text-sm font-medium text-white"
                >
                  <Save size={14} />
                  {saving ? "Saving…" : "Save Settings"}
                </button>
              </div>
            </div>
          </section>

          <section className="panel-card rounded-[1.5rem] p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
              Runtime Status
            </p>
            <p className="mt-3 text-sm leading-7 text-[color:var(--text-soft)]">
              {loading ? "Loading runtime…" : health}
            </p>
            <p className="mt-3 text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
              {form.default_embedding_model
                ? `Embedding model: ${form.default_embedding_model}`
                : "No embedding model selected"}
            </p>

            <div className="mt-6 space-y-2">
              <p className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                Discovered Models
              </p>
              {models.length === 0 ? (
                <div className="rounded-[1.25rem] border border-dashed border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] px-4 py-4 text-sm text-[color:var(--text-soft)]">
                  No local models detected yet.
                </div>
              ) : (
                models.map((model) => (
                  <div
                    key={model}
                    className={`rounded-[1.25rem] border px-4 py-3 text-sm flex items-center justify-between ${
                      form.default_chat_model === model
                        ? "border-[color:var(--accent)] bg-[color:var(--accent-soft)] text-[color:var(--accent)]"
                        : "border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] text-[color:var(--text-main)]"
                    }`}
                  >
                    {model}
                    {form.provider === "lm-studio" && (
                      <div className="flex gap-2">
                        <button
                          onClick={async () => {
                            try {
                              await fetch(`/api/models/load?model=${model}`, { method: 'POST' });
                              alert(`Model ${model} load requested`);
                            } catch (e) {
                              alert('Failed to load model');
                            }
                          }}
                          className="text-[10px] uppercase font-bold opacity-60 hover:opacity-100"
                        >
                          Load
                        </button>
                        <button
                          onClick={async () => {
                            try {
                              await fetch(`/api/models/download?model=${model}`, { method: 'POST' });
                              alert(`Model ${model} download requested`);
                            } catch (e) {
                              alert('Failed to download model');
                            }
                          }}
                          className="text-[10px] uppercase font-bold opacity-60 hover:opacity-100"
                        >
                          Download
                        </button>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
