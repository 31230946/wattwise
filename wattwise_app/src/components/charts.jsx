import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, LineChart, Line,
  ErrorBar, ReferenceLine, Legend,
} from "recharts";
import { hourLabel, num, rs } from "../format.js";

const AX = { stroke: "#64748b", fontSize: 11, tickLine: false };
const GRID = <CartesianGrid stroke="#24324d" strokeDasharray="3 3" vertical={false} />;
const C = { cyan: "#06b6d4", amber: "#f59e0b", violet: "#a78bfa", slate: "#475569" };

function Tip({ active, payload, label, render }) {
  if (!active || !payload || !payload.length) return null;
  return <div className="tt">{render(payload[0].payload, label)}</div>;
}

// Bill screen: one bar per bill entered
export function BillHistoryChart({ history, months }) {
  const data = history.map((h, i) => ({ ...h, m: months[i] }));
  return (
    <div className="chart" style={{ height: 220 }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          {GRID}
          <XAxis dataKey="m" {...AX} />
          <YAxis {...AX} />
          <Tooltip cursor={{ fill: "rgba(148,163,184,0.08)" }}
            content={<Tip render={(p) => (<><b>{p.m}</b>{num(p.units)} units · {rs(p.bill_rs)} · {num(p.kg_co2)} kg CO₂</>)} />} />
          <Bar dataKey="units" radius={[4, 4, 0, 0]} fill={C.cyan} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// Homes like yours: 12 months, your bills solid, the rest from similar (simulated) homes
export function YearChart({ year }) {
  return (
    <>
      <div className="chart">
        <ResponsiveContainer>
          <BarChart data={year} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            {GRID}
            <XAxis dataKey="month" {...AX} />
            <YAxis {...AX} />
            <Tooltip cursor={{ fill: "rgba(148,163,184,0.08)" }}
              content={<Tip render={(p) => (<><b>{p.month} · {p.source}</b>{num(p.units)} units · {rs(p.bill_rs)} · {num(p.kg_co2)} kg CO₂<br />Slab {p.slab}</>)} />} />
            <ReferenceLine y={100} stroke="#334155" strokeDasharray="4 4" />
            <ReferenceLine y={300} stroke="#334155" strokeDasharray="4 4" label={{ value: "300-unit slab line", fill: "#64748b", fontSize: 10, position: "insideTopRight" }} />
            <Bar dataKey="units" radius={[4, 4, 0, 0]}>
              {year.map((r) => (
                <Cell key={r.month} fill={r.source === "your bill" ? C.cyan : "rgba(167,139,250,0.35)"}
                  stroke={r.source === "your bill" ? C.cyan : C.violet} strokeDasharray={r.source === "your bill" ? "" : "4 3"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="legend">
        <span><i style={{ background: C.cyan }} />Your bills</span>
        <span><i style={{ background: "rgba(167,139,250,0.35)", border: `1px dashed ${C.violet}` }} />Homes like yours (simulated)</span>
      </div>
    </>
  );
}

// Typical day for the last-bill month vs the peak month
export function DayChart({ a, b }) {
  const data = a.hourly_watts.map((w, h) => ({ h, a: w, b: b ? b.hourly_watts[h] : null }));
  const same = !b || b.month === a.month;
  return (
    <div className="chart">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 8, left: -6, bottom: 0 }}>
          {GRID}
          <XAxis dataKey="h" {...AX} tickFormatter={hourLabel} interval={2} />
          <YAxis {...AX} unit=" W" width={56} />
          <Tooltip content={<Tip render={(p) => (<><b>{hourLabel(p.h)}</b>{a.month}: {num(p.a)} W{!same && <><br />{b.month}: {num(p.b)} W</>}</>)} />} />
          <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
          <Line type="monotone" dataKey="a" name={a.month} stroke={C.cyan} strokeWidth={2.5} dot={false} animationDuration={500} />
          {!same && <Line type="monotone" dataKey="b" name={`${b.month} (peak month)`} stroke={C.amber} strokeWidth={2} dot={false} strokeDasharray="5 4" animationDuration={500} />}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// Daily forecast: past values + the next one with its 80% range
export function ForecastChart({ past, next, nextLabel, range, avg, pastLabel }) {
  const data = past.map((v, i) => ({ x: pastLabel(i, past.length), v, kind: "past" }));
  data.push({ x: nextLabel, v: next, kind: "next", err: [next - range[0], range[1] - next] });
  return (
    <>
      <div className="chart">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 12, right: 8, left: -12, bottom: 0 }}>
            {GRID}
            <XAxis dataKey="x" {...AX} interval="preserveStartEnd" minTickGap={14} />
            <YAxis {...AX} />
            <Tooltip cursor={{ fill: "rgba(148,163,184,0.08)" }}
              content={<Tip render={(p) => (<><b>{p.x}</b>{num(p.v, 1)} kWh{p.kind === "next" && <><br />likely {num(range[0], 1)}–{num(range[1], 1)}</>}</>)} />} />
            {avg != null && <ReferenceLine y={avg} stroke={C.amber} strokeDasharray="5 4" />}
            <Bar dataKey="v" radius={[3, 3, 0, 0]}>
              {data.map((d, i) => <Cell key={i} fill={d.kind === "next" ? C.amber : C.slate} />)}
              <ErrorBar dataKey="err" width={8} strokeWidth={2} stroke="#fde68a" direction="y" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="legend">
        <span><i style={{ background: C.slate }} />What you entered</span>
        <span><i style={{ background: C.amber }} />Forecast (line = likely range)</span>
        {avg != null && <span><i style={{ background: "transparent", borderTop: `2px dashed ${C.amber}`, height: 0, width: 16 }} />Forecast average for the next 30 days</span>}
      </div>
    </>
  );
}

export function ShareBars({ items }) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <div className="bars">
      {items.map((i) => (
        <div className="barrow" key={i.label}>
          <span>{i.label}</span>
          <div className="track"><div className="fill" style={{ width: `${(100 * i.value) / max}%` }} /></div>
          <span className="val">{i.text}</span>
        </div>
      ))}
    </div>
  );
}
