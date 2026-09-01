import type { EnterpriseTree, SelectedNode } from "../types/uns";
import { TreePanel } from "./TreePanel";
import { NodeWorkspace } from "./NodeWorkspace";

interface Props {
  enterprise: EnterpriseTree;
  selected: SelectedNode | null;
  onSelect: (node: SelectedNode) => void;
  onRefresh: () => void;
}

export function WorkspaceView({ enterprise, selected, onSelect, onRefresh }: Props) {
  return (
    <div className="flex flex-1 overflow-hidden">
      <TreePanel
        enterprise={enterprise}
        selected={selected}
        onSelect={onSelect}
        onRefresh={onRefresh}
      />
      <NodeWorkspace
        enterprise={enterprise}
        selected={selected}
        onRefresh={onRefresh}
      />
    </div>
  );
}
