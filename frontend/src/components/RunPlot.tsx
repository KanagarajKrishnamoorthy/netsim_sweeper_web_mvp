import { useMemo, useRef } from "react";

type Props = {
  title: string;
  values: Array<number | null>;
  color?: string;
  xAxisTitle: string;
  xUnit?: string;
  yAxisTitle: string;
  yUnit?: string;
  showMarkers?: boolean;
  legendLabel?: string;
  iterationCount?: number;
};

function metricLabel(title: string, unit?: string) {
  return unit?.trim() ? `${title} (${unit.trim()})` : title;
}

function safeFileName(name: string): string {
  return name.replace(/[<>:"/\\|?*]+/g, "_").replace(/\s+/g, "_").slice(0, 80) || "plot";
}

export default function RunPlot({
  title,
  values,
  color = "#0e8693",
  xAxisTitle,
  xUnit,
  yAxisTitle,
  yUnit,
  showMarkers = false,
  legendLabel,
  iterationCount,
}: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const numeric = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  const width = 700;
  const height = 330;
  const margin = { top: 20, right: 18, bottom: 62, left: 68 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const totalIterations = Math.max(iterationCount ?? 0, values.length, 1);

  const min = numeric.length ? Math.min(...numeric) : 0;
  const max = numeric.length ? Math.max(...numeric) : 1;
  const span = max - min || 1;

  const points = useMemo(
    () =>
      values
        .map((value, index) => {
          if (value === null || !Number.isFinite(value)) return null;
          const iteration = index + 1;
          const x = margin.left + ((iteration - 1) / Math.max(totalIterations - 1, 1)) * plotWidth;
          const y = margin.top + ((max - value) / span) * plotHeight;
          return { x, y, value };
        })
        .filter((p): p is { x: number; y: number; value: number } => p !== null),
    [values, margin.left, margin.top, max, plotHeight, plotWidth, span, totalIterations]
  );

  const polylinePoints = points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");

  function exportSvg() {
    if (!svgRef.current) return;
    const serializer = new XMLSerializer();
    let xml = serializer.serializeToString(svgRef.current);
    if (!xml.includes("xmlns=")) {
      xml = xml.replace("<svg", "<svg xmlns='http://www.w3.org/2000/svg'");
    }
    const blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${safeFileName(title)}.svg`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportCsv() {
    const rows = [
      "run_index,value",
      ...Array.from({ length: totalIterations }, (_, index) => `${index + 1},${values[index] ?? ""}`),
    ];
    const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${safeFileName(title)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => {
    const y = margin.top + fraction * plotHeight;
    const value = max - fraction * span;
    return { y, value };
  });
  const xTickValues = Array.from(
    new Set([1, Math.max(1, Math.round(totalIterations / 2)), totalIterations])
  ).sort((a, b) => a - b);

  return (
    <div className="plot-card">
      <div className="plot-head">
        <div className="plot-title">{title}</div>
        <div className="plot-actions">
          <button type="button" onClick={exportSvg}>
            Export SVG
          </button>
          <button type="button" onClick={exportCsv}>
            Export CSV
          </button>
        </div>
      </div>
      {numeric.length < 2 ? (
        <div className="plot-empty">Not enough completed data points yet.</div>
      ) : (
        <>
          <svg ref={svgRef} viewBox={`0 0 ${width} ${height}`} className="plot-svg">
            <rect x={margin.left} y={margin.top} width={plotWidth} height={plotHeight} className="plot-bg" />
            {yTicks.map((tick) => (
              <g key={tick.y}>
                <line x1={margin.left} y1={tick.y} x2={margin.left + plotWidth} y2={tick.y} className="plot-grid" />
                <text x={margin.left - 8} y={tick.y + 4} className="plot-tick">
                  {tick.value.toFixed(3)}
                </text>
              </g>
            ))}
            <line x1={margin.left} y1={margin.top + plotHeight} x2={margin.left + plotWidth} y2={margin.top + plotHeight} className="plot-axis" />
            <line x1={margin.left} y1={margin.top} x2={margin.left} y2={margin.top + plotHeight} className="plot-axis" />
            {xTickValues.map((tick) => {
              const x = margin.left + ((tick - 1) / Math.max(totalIterations - 1, 1)) * plotWidth;
              return (
                <g key={`x-${tick}`}>
                  <line x1={x} y1={margin.top + plotHeight} x2={x} y2={margin.top + plotHeight + 5} className="plot-axis" />
                  <text x={x} y={margin.top + plotHeight + 18} textAnchor="middle" className="plot-tick plot-tick-x">
                    {tick}
                  </text>
                </g>
              );
            })}
            <polyline points={polylinePoints} className="plot-line" style={{ stroke: color }} />
            {showMarkers &&
              points.map((p, idx) => <circle key={idx} cx={p.x} cy={p.y} r={2.9} className="plot-marker" style={{ fill: color }} />)}
            <text x={margin.left + plotWidth / 2} y={height - 14} textAnchor="middle" className="plot-axis-label">
              {metricLabel(xAxisTitle, xUnit)}
            </text>
            <text
              x={-(margin.top + plotHeight / 2)}
              y={16}
              transform="rotate(-90)"
              textAnchor="middle"
              className="plot-axis-label"
            >
              {metricLabel(yAxisTitle, yUnit)}
            </text>
          </svg>
          <div className="plot-legend">
            <span>
              <i style={{ backgroundColor: color }} /> {legendLabel || title}
            </span>
          </div>
          <div className="plot-range">
            <span>iterations 1..{totalIterations}</span>
            <span>min {min.toFixed(4)}</span>
            <span>max {max.toFixed(4)}</span>
          </div>
        </>
      )}
    </div>
  );
}
