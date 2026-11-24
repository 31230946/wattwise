import { useState } from "react";
import { api } from "../api.js";
import { parseNumbers, isoDate, num, rs } from "../format.js";
import { Card, Stat, Seg, ErrorBox, Empty, Spin, SlabTable, SavingsLine, Tip, Defaults } from "../components/ui.jsx";
import { ForecastChart } from "../components/charts.jsx";
import { ApplianceEditor, appliancesForApi, HomeAndMeter, PeerCard, ApplianceCard, BillCard } from "../components/forecastBits.jsx";

const CFG = {
  title: "Daily forecast",
  intro: "Note your electricity meter reading at about the same time every day. After 7 days, WattWise forecasts your next day, week and month, with what it means for your bill and carbon footprint.",
  unit: "day", min: 7, max: 28,
  valuesLabel: "kWh used each day, oldest first",
  readingsLabel: "Meter reading each day, oldest first",
  valuesHint: "7 to 28 values. Separate with spaces, commas or new lines.",
  readingsHint: "8 to 29 readings (the number on the meter). We work out each day's use from the difference.",
  sample: {
    values: "5.2 5.6 6.1 5.4 5.0 6.8 6.5 5.3 5.7 6.2 5.5 5.1 7.0 6.6 5.6 5.9 6.4 5.4 5.2 7.1 6.7 5.5 5.2 6.1 5.8 6.6 6.3 5.9",
    home: "2bhk",
    appliances: [
      { type: "ceiling_fan", count: "3", hours_per_day: "9", when: "evening", star: "3" },
      { type: "fridge", count: "1", hours_per_day: "", when: "all_day", star: "4" },
      { type: "geyser", count: "1", hours_per_day: "0.5", when: "morning" },
      { type: "tv", count: "1", hours_per_day: "3", when: "evening" },
      { type: "led_lights", count: "1", hours_per_day: "5", when: "evening" },
      { type: "washing_machine", count: "1", hours_per_day: "0.5", when: "day" },
    ],
  },
};

export default function ForecastPage({ meta }) {
  const c = CFG;
  const yesterday = new Date(Date.now() - 864e5);
  const [mode, setMode] = useState("values");
  const [text, setText] = useState("");
  const [date, setDate] = useState(isoDate(yesterday));
  const [home, setHome] = useState("2bhk");
  const [sm, setSm] = useState(false);
  const [apps, setApps] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [res, setRes] = useState(null);

  async function submit(e, override) {
    e && e.preventDefault();
    const t = override ? override.values : text;
    const m = override ? "values" : mode;
    const ap = override ? override.appliances : apps;
    const h = override ? override.home : home;
    setErr("");
    const { nums, bad } = parseNumbers(t);
    if (bad.length) return setErr(`These aren't numbers: ${bad.slice(0, 3).join(", ")}`);
    const need = m === "values" ? c.min : c.min + 1;
    if (nums.length < need) return setErr(`Enter at least ${need} ${m === "values" ? `${c.unit}s of kWh` : "meter readings"} (you have ${nums.length}).`);
    const key = m === "values" ? "daily_kwh" : "daily_meter_readings";
    const body = { [key]: nums.slice(-(m === "values" ? c.max : c.max + 1)), home_type: h, has_smart_meter: sm, last_reading_date: date };
    const al = appliancesForApi(ap, meta?.appliance_star_types);
    if (al) body.appliances = al;
    setBusy(true);
    try {
      const out = await api.daily(body);
      const past = m === "values" ? body[key] : body[key].slice(1).map((v, i) => v - body[key][i]);
      setRes({ out, past, date });
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  function sample() {
    const s = c.sample;
    setMode("values"); setText(s.values); setHome(s.home); setApps(s.appliances);
    submit(null, s);
  }

  const count = parseNumbers(text).nums.length;

  return (
    <>
      <div className="page-intro">
        <h2>{c.title} <span style={{ fontSize: "0.8rem", color: "var(--cyan)", verticalAlign: 3 }}>machine learning</span></h2>
        <p>{c.intro}</p>
      </div>
      <div className="grid-main">
        <form className="card sticky" onSubmit={submit}>
          <h3>Your readings</h3>
          <div className="field" style={{ marginTop: 10 }}>
            <Seg label="Input type" value={mode} onChange={setMode}
              options={[["values", `kWh per ${c.unit}`], ["readings", "Meter readings"]]} />
          </div>
          <div className="field">
            <label htmlFor="daily-t">{mode === "values" ? c.valuesLabel : c.readingsLabel} <span className="muted">({count})</span></label>
            <textarea id="daily-t" className="input" value={text} onChange={(e) => setText(e.target.value)}
              placeholder={mode === "values" ? c.sample.values.split(" ").slice(0, 8).join(", ") + ", ..." : "12034, 12040, 12046, ..."} />
            <div className="hint">{mode === "values" ? c.valuesHint : c.readingsHint}</div>
          </div>
          <div className="field">
            <label htmlFor="d-date">Date of the last value</label>
            <input id="d-date" type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <HomeAndMeter home={home} setHome={setHome} sm={sm} setSm={setSm} />
          <ApplianceEditor meta={meta} items={apps} setItems={setApps} />
          <ErrorBox error={err} />
          <div className="btns" style={{ marginTop: 12 }}>
            <button className="btn primary" disabled={busy}>{busy && <Spin />}Forecast</button>
            <button type="button" className="btn" onClick={sample} disabled={busy}>Try a sample home</button>
          </div>
        </form>

        <div className="stack">
          {!res && <Empty title="Your forecast will appear here">Enter at least {c.min} {c.unit}s, or try the sample home.</Empty>}
          {res && <DailyResults r={res} />}
        </div>
      </div>
    </>
  );
}

function Range({ r }) {
  return <>likely {num(r[0], 1)}–{num(r[1], 1)}</>;
}

function DailyResults({ r }) {
  const o = r.out;
  const f = o.forecast;
  const end = new Date(r.date + "T00:00:00");
  const label = (i, n) => {
    const d = new Date(end.getTime() - (n - 1 - i) * 864e5);
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  };
  return (
    <>
      {o.input_summary.low_history && <div className="notice warn"><span>ℹ</span><span>With less than 2 weeks of readings the forecast is rougher. Keep adding days.</span></div>}
      <div className="stats">
        <Stat k={`Tomorrow (${new Date(f.next_day.period + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })})`}
          v={`${num(f.next_day.kwh, 1)} kWh`} n={<Range r={f.next_day.range_80pct} />} tone="amber" />
        <Stat k="Next 7 days" v={`${num(f.next_7_days.kwh, 0)} kWh`} n={<><Range r={f.next_7_days.range_80pct} /> · {num(f.next_7_days.kg_co2)} kg CO₂</>} />
        <Stat k="Next 30 days" v={`${num(f.next_30_days.kwh, 0)} kWh`} n={<><Range r={f.next_30_days.range_80pct} /> · {num(f.next_30_days.kg_co2)} kg CO₂</>} />
      </div>
      <Card title="Your days and tomorrow" sub="'Likely' range: in testing on homes the model had never seen, 8 out of 10 real values fell inside it.">
        <ForecastChart past={r.past} next={f.next_day.kwh} nextLabel="Tomorrow" range={f.next_day.range_80pct}
          avg={f.next_30_days.kwh_per_day} pastLabel={label} />
      </Card>
      <Tip rec={o.recommendation} />
      <BillCard bill={o.bill} carbon={o.carbon} />
      <div className="row2">
        <Card title="Next month's bill, slab by slab" sub={`Based on the ${o.bill.based_on}.`}><SlabTable breakdown={o.bill.breakdown} /></Card>
        <div className="stack">
          <PeerCard peer={o.peer_group} />
          <ApplianceCard b={o.appliance_breakdown} />
        </div>
      </div>
      <SavingsLine s={o.expected_savings_if_tips_followed} />
      <Defaults list={o.inputs_defaulted} notes={[...o.notes,
        `Tomorrow = blend of XGBoost (${num(o.model_details.next_day.xgboost, 2)} kWh) and LSTM (${num(o.model_details.next_day.lstm, 2)} kWh).`]} />
    </>
  );
}
