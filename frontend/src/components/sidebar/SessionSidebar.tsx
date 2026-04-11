/**
 * ═══════════════════════════════════════════════════════════════════════
 *  SIDEBAR — Design System Reference (Claude-inspired light theme)
 * ═══════════════════════════════════════════════════════════════════════
 *
 *  FONT FAMILY
 *  ─────────────────────────────────────────────────────────────────────
 *  Primary:  "Inter", var(--font-sans)  — set globally in index.css
 *  Claude uses "Söhne" — Inter is the closest open-source match.
 *
 *  TYPOGRAPHY SCALE                    (use across all screens)
 *  ─────────────────────────────────────────────────────────────────────
 *  Nav items (New chat, Search…):   15px, weight 400, color #3f3f46
 *  Section labels (Recents):        13px, weight 500, color #a1a1aa
 *  Date group labels (Today…):      13px, weight 500, color #a1a1aa
 *  Chat history items:              14px, weight 400, color #3f3f46
 *  User display name:               14px, weight 600, color #27272a
 *  User plan label:                 12px, weight 400, color #a1a1aa
 *
 *  COLOR PALETTE                      (use across all screens)
 *  ─────────────────────────────────────────────────────────────────────
 *  Page/sidebar bg:       #f9f8f6   warm off-white
 *  Item hover bg:         #eeede9   warm light gray
 *  Item active/selected:  #e8e7e4   warm medium gray
 *  Divider stroke:        #e4e4e7   zinc-200
 *  Icon resting:          #71717a   zinc-500
 *  Icon hovered:          #3f3f46   zinc-700
 *  Text primary:          #3f3f46   zinc-700
 *  Text dark:             #27272a   zinc-800
 *  Text muted:            #a1a1aa   zinc-400
 *  Accent:                #d97757   Claude rust/orange (from index.css)
 *  Avatar bg:             #3f3f46   zinc-700
 *  Avatar text:           #ffffff
 *
 *  SPACING TOKENS                     (use across all screens)
 *  ─────────────────────────────────────────────────────────────────────
 *  Sidebar width:         280px     (set in App.tsx motion container)
 *  Container inset:       12px      (padding-left/right on outer aside)
 *  Button inner px:       12px      (left padding inside pill)
 *  Total left inset:      ~24px     (12 container + 12 button)
 *  Nav row height:        44px      (h-11 on button)
 *  Nav icon size:         20px      strokeWidth: 1.5
 *  Icon-to-text gap:      14px      (gap-3.5)
 *  Section separator:     24px      (mb-6 / mt-6 between sections)
 *  Chat item row height:  40px      (h-10)
 *  Chat items gap:        2px       (gap-0.5 between rows)
 *  Date group gap:        20px      (gap-5 between date groups)
 *  User avatar:           32px      (w-8 h-8)
 *  Footer padding:        py-4 px-4
 *
 *  ICON STYLE                         (use across all screens)
 *  ─────────────────────────────────────────────────────────────────────
 *  All icons: outline stroke, strokeWidth 1.5
 *  Resting:   #71717a (zinc-500)
 *  Hovered:   #3f3f46 (zinc-700) via parent `group` hover
 *
 *  HOVER ANIMATIONS (framer-motion)   (reusable pattern)
 *  ─────────────────────────────────────────────────────────────────────
 *  Plus:          rotate 90°
 *  BrainCircuit:  scale 1.15
 *  RefreshCw:     rotate 180°
 *  Spring config: stiffness 300, damping 20
 * ═══════════════════════════════════════════════════════════════════════
 */

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { TargetAndTransition } from "framer-motion";
import {
  Plus,
  Trash2,
  RefreshCw,
  BrainCircuit,
  ChevronsUpDown,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Session } from "@/types";

// ─── Commented-out icons: uncomment when enabling those nav sections ──
// import { Search, SlidersHorizontal } from "lucide-react";       // Top: Search, Customize
// import { MessageCircle, FolderClosed, LayoutGrid } from "lucide-react"; // Mid: Chats, Projects, Artifacts

/* ── Props ───────────────────────────────────────────────────────────── */
interface Props {
  sessions: Session[];
  activeSessionId: string | null;
  onNew: () => void;
  onLoad: (id: string) => void;
  onDelete: (id: string) => void;
  onReindex: () => void;
  onOpenMemory: () => void;
}

/* ── Date Grouping ───────────────────────────────────────────────────── */
type GroupedSessions = { label: string; sessions: Session[] };

function groupSessionsByDate(sessions: Session[]): GroupedSessions[] {
  const groups: Record<string, Session[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
    "Previous 30 Days": [],
    Older: [],
  };

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const last7 = new Date(today);
  last7.setDate(last7.getDate() - 7);
  const last30 = new Date(today);
  last30.setDate(last30.getDate() - 30);

  sessions.forEach((s) => {
    const d = new Date(s.updated_at);
    if (d >= today) groups["Today"].push(s);
    else if (d >= yesterday) groups["Yesterday"].push(s);
    else if (d >= last7) groups["Previous 7 Days"].push(s);
    else if (d >= last30) groups["Previous 30 Days"].push(s);
    else groups["Older"].push(s);
  });

  return Object.entries(groups)
    .map(([label, sessions]) => ({ label, sessions }))
    .filter((g) => g.sessions.length > 0);
}

/* ── Animated Icon ───────────────────────────────────────────────────── */
function AnimIcon({
  children,
  hoverAnim,
}: {
  children: React.ReactNode;
  hoverAnim: TargetAndTransition;
}) {
  return (
    <motion.span
      className="inline-flex items-center justify-center shrink-0 w-5 h-5"
      whileHover={hoverAnim}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
    >
      {children}
    </motion.span>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   NavRow — Sidebar navigation button.
   Fixed at 44px tall (h-[44px]), with 12px inner left padding.
   The container adds another 12px, giving ~24px total from the sidebar edge.
   ───────────────────────────────────────────────────────────────────── */
function NavRow({
  icon,
  label,
  onClick,
  hoverAnim,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  hoverAnim: TargetAndTransition;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group flex items-center gap-3.5 w-full",
        "h-11 pl-3 pr-3 rounded-xl",
        "text-[15px] font-normal text-[#3f3f46]",
        "hover:bg-[#eeede9] active:bg-[#e8e7e4]",
        "transition-colors duration-150 cursor-pointer"
      )}
    >
      <AnimIcon hoverAnim={hoverAnim}>{icon}</AnimIcon>
      {label}
    </button>
  );
}

/* ── Main Component ──────────────────────────────────────────────────── */
export function SessionSidebar({
  sessions,
  activeSessionId,
  onNew,
  onLoad,
  onDelete,
  onReindex,
  onOpenMemory,
}: Props) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const groupedSessions = useMemo(
    () => groupSessionsByDate(sessions),
    [sessions]
  );

  /* Icon props — 20px, stroke 1.5, zinc-500 → zinc-700 on hover */
  const ico = {
    size: 20,
    strokeWidth: 1.5,
    className:
      "text-[#71717a] group-hover:text-[#3f3f46] transition-colors duration-150",
  } as const;

  return (
    <aside
      className="w-full flex flex-col h-full bg-[#f9f8f6] font-sans select-none"
      style={{ padding: "0 12px" }}
    >
      {/* ══════════════════════════════════════════════════════════════
          SECTION 1 — Top Actions
          Container: 12px outer padding + 12px button padding = 24px
          Each row: 44px fixed height
          ════════════════════════════════════════════════════════════ */}
      <div className="flex flex-col pt-5 gap-0.5">
        <NavRow
          icon={<Plus {...ico} />}
          label="New chat"
          onClick={onNew}
          hoverAnim={{ rotate: 90 }}
        />
        <NavRow
          icon={<BrainCircuit {...ico} />}
          label="Memory"
          onClick={onOpenMemory}
          hoverAnim={{ scale: 1.15 }}
        />
        <NavRow
          icon={<RefreshCw {...ico} />}
          label="Reindex knowledge"
          onClick={onReindex}
          hoverAnim={{ rotate: 180 }}
        />
        <NavRow
          icon={<Activity {...ico} />}
          label="Diagnostics"
          onClick={() => window.location.href = "/diagnostics"}
          hoverAnim={{ scale: 1.15 }}
        />

        {/* ─── Commented: Search & Customize ──────────────────────────
            Uncomment when ready. Same NavRow + AnimIcon pattern.

            <NavRow
              icon={<Search {...ico} />}
              label="Search"
              hoverAnim={{ scale: 1.15 }}
            />
            <NavRow
              icon={<SlidersHorizontal {...ico} />}
              label="Customize"
              hoverAnim={{ x: [0, -2, 2, -2, 0] }}
            />
        ────────────────────────────────────────────────────────── */}
      </div>

      {/* ══════════════════════════════════════════════════════════════
          SECTION 2 — Category Nav (Chats / Projects / Artifacts)
          Currently disabled. Uncomment imports + JSX when ready.

          <div className="mx-1 my-2 border-t border-[#e4e4e7]" />
          <div className="flex flex-col gap-0.5">
            <NavRow icon={<MessageCircle {...ico} />} label="Chats" hoverAnim={{ y: -2 }} />
            <NavRow icon={<FolderClosed {...ico} />} label="Projects" hoverAnim={{ scaleY: 1.1 }} />
            <NavRow icon={<LayoutGrid {...ico} />} label="Artifacts" hoverAnim={{ rotate: 45 }} />
          </div>
          ════════════════════════════════════════════════════════════ */}

      {/* ══════════════════════════════════════════════════════════════
          SECTION 3 — Recents (scrollable chat history)
          Top margin:  24px (mt-6) for clear section break
          Items:       14px / 400 / #3f3f46
          Item height: 40px (h-[40px])
          ════════════════════════════════════════════════════════════ */}
      <nav className="flex-1 overflow-y-auto mt-6 custom-scrollbar">
        {sessions.length === 0 ? (
          <p className="text-[13px] text-[#a1a1aa] pl-3 py-6">
            No recent chats
          </p>
        ) : (
          <div className="flex flex-col gap-5">
            {groupedSessions.map((group) => (
              <div key={group.label}>
                {/* Date group label */}
                <div className="pl-3 pb-1 text-[13px] font-medium text-[#a1a1aa]">
                  {group.label}
                </div>

                {/* Chat items */}
                <div className="flex flex-col">
                  <AnimatePresence initial={false}>
                    {group.sessions.map((s) => (
                      <motion.div
                        key={s.id}
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.15 }}
                      >
                        <div
                          onMouseEnter={() => setHoveredId(s.id)}
                          onMouseLeave={() => setHoveredId(null)}
                          className={cn(
                            "group flex items-center",
                            "min-h-10 py-2.5 pl-3 pr-2 rounded-xl cursor-pointer",
                            "transition-colors duration-100",
                            s.id === activeSessionId
                              ? "bg-[#e8e7e4] text-[#27272a]"
                              : "text-[#3f3f46] hover:bg-[#eeede9] hover:text-[#27272a]"
                          )}
                          onClick={() => onLoad(s.id)}
                        >
                          <span className="flex-1 text-[14px] font-normal truncate leading-snug">
                            {s.title ?? "Untitled"}
                          </span>

                          {hoveredId === s.id && (
                            <motion.button
                              initial={{ opacity: 0, scale: 0.8 }}
                              animate={{ opacity: 1, scale: 1 }}
                              transition={{ duration: 0.1 }}
                              onClick={(e) => {
                                e.stopPropagation();
                                onDelete(s.id);
                              }}
                              className="shrink-0 ml-1 p-1 rounded-lg text-[#a1a1aa] hover:text-red-500 hover:bg-[#eeede9] transition-colors"
                            >
                              <Trash2 size={14} strokeWidth={1.5} />
                            </motion.button>
                          )}
                        </div>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </div>
              </div>
            ))}
          </div>
        )}
      </nav>

      {/* ══════════════════════════════════════════════════════════════
          SECTION 4 — User Profile Footer
          Border-top:  1px #e4e4e7
          Avatar:      32px circle, bg #3f3f46, white 13px semibold
          Name:        14px / 600 / #27272a
          Plan label:  12px / 400 / #a1a1aa
          Right icons: Download + ChevronsUpDown, 18px, #a1a1aa
          ════════════════════════════════════════════════════════════ */}
      <div className="mb-3 mt-1 p-2 flex items-center gap-2 rounded-xl hover:bg-[#eeede9] cursor-pointer transition-colors duration-150 group">
        <div className="w-8 h-8 rounded-full bg-[#3f3f46] flex items-center justify-center shrink-0">
          <span className="text-white text-[13px] font-semibold leading-none">
            S
          </span>
        </div>

        <div className="flex-1 min-w-0 px-1">
          <div className="text-[14px] font-semibold text-[#27272a] truncate leading-tight">
            Sourish
          </div>
          <div className="text-[12px] font-normal text-[#a1a1aa] leading-tight mt-0.5">
            Pro plan
          </div>
        </div>

        <div className="flex items-center text-[#a1a1aa] group-hover:text-[#3f3f46] pr-1 transition-colors duration-150">
          <ChevronsUpDown size={16} strokeWidth={1.5} />
        </div>
      </div>
    </aside>
  );
}
