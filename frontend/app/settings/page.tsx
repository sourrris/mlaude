import { Suspense } from "react";

import { WorkspaceChrome } from "@/components/ui/workspace-chrome";
import { ModelSettingsPanel } from "@/components/settings/model-settings";

export default function SettingsPage() {
  return (
    <Suspense fallback={null}>
      <WorkspaceChrome activeSection="settings">
        <ModelSettingsPanel />
      </WorkspaceChrome>
    </Suspense>
  );
}
