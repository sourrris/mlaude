import { WorkspaceChrome } from "@/components/ui/workspace-chrome";
import { ModelSettingsPanel } from "@/components/settings/model-settings";

export default function SettingsPage() {
  return (
    <WorkspaceChrome activeSection="settings">
      <ModelSettingsPanel />
    </WorkspaceChrome>
  );
}
