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
    <div className="mx-auto flex w-full max-w-12xl flex-1 flex-col items-center justify-center px-6 py-16">
      <div className="mx-auto flex h-16 rounded-2xl items-center justify-center bg-[color:var(--accent-soft)] text-4xl font-semibold text-[color:var(--accent)] px-4">
        Hello Sir, What&apos;s on your mind?
      </div>
    </div>
  );
}
