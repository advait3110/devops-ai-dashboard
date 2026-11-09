/*
 * Hand-written SVG charts.
 * A charting library (recharts, chart.js) would add 100-400 KB of JavaScript.
 * A line chart is just: scale values to pixels and join them with a <path>.
 */
import { useEffect, useMemo, useRef, useState } from "react";

function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    if (!ref.current) return undefined;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

/**
 * series: [{ name, color, points: [[timestampSeconds, value], ...] }]
 */
export function LineChart({ series, height = 180, yMax, yNice, yFormat = (v) => v.toFixed(0), area = true, label }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const { xMin, xMax, top } = useMemo(() => {
    const all = series.flatMap((s) => s.points.filter((p) => p[1] !== null));
    if (!all.length) return { xMin: 0, xMax: 1, top: yMax || 1 };
    const xs = all.map((p) => p[0]);
    const maxV = Math.max(...all.map((p) => p[1]));
    return {
      xMin: Math.min(...xs),
      xMax: Math.max(...xs),
      top: yMax ?? (maxV <= 0 ? 1 : (yNice || niceCeil)(maxV * 1.15)),
    };
  }, [series, yMax, yNice]);

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);
  // Left margin grows with the longest axis label ("9.5 MB/s" needs more room than "50%").
  const labelWidth = Math.max(...ticks.map((v) => yFormat(v).length)) * 6.6 + 12;
  const pad = { top: 10, right: 12, bottom: 22, left: Math.max(36, labelWidth) };
  const w = width - pad.left - pad.right;
  const h = height - pad.top - pad.bottom;
  const x = (t) => pad.left + ((t - xMin) / Math.max(xMax - xMin, 1)) * w;
  const y = (v) => pad.top + h - (Math.min(v, top) / top) * h;
  const empty = !series.some((s) => s.points.length > 1);

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const t = xMin + ((px - pad.left) / w) * (xMax - xMin);
    setHover(t);
  };

  const hoverPoints =
    hover === null
      ? []
      : series.map((s) => {
          let best = null;
          for (const p of s.points) if (!best || Math.abs(p[0] - hover) < Math.abs(best[0] - hover)) best = p;
          return { ...s, point: best };
        });
  const hoverT = hoverPoints[0]?.point?.[0];

  return (
    <div className="chart" ref={ref}>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={label || series.map((s) => s.name).join(", ")}
        onMouseMove={empty ? undefined : onMove}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.left} x2={width - pad.right} y1={y(v)} y2={y(v)} className="grid" />
            <text x={pad.left - 8} y={y(v) + 4} textAnchor="end" className="axis">
              {yFormat(v)}
            </text>
          </g>
        ))}
        {!empty &&
          [xMin, (xMin + xMax) / 2, xMax].map((t, i) => (
            <text key={i} x={x(t)} y={height - 4} textAnchor={["start", "middle", "end"][i]} className="axis">
              {new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </text>
          ))}
        {series.map((s) => {
          const pts = s.points.filter((p) => p[1] !== null);
          if (pts.length < 2) return null;
          const line = pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
          const fill = `${line}L${x(pts.at(-1)[0])},${pad.top + h}L${x(pts[0][0])},${pad.top + h}Z`;
          return (
            <g key={s.name}>
              {area && <path d={fill} fill={s.color} opacity="0.1" />}
              <path d={line} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" />
            </g>
          );
        })}
        {hoverT !== undefined && (
          <g>
            <line x1={x(hoverT)} x2={x(hoverT)} y1={pad.top} y2={pad.top + h} className="crosshair" />
            {hoverPoints.map(
              (s) => s.point && <circle key={s.name} cx={x(s.point[0])} cy={y(s.point[1])} r="3.5" fill={s.color} />,
            )}
          </g>
        )}
        {empty && (
          <text x={width / 2} y={height / 2} textAnchor="middle" className="axis">
            Collecting data…
          </text>
        )}
      </svg>
      {hoverT !== undefined && (
        <div className="chart-tip" style={{ left: Math.min(x(hoverT) + 10, width - 150) }}>
          <div className="tip-time">{new Date(hoverT * 1000).toLocaleTimeString()}</div>
          {hoverPoints.map(
            (s) =>
              s.point && (
                <div key={s.name}>
                  <span className="swatch" style={{ background: s.color }} />
                  {s.name}: <b>{yFormat(s.point[1])}</b>
                </div>
              ),
          )}
        </div>
      )}
      {series.length > 1 && (
        <div className="legend">
          {series.map((s) => (
            <span key={s.name}>
              <span className="swatch" style={{ background: s.color }} />
              {s.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function niceCeil(v) {
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / p) * p;
}

/** Ring gauge for a percentage. */
export function Gauge({ value = 0, label, detail, warn = 75, crit = 90 }) {
  const r = 42;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, value || 0));
  const t = v >= crit ? "crit" : v >= warn ? "warn" : "ok";
  return (
    <div className="gauge">
      <svg viewBox="0 0 100 100" role="img" aria-label={`${label} ${v.toFixed(1)} percent`}>
        <circle cx="50" cy="50" r={r} className="gauge-track" />
        <circle
          cx="50"
          cy="50"
          r={r}
          className={`gauge-value stroke-${t}`}
          strokeDasharray={`${(v / 100) * c} ${c}`}
          transform="rotate(-90 50 50)"
        />
        <text x="50" y="54" textAnchor="middle" className="gauge-num">
          {v.toFixed(0)}%
        </text>
      </svg>
      <div className="gauge-label">{label}</div>
      {detail && <div className="gauge-detail">{detail}</div>}
    </div>
  );
}
