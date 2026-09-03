import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Dashboard } from "../types/dashboard";

export function MenuPage() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const navigate = useNavigate();

  const load = () => {
    api.dashboards.list().then(setDashboards);
  };

  useEffect(load, []);

  const createDashboard = async () => {
    const name = window.prompt("Nombre del dashboard");
    if (!name) return;
    const created = await api.dashboards.create({ name });
    navigate(`/dashboards/${created.id}/edit`);
  };

  const deleteDashboard = async (id: string) => {
    if (!window.confirm("¿Eliminar este dashboard?")) return;
    await api.dashboards.delete(id);
    load();
  };

  return (
    <div className="min-h-screen bg-surface-subtle p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">SCADA Dashboards</h1>
          <p className="text-ink-secondary text-sm">Dashboard authoring and production publishing</p>
        </div>
        <button onClick={createDashboard} className="bg-accent text-white px-4 py-2 rounded-lg font-semibold">
          + Nuevo dashboard
        </button>
      </div>
      <div className="bg-surface rounded-xl border border-border p-6">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-ink-muted text-xs uppercase border-b border-border">
              <th className="py-2">Nombre</th>
              <th>Descripción</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {dashboards.map((d) => (
              <tr key={d.id} className="border-b border-border-subtle">
                <td className="py-3 font-semibold text-ink">{d.name}</td>
                <td className="text-ink-secondary">{d.description}</td>
                <td>
                  <span className={d.status === "published" ? "text-success" : "text-warning"}>
                    {d.status === "published" ? "Publicado" : "Borrador"}
                  </span>
                </td>
                <td className="space-x-2">
                  <Link to={`/dashboards/${d.id}`} className="border border-border rounded px-3 py-1">Ver</Link>
                  <Link to={`/dashboards/${d.id}/edit`} className="border border-border rounded px-3 py-1">Editar</Link>
                  <button onClick={() => deleteDashboard(d.id)} className="bg-danger-soft text-danger rounded px-3 py-1">Eliminar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
