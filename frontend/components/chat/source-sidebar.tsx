"use client";

import { FileText, SearchSlash, X } from "lucide-react";

import type { WorkspaceFile, WorkspaceMessage } from "@/lib/types";

interface SourceSidebarProps {
  message: WorkspaceMessage | null;
  userFiles: WorkspaceFile[];
  onClose: () => void;
}

function SourceCard({
  title,
  eyebrow,
  preview,
}: {
  title: string;
  eyebrow: string;
  preview: string;
}) {
  return (
    <div className="panel-card rounded-[1.25rem] p-4">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
        {eyebrow}
      </p>
      <h3 className="mt-2 text-sm font-semibold text-[color:var(--text-main)]">
        {title}
      </h3>
      <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
        {preview}
      </p>
    </div>
  );
}

export function SourceSidebar({
  message,
  userFiles,
  onClose,
}: SourceSidebarProps) {
  const citations = message?.citations ?? [];
  const documents = message?.documents ?? [];

  const citationOrder = new Map<string, number>();
  citations.forEach((citation, index) => {
    if (!citationOrder.has(citation.document_id)) {
      citationOrder.set(citation.document_id, index);
    }
  });

  const citedDocuments = [...documents]
    .filter((document) => citationOrder.has(document.document_id))
    .sort(
      (left, right) =>
        (citationOrder.get(left.document_id) ?? 999) -
        (citationOrder.get(right.document_id) ?? 999)
    );

  const otherDocuments = documents.filter(
    (document) => !citationOrder.has(document.document_id)
  );

  return (
    <aside
      data-testid="source-sidebar"
      className="panel-surface flex h-full w-full flex-col rounded-[1.75rem] border border-[color:var(--border-soft)]"
    >
      <div className="flex items-center justify-between border-b border-[color:var(--border-soft)] px-5 py-4">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
            Sources
          </p>
          <h2 className="mt-1 text-base font-semibold tracking-tight text-[color:var(--text-main)]">
            Citations and supporting context
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-9 w-9 items-center justify-center rounded-full text-[color:var(--text-soft)] transition hover:bg-white hover:text-[color:var(--text-main)]"
          aria-label="Close sources"
        >
          <X size={16} />
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-5">
        {citedDocuments.length === 0 && otherDocuments.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center rounded-[1.5rem] border border-dashed border-[color:var(--border-soft)] bg-white/60 px-5 py-10 text-center">
            <SearchSlash className="text-[color:var(--text-faint)]" size={22} />
            <p className="mt-3 text-sm font-medium text-[color:var(--text-main)]">
              No sources for this message yet
            </p>
            <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
              Once retrieval or tool results are used, their citations and supporting
              excerpts appear here instead of in a modal dump.
            </p>
          </div>
        ) : null}

        {citedDocuments.length > 0 ? (
          <section className="space-y-3">
            <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
              Cited First
            </p>
            {citedDocuments.map((document) => (
              <SourceCard
                key={document.document_id}
                title={document.title}
                eyebrow={document.source}
                preview={document.preview}
              />
            ))}
          </section>
        ) : null}

        {otherDocuments.length > 0 ? (
          <section className="space-y-3">
            <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
              More Found
            </p>
            {otherDocuments.map((document) => (
              <SourceCard
                key={document.document_id}
                title={document.title}
                eyebrow={document.source}
                preview={document.preview}
              />
            ))}
          </section>
        ) : null}

        {userFiles.length > 0 ? (
          <section className="space-y-3">
            <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
              User Files
            </p>
            {userFiles.map((file) => (
              <div
                key={file.id}
                className="panel-card flex items-center gap-3 rounded-[1.25rem] px-4 py-3"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[color:var(--accent-soft)] text-[color:var(--accent)]">
                  <FileText size={16} />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-[color:var(--text-main)]">
                    {file.title}
                  </p>
                  <p className="truncate text-xs text-[color:var(--text-faint)]">
                    {file.filename}
                  </p>
                </div>
              </div>
            ))}
          </section>
        ) : null}
      </div>
    </aside>
  );
}
