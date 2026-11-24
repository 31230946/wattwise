import { Card, Seg, Notice } from "./ui.jsx";
import { ShareBars } from "./charts.jsx";
import { num, rs } from "../format.js";

const HOME_TYPES = [["1bhk", "1 BHK"], ["2bhk", "2 BHK"], ["3bhk", "3 BHK"], ["villa", "Villa / bungalow"]];
const WHEN = { morning: "Morning", day: "Daytime", evening: "Evening", night: "Night", all_day: "All day" };

// ADVANCED (optional): appliance list -> rough split of where the units go. Makes the tip more specific.
// ACs, fridges and ceiling fans can take a BEE star rating; the estimate is always scaled to the meter total.
const STARS = [["", "Star rating: not sure"], ["1", "1-star"], ["2", "2-star"], ["3", "3-star"], ["4", "4-star"], ["5", "5-star"]];

export function ApplianceEditor({ meta, items, setItems }) {
  const types = meta ? Object.entries(meta.appliance_types) : [];
  const starTypes = new Set(meta?.appliance_star_types || []);
  const upd = (i, patch) => setItems(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const setType = (i, t) => upd(i, { type: t, star: starTypes.has(t) ? items[i].star : "", ...(t === "fridge" ? { when: "all_day" } : {}) });
  return (
    <details className="more">
      <summary>Advanced: appliance breakdown (optional)</summary>
      <div className="hint" style={{ marginTop: -4, marginBottom: 10 }}>
        List your main appliances to see roughly where your units go and get a more specific tip. ACs, fridges and fans can use their BEE star rating.
        It's an estimate (typical or star-label energy use × your hours, scaled to your meter), not a measurement.
      </div>
      {items.map((it, i) => (
        <div className="app-card" key={i}>
          <div className="app-line">
            <select className="input" aria-label="Appliance" value={it.type} onChange={(e) => setType(i, e.target.value)}>
              {types.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
            <button type="button" className="x" aria-label="Remove appliance" onClick={() => setItems(items.filter((_, j) => j !== i))}>×</button>
          </div>
          <div className="app-line app-grid">
            <label><span>How many</span>
              <input className="input" inputMode="numeric" value={it.count} onChange={(e) => upd(i, { count: e.target.value })} /></label>
            <label><span>Hours/day</span>
              <input className="input" inputMode="decimal" value={it.when === "all_day" ? "24" : it.hours_per_day}
                disabled={it.when === "all_day"} onChange={(e) => upd(i, { hours_per_day: e.target.value })} /></label>
            <label><span>When</span>
              <select className="input" value={it.when} onChange={(e) => upd(i, { when: e.target.value })}>
                {Object.entries(WHEN).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></label>
          </div>
          {starTypes.has(it.type) && (
            <select className="input" aria-label="BEE star rating" value={it.star || ""} onChange={(e) => upd(i, { star: e.target.value })}>
              {STARS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
            </select>
          )}
        </div>
      ))}
      <button type="button" className="btn small" disabled={!meta}
        onClick={() => setItems([...items, { type: "ceiling_fan", count: "1", hours_per_day: "8", when: "evening", star: "" }])}>+ Add appliance</button>
    </details>
  );
}

export function appliancesForApi(items, starTypes = []) {
  if (!items.length) return null;
  const st = new Set(starTypes);
  return items.map((it) => ({
    type: it.type,
    count: Math.max(1, parseInt(it.count, 10) || 1),
    when: it.when,
    hours_per_day: it.when === "all_day" ? null : Math.min(24, Math.max(0, Number(it.hours_per_day) || 0)),
    ...(it.star && st.has(it.type) ? { star_rating: Number(it.star) } : {}),
  }));
}

export function HomeAndMeter({ home, setHome, sm, setSm }) {
  return (
    <>
      <div className="field">
        <span className="label">Home size</span>
        <Seg label="Home size" value={home} onChange={setHome} options={HOME_TYPES} />
        <div className="hint">Only used to compare you with similar homes. It doesn't change the forecast.</div>
      </div>
      <div className="field">
        <label className="check"><input type="checkbox" checked={sm} onChange={(e) => setSm(e.target.checked)} />
          <span>I have a smart / time-of-day meter</span></label>
      </div>
    </>
  );
}

export function PeerCard({ peer }) {
  if (!peer) return null;
  const pct = peer.you_vs_peers_pct;
  return (
    <Card title="You vs similar homes" sub={`${peer.home_type.toUpperCase()} homes use about ${num(peer.peer_mean_kwh_per_day, 1)} kWh a day.`}>
      <div className="stat" style={{ border: 0, padding: 0, background: "none" }}>
        <div className="v" style={{ color: pct > 10 ? "var(--amber)" : "var(--emerald)" }}>{pct > 0 ? "+" : ""}{num(pct, 0)}%</div>
        <div className="n">{pct > 10 ? "You're using more than similar homes." : pct < -10 ? "You're using less than similar homes. Nice." : "About the same as similar homes."}</div>
      </div>
      <p className="small-print" style={{ marginTop: 8 }}>{peer.note}</p>
    </Card>
  );
}

export function ApplianceCard({ b }) {
  if (!b) return null;
  return (
    <Card title="Where your units probably go" sub="Estimate from your appliance list (typical or BEE star-label energy use × your hours), scaled to your meter total.">
      {b.hours_look_off && <div style={{ marginBottom: 10 }}><Notice kind="warn"><span>⚠</span><span>Your hours add up to much more or less than your meter shows. Check them; the split below may be off.</span></Notice></div>}
      <ShareBars items={b.items.map((i) => ({ label: `${i.label}${i.count > 1 ? ` ×${i.count}` : ""}${i.star_rating ? ` · ${i.star_rating}★` : ""}`, value: i.kwh, text: `${num(i.share_pct)}%` }))} />
      <p className="small-print" style={{ marginTop: 10 }}>{b.note}</p>
    </Card>
  );
}

export function BillCard({ bill, carbon }) {
  return (
    <div className="stats">
      <div className="stat"><div className="k">Next month's bill (est.)</div><div className="v">{rs(bill.estimated_bill_rs)}</div>
        <div className="n">{num(bill.monthly_units)} units · slab {bill.current_slab}</div></div>
      <div className="stat amber"><div className="k">Each unit you cut saves</div><div className="v">₹{num(bill.marginal_rate_rs_per_kwh, 2)}</div>
        <div className="n">{bill.units_to_next_slab_line > 0 && bill.units_to_next_slab_line < 40 ? `${num(bill.units_to_next_slab_line)} units from the next slab` : "at your current slab"}</div></div>
      <div className="stat"><div className="k">Carbon next month</div><div className="v">{num(carbon.kg_co2)} kg</div><div className="n">CO₂ (CEA grid average)</div></div>
    </div>
  );
}
