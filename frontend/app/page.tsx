import { Suspense } from "react";

import { ChatWorkspace } from "@/components/chat/chat-workspace";

export default function HomePage() {
  return (
    <Suspense fallback={null}>
      <ChatWorkspace />
    </Suspense>
  );
}
