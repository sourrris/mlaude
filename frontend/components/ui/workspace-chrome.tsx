"use client";

import { useDeferredValue, useEffect, useState, startTransition } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Menu } from "lucide-react";

import { createSession, listSessions } from "@/lib/api";
import type { WorkspaceSession } from "@/lib/types";
import { AppSidebar } from "@/components/sidebar/app-sidebar";

interface WorkspaceChromeProps {
  activeSection: "chat" | "files" | "settings";
  selectedSessionId?: string | null;
  children: React.ReactNode;
}

export function WorkspaceChrome({
  activeSection,
  selectedSessionId = null,
  children,
}: WorkspaceChromeProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [sessions, setSessions] = useState<WorkspaceSession[]>([]);
  const [query, setQuery] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const nextSessions = await listSessions(deferredQuery);
        if (!cancelled) {
          setSessions(nextSessions);
        }
      } catch (error) {
        if (!cancelled) {
          console.error(error);
        }
      }
    }

    load();

    const refresh = () => {
      load();
    };
    window.addEventListener("mlaude:sessions-changed", refresh);
    return () => {
      cancelled = true;
      window.removeEventListener("mlaude:sessions-changed", refresh);
    };
  }, [deferredQuery]);

  async function handleNewSession() {
    const session = await createSession();
    window.dispatchEvent(new Event("mlaude:sessions-changed"));
    startTransition(() => {
      router.push(`/?session=${session.id}`);
    });
    setSidebarOpen(false);
  }

  function handleSelectSession(sessionId: string) {
    startTransition(() => {
      router.push(`/?session=${sessionId}`);
    });
    setSidebarOpen(false);
  }

  return (
    <div className="workspace-shell">
      <div className="flex min-h-screen">
        <div className="hidden h-screen w-[320px] shrink-0 border-r border-[color:var(--border-soft)] lg:block">
          <AppSidebar
            sessions={sessions}
            activeSection={activeSection}
            activeSessionId={selectedSessionId}
            query={query}
            onQueryChange={setQuery}
            onSelectSession={handleSelectSession}
            onNewSession={handleNewSession}
          />
        </div>

        {sidebarOpen ? (
          <div className="fixed inset-0 z-40 bg-black/20 lg:hidden">
            <div className="h-full w-[88vw] max-w-[340px] border-r border-[color:var(--border-soft)] bg-[color:var(--bg-sidebar)] shadow-2xl">
              <AppSidebar
                sessions={sessions}
                activeSection={activeSection}
                activeSessionId={selectedSessionId}
                query={query}
                onQueryChange={setQuery}
                onSelectSession={handleSelectSession}
                onNewSession={handleNewSession}
                onCloseMobile={() => setSidebarOpen(false)}
              />
            </div>
          </div>
        ) : null}

        <div className="flex min-h-screen min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-[color:var(--border-soft)] px-4 py-3 lg:hidden">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/80 text-[color:var(--text-main)] shadow-sm"
              aria-label="Open sidebar"
            >
              <Menu size={18} />
            </button>
            <div className="text-right">
              <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
                {pathname === "/settings"
                  ? "Settings"
                  : pathname === "/files"
                    ? "Files"
                    : "Chat"}
              </p>
              <p className="text-sm font-medium text-[color:var(--text-main)]">
                Local Workspace
              </p>
            </div>
          </div>
          <div className="min-h-0 flex-1">{children}</div>
        </div>
      </div>
    </div>
  );
}
