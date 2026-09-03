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

  const load = () => {
    if (id) api.dashboards.get(id).then(setDashboard);
  };

  useEffect(load, [id]);

  if (!dashboard) return <div className="p-8">Cargando…</div>;

  const saveName = async (name: string) => {
    setDashboard({ ...dashboard, name });
    await api.dashboards.update(dashboard.id, { name });
  };

  const saveDescription = async (description: string) => {
    setDashboard({ ...dashboard, description });
    await api.dashboards.update(dashboard.id, { description });
  };

  const addChart = async (chart: Omit<Chart, "id" | "dashboard_id">) => {
    await api.charts.create(dashboard.id, chart);
    load();
  };

  const removeChart = async (chartId: string) => {
    await api.charts.delete(chartId);
    load();
  };

  const onLayoutChange = async (layout: { i: string; x: number; y: number; w: number; h: number }[]) => {
    for (const l of layout) {
      await api.charts.update(l.i, { layout_x: l.x, layout_y: l.y, layout_w: l.w, layout_h: l.h });
    }
  };

  const publish = async () => {
    await api.dashboards.publish(dashboard.id);
    navigate(`/dashboards/${dashboard.id}`);
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
        <ChartForm topicPrefix="" onSubmit={addChart} />
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
            <ChartRenderer dashboardId={dashboard.id} chart={chart} editable onRemove={() => removeChart(chart.id)} />
          )}
        />
      </div>
    </div>
  );
}
