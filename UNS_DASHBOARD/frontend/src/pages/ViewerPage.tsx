import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { GridWorkspace } from "../components/editor/GridWorkspace";
import { ChartRenderer } from "../components/ChartRenderer";
import type { DashboardDetail } from "../types/dashboard";

export function ViewerPage() {
  const { id } = useParams<{ id: string }>();
  const [dashboard, setDashboard] = useState<DashboardDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setLoadError(null);
    if (id) api.dashboards.get(id).then(setDashboard).catch(() => setLoadError("No se pudo cargar el dashboard."));
  }, [id]);

  if (loadError) return <div className="p-8 text-danger">{loadError}</div>;
  if (!dashboard) return <div className="p-8">Cargando…</div>;

  return (
    <div className="min-h-screen bg-surface-subtle">
      <div className="flex items-center justify-between bg-surface border-b border-border px-8 py-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-bold text-ink">{dashboard.name}</h1>
            <span className="bg-surface-subtle text-ink-muted text-xs font-semibold rounded-full px-2 py-0.5">Solo visualización</span>
          </div>
          <p className="text-xs text-ink-secondary">{dashboard.description}</p>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/" className="border border-border rounded-lg px-4 py-2 text-sm font-semibold">Dashboards</Link>
          <Link to={`/dashboards/${dashboard.id}/edit`} className="bg-accent text-white rounded-lg px-4 py-2 text-sm font-bold">Editar</Link>
        </div>
      </div>
      <div className="p-6">
        <GridWorkspace
          charts={dashboard.charts}
          editable={false}
          renderChart={(chart) => <ChartRenderer dashboardId={dashboard.id} chart={chart} editable={false} />}
        />
      </div>
    </div>
  );
}
