import { useState, useEffect, useCallback } from "react";
import { api } from "./api/client";
import type { EnterpriseTree, SelectedNode } from "./types/uns";
import { AppHeader } from "./components/AppHeader";
import { CatalogView } from "./components/CatalogView";
import { WorkspaceView } from "./components/WorkspaceView";
import { BrokersView } from "./components/BrokersView";
import { NodeTypesView } from "./components/NodeTypesView";

export type AppView = "catalog" | "workspace" | "brokers" | "nodetypes";

export default function App() {
  const [view, setView] = useState<AppView>("catalog");
  const [tree, setTree] = useState<EnterpriseTree[]>([]);
  const [selected, setSelected] = useState<SelectedNode | null>(null);
  const [activeEnterpriseId, setActiveEnterpriseId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setTree(await api.tree.get());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const openWorkspace = (enterpriseId: string) => {
    setActiveEnterpriseId(enterpriseId);
    setView("workspace");
  };

  const activeEnterprise = tree.find(e => e.id === activeEnterpriseId) ?? tree[0] ?? null;

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-surface-subtle">
      <AppHeader
        view={view}
        setView={setView}
        activeEnterprise={activeEnterprise}
        onBack={() => setView("catalog")}
      />
      {view === "catalog" ? (
        <CatalogView
          tree={tree}
          loading={loading}
          onOpen={openWorkspace}
          onRefresh={refresh}
        />
      ) : view === "workspace" && activeEnterprise ? (
        <WorkspaceView
          enterprise={activeEnterprise}
          selected={selected}
          onSelect={setSelected}
          onRefresh={refresh}
        />
      ) : view === "brokers" ? (
        <BrokersView />
      ) : view === "nodetypes" ? (
        <NodeTypesView />
      ) : (
        <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
          Coming soon
        </div>
      )}
    </div>
  );
}
