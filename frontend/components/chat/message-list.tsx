"use client";

import { useEffect, useMemo, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import {
  ChevronRight,
  FileSearch,
  Globe2,
  Hammer,
  Sigma,
  Sparkles,
} from "lucide-react";

import { FileBadge } from "@/components/files/file-badge";
import type { AssistantPacket, WorkspaceMessage } from "@/lib/types";

interface MessageListProps {
  messages: WorkspaceMessage[];
  onOpenSources: (messageId: string) => void;
}

function ToolCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="panel-card rounded-[1.2rem] p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
        {title}
      </p>
      <p className="mt-1 text-sm text-[color:var(--text-soft)]">
        {description}
      </p>
      {children ? <div className="mt-3">{children}</div> : null}
    </div>
  );
}

function AssistantTimeline({ packets }: { packets: AssistantPacket[] }) {
  const reasoning = packets
    .filter(
      (
        packet,
      ): packet is Extract<AssistantPacket, { type: "reasoning_delta" }> =>
        packet.type === "reasoning_delta",
    )
    .map((packet) => packet.reasoning)
    .join("")
    .trim();

  const searchQueries =
    packets.find(
      (
        packet,
      ): packet is Extract<
        AssistantPacket,
        { type: "search_tool_queries_delta" }
      > => packet.type === "search_tool_queries_delta",
    )?.queries ?? [];

  const searchDocuments =
    packets.find(
      (
        packet,
      ): packet is Extract<
        AssistantPacket,
        { type: "search_tool_documents_delta" }
      > => packet.type === "search_tool_documents_delta",
    )?.documents ?? [];

  const fileRead =
    packets.find(
      (
        packet,
      ): packet is Extract<AssistantPacket, { type: "file_reader_result" }> =>
        packet.type === "file_reader_result",
    ) ?? null;

  const pythonStart =
    packets.find(
      (
        packet,
      ): packet is Extract<AssistantPacket, { type: "python_tool_start" }> =>
        packet.type === "python_tool_start",
    ) ?? null;
  const pythonResult =
    packets.find(
      (
        packet,
      ): packet is Extract<AssistantPacket, { type: "python_tool_delta" }> =>
        packet.type === "python_tool_delta",
    ) ?? null;

  const urls =
    packets.find(
      (packet): packet is Extract<AssistantPacket, { type: "open_url_urls" }> =>
        packet.type === "open_url_urls",
    )?.urls ?? [];
  const urlDocuments =
    packets.find(
      (
        packet,
      ): packet is Extract<AssistantPacket, { type: "open_url_documents" }> =>
        packet.type === "open_url_documents",
    )?.documents ?? [];

  return (
    <div className="mb-4 flex flex-col gap-3">
      {reasoning ? (
        <ToolCard
          title="Thinking"
          description="Live reasoning emitted by the active model."
        >
          <div className="rounded-2xl border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] px-4 py-3">
            <p className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
              <Sparkles size={13} />
              Model Trace
            </p>
            <p className="whitespace-pre-wrap text-sm leading-6 text-[color:var(--text-soft)]">
              {reasoning}
            </p>
          </div>
        </ToolCard>
      ) : null}

      {searchQueries.length > 0 ? (
        <ToolCard
          title="Internal Search"
          description="Searching the current chat and local knowledge library."
        >
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {searchQueries.map((query) => (
                <span
                  key={query}
                  className="inline-flex items-center rounded-full bg-[color:var(--accent-soft)] px-3 py-1 text-xs font-medium text-[color:var(--accent)]"
                >
                  {query}
                </span>
              ))}
            </div>
            <div className="space-y-2">
              {searchDocuments.slice(0, 3).map((document) => (
                <div
                  key={document.document_id}
                  className="flex items-start gap-3 rounded-2xl border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] px-3 py-3"
                >
                  <FileSearch
                    size={16}
                    className="mt-1 shrink-0 text-[color:var(--accent)]"
                  />
                  <div>
                    <p className="text-sm font-medium text-[color:var(--text-main)]">
                      {document.title}
                    </p>
                    <p className="mt-1 text-sm leading-6 text-[color:var(--text-soft)]">
                      {document.preview}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </ToolCard>
      ) : null}

      {fileRead ? (
        <ToolCard
          title="Read File"
          description={`Opened a direct excerpt from ${fileRead.file_name}.`}
        >
          <pre className="overflow-x-auto rounded-2xl bg-[color:var(--bg-muted)] p-4 text-xs leading-6 text-[color:var(--text-soft)]">
            <code>{fileRead.preview}</code>
          </pre>
        </ToolCard>
      ) : null}

      {pythonStart && pythonResult ? (
        <ToolCard
          title="Python"
          description="Ran local Python to inspect or transform data."
        >
          <div className="space-y-3">
            <pre className="overflow-x-auto rounded-2xl bg-[color:var(--bg-muted)] p-4 text-xs leading-6 text-[color:var(--text-soft)]">
              <code>{pythonStart.code}</code>
            </pre>
            {pythonResult.stdout ? (
              <div className="rounded-2xl border border-[color:var(--border-soft)] bg-white px-3 py-3">
                <p className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                  <Sigma size={13} />
                  Stdout
                </p>
                <pre className="overflow-x-auto text-xs leading-6 text-[color:var(--text-soft)]">
                  <code>{pythonResult.stdout}</code>
                </pre>
              </div>
            ) : null}
            {pythonResult.stderr ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-3">
                <p className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-[color:var(--warning)]">
                  <Hammer size={13} />
                  Stderr
                </p>
                <pre className="overflow-x-auto text-xs leading-6 text-[color:var(--warning)]">
                  <code>{pythonResult.stderr}</code>
                </pre>
              </div>
            ) : null}
          </div>
        </ToolCard>
      ) : null}

      {urls.length > 0 ? (
        <ToolCard
          title="Open URL"
          description="Fetched additional context from linked pages."
        >
          <div className="space-y-2">
            {urls.map((url) => (
              <div
                key={url}
                className="flex items-start gap-3 rounded-2xl border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] px-3 py-3"
              >
                <Globe2
                  className="mt-1 shrink-0 text-[color:var(--accent)]"
                  size={16}
                />
                <div>
                  <p className="text-sm font-medium text-[color:var(--text-main)]">
                    {url}
                  </p>
                  {urlDocuments.find((document) => document.source === url) ? (
                    <p className="mt-1 text-sm leading-6 text-[color:var(--text-soft)]">
                      {
                        urlDocuments.find((document) => document.source === url)
                          ?.preview
                      }
                    </p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </ToolCard>
      ) : null}
    </div>
  );
}

export function MessageList({ messages, onOpenSources }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const renderedMessages = useMemo(() => messages, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-5 py-6" data-testid="message-list">
      <div className="mx-auto flex w-full max-4xl flex-col gap-8">

        {renderedMessages.map((message) => {
          const streaming = Boolean(message.meta?.streaming);
          const stopReason = String(message.meta?.stop_reason ?? "");
          const showSources =
            message.role === "assistant" && message.documents.length > 0;

          if (message.role === "user") {
            return (
              <div key={message.id} className="flex justify-end">
                <div className="max-w-[80%] rounded-[1.75rem] rounded-br-md bg-[color:var(--text-main)] px-5 py-4 text-white shadow-lg">
                  {message.files.length > 0 ? (
                    <div className="mb-3 flex flex-col gap-2">
                      {message.files.map((file) => (
                        <FileBadge key={file.id} file={file} />
                      ))}
                    </div>
                  ) : null}
                  <p className="whitespace-pre-wrap text-[15px] leading-7">
                    {message.content}
                  </p>
                </div>
              </div>
            );
          }

          return (
            <div key={message.id} className="flex justify-start">
              <div className="w-full max-w-[46rem]">
                <AssistantTimeline packets={message.packets} />
                <div className="panel-surface rounded-[1.75rem] px-5 py-5">
                  {message.content ? (
                    <div className="prose-chat">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeHighlight]}
                      >
                        {message.content}
                      </ReactMarkdown>
                      {streaming ? (
                        <span className="ml-1 inline-flex h-4 w-0.5 animate-pulse rounded-full bg-[color:var(--accent)] align-middle" />
                      ) : null}
                    </div>
                  ) : (
                    <p className="text-sm text-[color:var(--text-soft)]">
                      {streaming ? "Thinking…" : "No response content."}
                    </p>
                  )}

                  {showSources ? (
                    <div className="mt-4 flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => onOpenSources(message.id)}
                        data-testid="sources-button"
                        className="inline-flex items-center gap-2 rounded-full bg-[color:var(--accent-soft)] px-3 py-2 text-sm font-medium text-[color:var(--accent)] transition hover:opacity-90"
                      >
                        Sources
                        <ChevronRight size={14} />
                      </button>
                      <span className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                        {message.citations.length} cited
                      </span>
                    </div>
                  ) : null}

                  {stopReason === "user_cancelled" ? (
                    <p className="mt-4 text-xs uppercase tracking-[0.16em] text-[color:var(--warning)]">
                      Response stopped by user
                    </p>
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
