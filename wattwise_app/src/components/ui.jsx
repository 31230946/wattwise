import { rs, rs2, num } from "../format.js";

export function Card({ title, sub, children }) {
  return (
    <section className="card">
      {title && (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
          <div>
            <h3>{title}</h3>
            {sub && <div className="sub">{sub}</div>}
          </div>
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ k, v, n, tone = "" }) {
  return (
    <div className={`stat ${tone}`}>
      <div className="k">{k}</div>
      <div className="v">{v}</div>
      {n && <div className="n">{n}</div>}
    </div>
  );
}

export function Seg({ options, value, onChange, label }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map(([val, text]) => (
        <button type="button" key={String(val)} className={value === val ? "on" : ""} role="radio"
          aria-checked={value === val} onClick={() => onChange(val)}>{text}</button>
      ))}
    </div>
  );
}

export function Notice({ kind = "", children }) {
  return <div className={`notice ${kind}`}>{children}</div>;
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return <Notice kind="err"><span>⚠</span><span>{error}</span></Notice>;
}

export function Empty({ title, children }) {
  return <div className="empty"><b>{title}</b>{children}</div>;
}

export function Spin() { return <span className="spinner" aria-hidden="true" />; }

// MSEDCL slab breakdown table (from the API's bill.breakdown)
export function SlabTable({ breakdown }) {
  if (!breakdown) return null;
  return (
    <div className="table-scroll">
      <table className="table">
        <thead><tr><th>Slab (units)</th><th className="r">Units</th><th className="r">Rate</th><th className="r">Amount</th></tr></thead>
        <tbody>
          {breakdown.slabs.map((s) => (
            <tr key={s.slab}><td>{s.slab}</td><td className="r">{num(s.units, 1)}</td><td className="r">{rs2(s.rate_rs)}</td><td className="r">{rs2(s.energy_rs)}</td></tr>
          ))}
          <tr><td>Wheeling charge</td><td className="r" colSpan={2}>₹1.20 × units</td><td className="r">{rs2(breakdown.wheeling_rs)}</td></tr>
          <tr><td>Fixed charge</td><td className="r" colSpan={2}>per month</td><td className="r">{rs2(breakdown.fixed_rs)}</td></tr>
          <tr className="total"><td>Total</td><td colSpan={2}></td><td className="r">{rs(breakdown.total_rs)}</td></tr>
        </tbody>
      </table>
      <div className="hint">Excludes {breakdown.excludes}. MSEDCL residential tariff FY 2026-27.</div>
    </div>
  );
}

export function SavingsLine({ s }) {
  if (!s) return null;
  return (
    <Notice>
      <span>🌱</span>
      <span><b>If you follow the tips:</b> {s.message} <span className="small-print">(Estimate from other studies, not a measured WattWise result.)</span></span>
    </Notice>
  );
}

export function Tip({ rec }) {
  if (!rec) return null;
  const quiet = rec.action === "no_action";
  return (
    <section className="card tip">
      <span className="tag">{quiet ? "You're doing well" : "Your tip"}</span>
      <h3>{rec.title}</h3>
      <p>{rec.message}</p>
      {!quiet && (
        <div className="chips">
          {rec.saving_rs_per_month != null && <span className="chip green">Save ~{rs(rec.saving_rs_per_month)}/month</span>}
          {rec.saving_kg_co2_per_month != null && <span className="chip green">−{num(rec.saving_kg_co2_per_month, 1)} kg CO₂/month</span>}
          {rec.target_appliance && <span className="chip">{rec.target_appliance}</span>}
        </div>
      )}
    </section>
  );
}

export function Defaults({ list, notes }) {
  if ((!list || !list.length) && (!notes || !notes.length)) return null;
  return (
    <details className="more">
      <summary>About these numbers</summary>
      <ul className="small-print">
        {(notes || []).map((n) => <li key={n}>{n}</li>)}
        {list && list.length > 0 && <li>Filled in for you because you didn't enter them: {list.join(", ")}.</li>}
      </ul>
    </details>
  );
}
