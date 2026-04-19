"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock3, FileSearch, Globe2, SearchX } from "lucide-react";

import type { AgentRun, RunStep, SourceDocument } from "@/lib/types";

function statusTone(status: RunStep["status"] | AgentRun["status"]) {
  if (status === "completed") {
    return "text-emerald-700 bg-emerald-50 border-emerald-200";
  }
  if (status === "error") {
    return "text-rose-700 bg-rose-50 border-rose-200";
  }
  if (status === "running") {
    return "text-sky-700 bg-sky-50 border-sky-200";
  }
  return "text-stone-600 bg-stone-50 border-stone-200";
}

function readEvidence(run: AgentRun): SourceDocument[] {
  const value = run.artifacts?.evidence_pool;
  return Array.isArray(value) ? (value as SourceDocument[]) : [];
}

export function RunsPanel({
  runs,
  liveRun,
}: {
  runs: AgentRun[];
  liveRun: AgentRun | null;
}) {
  const visibleRuns = useMemo(() => {
    const merged = liveRun
      ? [liveRun, ...runs.filter((run) => run.id !== liveRun.id)]
      : runs;
    return merged;
  }, [liveRun, runs]);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(
    visibleRuns[0]?.id ?? null,
  );

  const selectedRun =
    visibleRuns.find((run) => run.id === selectedRunId) ?? visibleRuns[0] ?? null;
  const evidence = selectedRun ? readEvidence(selectedRun) : [];

  if (!visibleRuns.length) {
    return (
      <div
        data-testid="runs-panel"
        className="flex flex-1 items-center justify-center px-6 py-10"
      >
        <div className="max-w-md rounded-[1.6rem] border border-dashed border-[color:var(--border-soft)] bg-white/70 px-6 py-8 text-center">
          <SearchX className="mx-auto text-[color:var(--text-faint)]" size={20} />
          <p className="mt-3 text-sm font-medium text-[color:var(--text-main)]">
            No runs for this session yet
          </p>
          <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
            Each user turn creates a bounded research run with explicit steps,
            evidence, and stop reasons.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="runs-panel"
      className="grid min-h-0 flex-1 gap-4 px-5 py-5 xl:grid-cols-[320px_minmax(0,1fr)]"
    >
      <div className="min-h-0 overflow-y-auto rounded-[1.5rem] border border-[color:var(--border-soft)] bg-white/70 p-3">
        <p className="px-2 text-xs uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
          Session Runs
        </p>
        <div className="mt-3 flex flex-col gap-2">
          {visibleRuns.map((run) => (
            <button
              key={run.id}
              type="button"
              onClick={() => setSelectedRunId(run.id)}
              className={`rounded-[1.25rem] border px-4 py-3 text-left transition ${
                selectedRun?.id === run.id
                  ? "border-[color:var(--accent)] bg-[color:var(--accent-soft)]"
                  : "border-[color:var(--border-soft)] bg-white hover:border-[color:var(--border-strong)]"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium text-[color:var(--text-main)]">
                  {run.meta?.model ? String(run.meta.model) : "Research run"}
                </p>
                <span
                  className={`rounded-full border px-2 py-1 text-[11px] uppercase tracking-[0.14em] ${statusTone(
                    run.status,
                  )}`}
                >
                  {run.status}
                </span>
              </div>
              <p className="mt-2 text-xs text-[color:var(--text-faint)]">
                {run.stop_reason || "in_progress"}
              </p>
            </button>
          ))}
        </div>
      </div>

      {selectedRun ? (
        <div className="min-h-0 overflow-y-auto rounded-[1.5rem] border border-[color:var(--border-soft)] bg-white/70 p-5">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-lg font-semibold tracking-tight text-[color:var(--text-main)]">
              Research Run
            </h3>
            <span
              className={`rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.16em] ${statusTone(
                selectedRun.status,
              )}`}
            >
              {selectedRun.status}
            </span>
            <span className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
              stop: {selectedRun.stop_reason || "none"}
            </span>
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <section className="rounded-[1.25rem] border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                Plan
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {selectedRun.plan.map((step) => (
                  <span
                    key={step}
                    className="rounded-full bg-white px-3 py-1 text-xs text-[color:var(--text-soft)]"
                  >
                    {step}
                  </span>
                ))}
              </div>
            </section>

            <section className="rounded-[1.25rem] border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                Final Answer
              </p>
              <p className="mt-3 text-sm leading-6 text-[color:var(--text-soft)]">
                {String(selectedRun.artifacts?.answer_preview || "No answer persisted yet.")}
              </p>
            </section>
          </div>

          <section className="mt-5">
            <p className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
              Step Timeline
            </p>
            <div className="mt-3 flex flex-col gap-3">
              {selectedRun.steps.map((step) => (
                <div
                  key={step.id}
                  className="rounded-[1.25rem] border border-[color:var(--border-soft)] bg-white p-4"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      {step.status === "completed" ? (
                        <CheckCircle2 size={16} className="text-emerald-600" />
                      ) : step.status === "error" ? (
                        <AlertTriangle size={16} className="text-rose-600" />
                      ) : (
                        <Clock3 size={16} className="text-sky-600" />
                      )}
                      <p className="text-sm font-medium text-[color:var(--text-main)]">
                        {step.step_type}
                      </p>
                    </div>
                    <span
                      className={`rounded-full border px-2 py-1 text-[11px] uppercase tracking-[0.14em] ${statusTone(
                        step.status,
                      )}`}
                    >
                      {step.status}
                    </span>
                  </div>
                  {step.error_text ? (
                    <p className="mt-2 text-sm text-rose-700">{step.error_text}</p>
                  ) : null}
                  {Object.keys(step.output_payload || {}).length > 0 ? (
                    <pre className="mt-3 overflow-x-auto rounded-[1rem] bg-[color:var(--bg-muted)] p-3 text-xs leading-6 text-[color:var(--text-soft)]">
                      <code>{JSON.stringify(step.output_payload, null, 2)}</code>
                    </pre>
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          <section className="mt-5">
            <p className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
              Evidence
            </p>
            {evidence.length === 0 ? (
              <div className="mt-3 rounded-[1.25rem] border border-dashed border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] p-4 text-sm text-[color:var(--text-soft)]">
                This run did not persist a final evidence pool.
              </div>
            ) : (
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                {evidence.map((document) => (
                  <div
                    key={document.document_id}
                    className="rounded-[1.25rem] border border-[color:var(--border-soft)] bg-white p-4"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-1 text-[color:var(--accent)]">
                        {document.source_kind === "web_page" ||
                        document.source_kind === "web_result" ? (
                          <Globe2 size={16} />
                        ) : (
                          <FileSearch size={16} />
                        )}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-[color:var(--text-main)]">
                          {document.title}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                          {document.source_kind || "source"}
                        </p>
                        <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
                          {document.preview}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
