interface WelcomeStateProps {
  onSuggestion: (value: string) => void;
}

const SUGGESTIONS = [
  "Summarize the files in this session and tell me what matters most.",
  "Compare the uploaded notes and highlight contradictions or duplicates.",
  "Extract action items from my local documents and group them by priority.",
];

export function WelcomeState({ onSuggestion }: WelcomeStateProps) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-6 py-16">
      <div className="panel-surface w-full max-w-3xl rounded-[2rem] px-8 py-10 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-[1.5rem] bg-[color:var(--accent-soft)] text-2xl font-semibold text-[color:var(--accent)]">
          M
        </div>
        <h1 className="mt-6 text-3xl font-semibold tracking-tight text-[color:var(--text-main)]">
          Local chat, files, and grounded answers
        </h1>
        <p className="mx-auto mt-3 max-w-2xl text-sm leading-7 text-[color:var(--text-soft)]">
          This workspace is trimmed to the essentials: start a session, attach local
          files, search across them, and inspect sources in-place while the assistant works.
        </p>

        <div className="mt-8 grid gap-3 text-left md:grid-cols-3">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => onSuggestion(suggestion)}
              className="panel-card rounded-[1.5rem] px-4 py-4 text-sm leading-6 text-[color:var(--text-main)] transition hover:-translate-y-0.5 hover:border-[color:var(--border-strong)]"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
