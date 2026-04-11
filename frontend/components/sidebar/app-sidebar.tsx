"use client";

import { useMemo } from "react";
import Link from "next/link";
import { MessageSquarePlus, Search, Settings2, Library, PanelLeftClose } from "lucide-react";

import type { WorkspaceSession } from "@/lib/types";

interface AppSidebarProps {
  sessions: WorkspaceSession[];
  activeSection: "chat" | "files" | "settings";
  activeSessionId?: string | null;
  query: string;
  onQueryChange: (value: string) => void;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onCloseMobile?: () => void;
}

function groupSessions(sessions: WorkspaceSession[]) {
  const groups = {
    Today: [] as WorkspaceSession[],
    Yesterday: [] as WorkspaceSession[],
    Earlier: [] as WorkspaceSession[],
  };

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  for (const session of sessions) {
    const updatedAt = session.updated_at ? new Date(session.updated_at) : today;
    if (updatedAt >= today) {
      groups.Today.push(session);
    } else if (updatedAt >= yesterday) {
      groups.Yesterday.push(session);
    } else {
      groups.Earlier.push(session);
    }
  }

  return Object.entries(groups).filter(([, items]) => items.length > 0);
}

export function AppSidebar({
  sessions,
  activeSection,
  activeSessionId,
  query,
  onQueryChange,
  onSelectSession,
  onNewSession,
  onCloseMobile,
}: AppSidebarProps) {
  const groupedSessions = useMemo(() => groupSessions(sessions), [sessions]);

  return (
    <aside className="flex h-full w-full flex-col bg-[color:var(--bg-sidebar)]">
      <div className="flex items-center justify-between px-4 pb-3 pt-5">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[color:var(--text-faint)]">
            Workspace
          </p>
          <h1 className="mt-1 text-lg font-semibold tracking-tight text-[color:var(--text-main)]">
            Mlaude
          </h1>
        </div>
        {onCloseMobile ? (
          <button
            type="button"
            onClick={onCloseMobile}
            className="rounded-full p-2 text-[color:var(--text-soft)] transition hover:bg-white/70 hover:text-[color:var(--text-main)] lg:hidden"
            aria-label="Close sidebar"
          >
            <PanelLeftClose size={18} />
          </button>
        ) : null}
      </div>

      <div className="px-3">
        <button
          type="button"
          onClick={onNewSession}
          data-testid="new-session-button"
          className="flex w-full items-center gap-3 rounded-2xl border border-[color:var(--border-strong)] bg-white px-4 py-3 text-left text-sm font-medium text-[color:var(--text-main)] shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[color:var(--accent-soft)] text-[color:var(--accent)]">
            <MessageSquarePlus size={17} />
          </div>
          <div>
            <p>New Session</p>
            <p className="text-xs font-normal text-[color:var(--text-faint)]">
              Start a fresh local chat
            </p>
          </div>
        </button>
      </div>

      <div className="px-3 pt-4">
        <label className="flex items-center gap-2 rounded-2xl border border-transparent bg-white/70 px-3 py-2 shadow-sm transition focus-within:border-[color:var(--border-strong)] focus-within:bg-white">
          <Search size={15} className="text-[color:var(--text-faint)]" />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search chats"
            data-testid="chat-search-input"
            className="w-full bg-transparent text-sm text-[color:var(--text-main)] outline-none placeholder:text-[color:var(--text-faint)]"
          />
        </label>
      </div>

      <div className="px-3 pt-4">
        <nav className="flex flex-col gap-1">
          <Link
            href="/files"
            data-testid="files-link"
            className={`flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition ${
              activeSection === "files"
                ? "bg-white text-[color:var(--text-main)] shadow-sm"
                : "text-[color:var(--text-soft)] hover:bg-white/70 hover:text-[color:var(--text-main)]"
            }`}
          >
            <Library size={16} />
            Knowledge & Files
          </Link>
          <Link
            href="/settings"
            data-testid="settings-link"
            className={`flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition ${
              activeSection === "settings"
                ? "bg-white text-[color:var(--text-main)] shadow-sm"
                : "text-[color:var(--text-soft)] hover:bg-white/70 hover:text-[color:var(--text-main)]"
            }`}
          >
            <Settings2 size={16} />
            Settings
          </Link>
        </nav>
      </div>

      <div className="mt-5 min-h-0 flex-1 overflow-y-auto px-3 pb-5">
        <div className="mb-3 px-1">
          <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-faint)]">
            Recents
          </p>
        </div>
        {groupedSessions.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-[color:var(--border-soft)] bg-white/50 p-4 text-sm text-[color:var(--text-soft)]">
            Your recent chats will appear here once you start using the workspace.
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {groupedSessions.map(([label, items]) => (
              <section key={label}>
                <p className="mb-2 px-1 text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
                  {label}
                </p>
                <div className="flex flex-col gap-1.5">
                  {items.map((session) => (
                    <button
                      key={session.id}
                      type="button"
                      onClick={() => onSelectSession(session.id)}
                      className={`rounded-2xl px-3 py-3 text-left transition ${
                        activeSection === "chat" && activeSessionId === session.id
                          ? "bg-white text-[color:var(--text-main)] shadow-sm"
                          : "text-[color:var(--text-soft)] hover:bg-white/70 hover:text-[color:var(--text-main)]"
                      }`}
                    >
                      <p className="truncate text-sm font-medium">{session.title}</p>
                      <p className="mt-1 truncate text-xs text-[color:var(--text-faint)]">
                        {session.last_message_preview || "No messages yet"}
                      </p>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
