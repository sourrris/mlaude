import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Save, RefreshCw } from "lucide-react";

interface Props {
  open: boolean;
  content: string | null;
  onClose: () => void;
  onLoad: () => void;
  onSave: (content: string) => void;
}

export function MemoryEditor({ open, content, onClose, onLoad, onSave }: Props) {
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load memory when opened
  useEffect(() => {
    if (open) {
      onLoad();
      setSaved(false);
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync content into draft when received
  useEffect(() => {
    if (content !== null) {
      setDraft(content);
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [content]);

  const handleSave = () => {
    onSave(draft);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const isDirty = content !== null && draft !== content;

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 bg-black/60 z-40 backdrop-blur-sm"
            onClick={onClose}
          />

          <motion.div
            key="modal"
            initial={{ opacity: 0, scale: 0.97, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="fixed inset-x-4 top-[5vh] bottom-[5vh] max-w-2xl mx-auto z-50 bg-zinc-900 border border-zinc-700 rounded-2xl flex flex-col overflow-hidden shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
              <div>
                <h2 className="text-[14px] font-semibold text-zinc-100">Memory</h2>
                <p className="text-[12px] text-zinc-500 mt-0.5">~/.mlaude/MEMORY.md</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={onLoad}
                  className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                  title="Reload"
                >
                  <RefreshCw size={14} />
                </button>
                <button
                  onClick={handleSave}
                  disabled={!isDirty}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium transition-all duration-150 disabled:opacity-30 disabled:cursor-default bg-amber-400 text-black hover:bg-amber-300 disabled:bg-zinc-700 disabled:text-zinc-500"
                >
                  <Save size={12} />
                  {saved ? "Saved!" : "Save"}
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Editor */}
            <div className="flex-1 overflow-hidden p-4">
              {content === null ? (
                <div className="h-full flex items-center justify-center">
                  <div className="flex items-center gap-2 text-zinc-500 text-[13px]">
                    <RefreshCw size={14} className="animate-spin" />
                    Loading…
                  </div>
                </div>
              ) : (
                <textarea
                  ref={textareaRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  className="w-full h-full resize-none bg-zinc-950/50 border border-zinc-800 rounded-xl p-4 text-[13px] text-zinc-300 leading-relaxed font-mono outline-none focus:border-zinc-600 transition-colors placeholder:text-zinc-700"
                  placeholder="# What I Know About You&#10;&#10;## Identity&#10;&#10;## Notes"
                  spellCheck={false}
                />
              )}
            </div>

            {/* Footer hint */}
            <div className="px-5 py-3 border-t border-zinc-800">
              <p className="text-[11px] text-zinc-600">
                Edit directly and save. Changes take effect on the next message.
                {isDirty && <span className="text-amber-500 ml-2">· Unsaved changes</span>}
              </p>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
