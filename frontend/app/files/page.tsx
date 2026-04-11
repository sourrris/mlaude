import { WorkspaceChrome } from "@/components/ui/workspace-chrome";
import { LibraryManager } from "@/components/files/library-manager";

export default function FilesPage() {
  return (
    <WorkspaceChrome activeSection="files">
      <LibraryManager />
    </WorkspaceChrome>
  );
}
