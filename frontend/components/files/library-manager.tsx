"use client";

import { useEffect, useRef, useState } from "react";
import { FilePlus2, FolderOpen } from "lucide-react";

import { listFiles, uploadFile } from "@/lib/api";
import type { WorkspaceFile } from "@/lib/types";

export function LibraryManager() {
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [loading, setLoading] = useState(true);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const nextFiles = await listFiles({ scope: "library" });
      if (!cancelled) {
        setFiles(nextFiles);
        setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleUpload(fileList: FileList) {
    const uploaded = await Promise.all(
      Array.from(fileList).map((file) =>
        uploadFile({
          file,
          scope: "library",
        })
      )
    );
    setFiles((current) => [...uploaded, ...current]);
  }

  return (
    <div className="flex h-full min-h-screen flex-col px-4 py-4 lg:px-5 lg:py-5">
      <div className="panel-surface mx-auto flex w-full max-w-5xl flex-1 flex-col rounded-[2rem] px-6 py-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="max-w-2xl">
            <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
              Local RAG
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[color:var(--text-main)]">
              Knowledge library
            </h1>
            <p className="mt-3 text-sm leading-7 text-[color:var(--text-soft)]">
              Upload files once and keep them available to new chats. Session-specific
              attachments still live in the composer, while this page acts as the shared
              local corpus for retrieval.
            </p>
          </div>

          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="inline-flex items-center gap-2 rounded-full bg-[color:var(--accent)] px-4 py-2 text-sm font-medium text-white"
          >
            <FilePlus2 size={15} />
            Add Library Files
          </button>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {loading ? (
            <div className="rounded-[1.5rem] border border-[color:var(--border-soft)] bg-white/60 px-5 py-6 text-sm text-[color:var(--text-soft)]">
              Loading library…
            </div>
          ) : files.length === 0 ? (
            <div className="rounded-[1.5rem] border border-dashed border-[color:var(--border-soft)] bg-white/60 px-5 py-8 text-sm text-[color:var(--text-soft)] md:col-span-2 xl:col-span-3">
              No shared files yet. Upload PDFs, Markdown, CSVs, or notes to make them
              available to new chats.
            </div>
          ) : (
            files.map((file) => (
              <div key={file.id} className="panel-card rounded-[1.5rem] p-5">
                <div className="flex items-start gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-[1rem] bg-[color:var(--accent-soft)] text-[color:var(--accent)]">
                    <FolderOpen size={18} />
                  </div>
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-semibold text-[color:var(--text-main)]">
                      {file.title}
                    </h3>
                    <p className="mt-1 truncate text-xs text-[color:var(--text-faint)]">
                      {file.filename}
                    </p>
                  </div>
                </div>

                <div className="mt-4 flex items-center justify-between text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                  <span>{file.chunk_count} chunks</span>
                  <span>{Math.max(1, Math.round(file.byte_size / 1024))} KB</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          if (event.target.files?.length) {
            void handleUpload(event.target.files);
            event.target.value = "";
          }
        }}
      />
    </div>
  );
}
