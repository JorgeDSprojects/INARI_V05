import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { GridWorkspace } from "../components/editor/GridWorkspace";
import { DashboardMetaForm } from "../components/editor/DashboardMetaForm";
import { ChartForm } from "../components/editor/ChartForm";
import { ChartRenderer } from "../components/ChartRenderer";
import type { Chart, DashboardDetail } from "../types/dashboard";

export function EditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState<DashboardDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editingChart, setEditingChart] = useState<Chart | null>(null);

  const load = () => {
    setLoadError(null);
    if (id) api.dashboards.get(id).then(setDashboard).catch(() => setLoadError("No se pudo cargar el dashboard."));
  };

  useEffect(load, [id]);

  if (loadError) return <div className="p-8 text-danger">{loadError}</div>;
  if (!dashboard) return <div className="p-8">Cargando…</div>;

  const fail = () => window.alert("La operación falló. Inténtalo de nuevo.");

  const saveName = async (name: string) => {
    setDashboard({ ...dashboard, name });
    await api.dashboards.update(dashboard.id, { name }).catch(fail);
  };

  const saveDescription = async (description: string) => {
    setDashboard({ ...dashboard, description });
    await api.dashboards.update(dashboard.id, { description }).catch(fail);
  };

  const submitChart = async (chart: Omit<Chart, "id" | "dashboard_id">) => {
    if (editingChart) {
      const { layout_x, layout_y, layout_w, layout_h, ...rest } = chart;
      await api.charts.update(editingChart.id, rest).then(load).then(() => setEditingChart(null)).catch(fail);
    } else {
      await api.charts.create(dashboard.id, chart).then(load).catch(fail);
    }
  };

  const removeChart = async (chartId: string) => {
    await api.charts.delete(chartId).then(load).catch(fail);
    if (editingChart?.id === chartId) setEditingChart(null);
  };

  const onLayoutChange = async (layout: { i: string; x: number; y: number; w: number; h: number }[]) => {
    for (const l of layout) {
      await api.charts.update(l.i, { layout_x: l.x, layout_y: l.y, layout_w: l.w, layout_h: l.h }).catch(fail);
    }
  };

  const publish = async () => {
    await api.dashboards.publish(dashboard.id).then(() => navigate(`/dashboards/${dashboard.id}`)).catch(fail);
  };

  return (
    <div className="flex h-screen">
      <div className="w-96 border-r border-border p-6 overflow-y-auto flex flex-col gap-6">
        <DashboardMetaForm
          name={dashboard.name}
          description={dashboard.description ?? ""}
          onChangeName={saveName}
          onChangeDescription={saveDescription}
        />
        <ChartForm key={editingChart?.id ?? "new"} initial={editingChart ?? undefined} onSubmit={submitChart} onCancel={() => setEditingChart(null)} />
        <button onClick={publish} className="bg-accent text-white rounded-lg py-3 font-bold">
          Publicar dashboard
        </button>
      </div>
      <div className="flex-1 p-6 overflow-y-auto bg-surface-subtle">
        <GridWorkspace
          charts={dashboard.charts}
          editable
          onLayoutChange={onLayoutChange}
          renderChart={(chart) => (
            <ChartRenderer
              dashboardId={dashboard.id}
              chart={chart}
              editable
              onRemove={() => removeChart(chart.id)}
              onEdit={() => setEditingChart(chart)}
            />
          )}
        />
      </div>
    </div>
  );
}
