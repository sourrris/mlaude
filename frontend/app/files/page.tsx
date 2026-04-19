import { Suspense } from "react";

import { WorkspaceChrome } from "@/components/ui/workspace-chrome";
import { LibraryManager } from "@/components/files/library-manager";

export default function FilesPage() {
  return (
    <Suspense fallback={null}>
      <WorkspaceChrome activeSection="files">
        <LibraryManager />
      </WorkspaceChrome>
    </Suspense>
  );
}
