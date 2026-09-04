import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { Responsive, WidthProvider } from "react-grid-layout";
import type { ReactNode } from "react";
import type { Chart } from "../../types/dashboard";

const ResponsiveGridLayout = WidthProvider(Responsive);

export function GridWorkspace({
  charts,
  editable,
  onLayoutChange,
  renderChart,
}: {
  charts: Chart[];
  editable: boolean;
  onLayoutChange?: (layout: { i: string; x: number; y: number; w: number; h: number }[]) => void;
  renderChart: (chart: Chart) => ReactNode;
}) {
  const layout = charts.map((c) => ({ i: c.id, x: c.layout_x, y: c.layout_y, w: c.layout_w, h: c.layout_h }));

  return (
    <ResponsiveGridLayout
      className="layout"
      layouts={{ lg: layout }}
      breakpoints={{ lg: 0 }}
      cols={{ lg: 12 }}
      rowHeight={60}
      isDraggable={editable}
      isResizable={editable}
      draggableCancel="button, .echarts-for-react"
      onLayoutChange={(current) => onLayoutChange?.(current.map((l) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h })))}
    >
      {charts.map((chart) => (
        <div key={chart.id}>{renderChart(chart)}</div>
      ))}
    </ResponsiveGridLayout>
  );
}
