import { useMemo, useRef } from "react";

type Props = {
  title: string;
  series: Array<{
    metricId: string;
    label: string;
    values: Array<number | null>;
    color: string;
  }>;
  xAxisTitle: string;
  xUnit?: string;
  yAxisTitle: string;
  yUnit?: string;
  showMarkers?: boolean;
  iterationCount?: number;
};

function metricLabel(title: string, unit?: string) {
  return unit?.trim() ? `${title} (${unit.trim()})` : title;
}

function safeFileName(name: string): string {
  return name.replace(/[<>:"/\\|?*]+/g, "_").replace(/\s+/g, "_").slice(0, 80) || "plot";
}

export default function CombinedPlot({
  title,
  series,
  xAxisTitle,
  xUnit,
  yAxisTitle,
  yUnit,
  showMarkers = false,
  iterationCount,
}: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const numeric = series.flatMap((line) =>
    line.values.filter((v): v is number => typeof v === "number" && Number.isFinite(v))
  );
  const width = 760;
  const height = 350;
  const margin = { top: 20, right: 18, bottom: 62, left: 68 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const totalIterations = Math.max(
    iterationCount ?? 0,
    ...series.map((line) => line.values.length),
    1
  );
  const min = numeric.length ? Math.min(...numeric) : 0;
  const max = numeric.length ? Math.max(...numeric) : 1;
  const span = max - min || 1;

  const prepared = useMemo(
    () =>
      series.map((line) => {
        const points = line.values
          .map((value, index) => {
            if (value === null || !Number.isFinite(value)) return null;
            const iteration = index + 1;
            const x = margin.left + ((iteration - 1) / Math.max(totalIterations - 1, 1)) * plotWidth;
            const y = margin.top + ((max - value) / span) * plotHeight;
            return { x, y, value };
          })
          .filter((p): p is { x: number; y: number; value: number } => p !== null);
        return {
          ...line,
          points,
          polyline: points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" "),
        };
      }),
    [series, margin.left, margin.top, max, plotHeight, plotWidth, span, totalIterations]
  );

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
    const headers = ["run_index", ...series.map((line) => line.label)];
    const rows = Array.from({ length: totalIterations }, (_, idx) => {
      const row = [String(idx + 1), ...series.map((line) => (line.values[idx] ?? "").toString())];
      return row.join(",");
    });
    const blob = new Blob([[headers.join(","), ...rows].join("\n")], { type: "text/csv;charset=utf-8" });
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
        <div className="plot-empty">Not enough data points for combined view.</div>
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
            {prepared.map((line) => (
              <g key={line.metricId}>
                <polyline points={line.polyline} className="plot-line" style={{ stroke: line.color }} />
                {showMarkers &&
                  line.points.map((p, idx) => (
                    <circle
                      key={`${line.metricId}-${idx}`}
                      cx={p.x}
                      cy={p.y}
                      r={2.7}
                      className="plot-marker"
                      style={{ fill: line.color }}
                    />
                  ))}
              </g>
            ))}
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
            {series.map((line) => (
              <span key={line.metricId}>
                <i style={{ backgroundColor: line.color }} /> {line.label}
              </span>
            ))}
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
