import { useState } from "react";
import { api } from "../api.js";
import { MONTHS, MONTHS_LONG, lastMonthIndex, rs, rs2, num, hourLabel } from "../format.js";
import { Card, Stat, Seg, Notice, ErrorBox, Empty, Spin, SlabTable, SavingsLine } from "../components/ui.jsx";
import { BillHistoryChart, YearChart, DayChart } from "../components/charts.jsx";

const SAMPLE = { units: ["126", "132", "129"], last: 8, ac: true }; // Jul, Aug, Sep bills of a home with an AC

export default function BillPage() {
  const [units, setUnits] = useState(["", "", ""]);
  const [last, setLast] = useState(lastMonthIndex()); // 0-based month of the LAST bill
  const [ac, setAc] = useState(null);
  const [sm, setSm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [res, setRes] = useState(null);

  const n = units.length;
  const monthOf = (i) => MONTHS[(last - (n - 1 - i) + 24) % 12]; // label for the i-th box

  async function submit(e, override) {
    e && e.preventDefault();
    const u = override ? override.units : units;
    const lm = override ? override.last : last;
    const a = override ? override.ac : ac;
    const vals = u.map((x) => x.trim()).filter((x) => x !== "").map(Number);
    setErr("");
    if (!vals.length) return setErr("Enter the units from at least one bill.");
    if (vals.some((v) => !Number.isFinite(v) || v <= 0)) return setErr("Bill units must be numbers above 0.");
    if (a === null) return setErr("Choose whether your home has an AC.");
    setBusy(true);
    try {
      const body = { monthly_units: vals, has_smart_meter: sm };
      const [bill, like] = await Promise.allSettled([
        api.bill(body),
        api.likeYours({ ...body, last_bill_month: lm + 1, has_ac: a }),
      ]);
      if (bill.status === "rejected") throw bill.reason;
      setRes({
        bill: bill.value, like: like.status === "fulfilled" ? like.value : null,
        likeErr: like.status === "rejected" ? like.reason.message : "",
        months: vals.map((_, i) => MONTHS[(lm - (vals.length - 1 - i) + 24) % 12]),
      });
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  function sample() {
    setUnits(SAMPLE.units); setLast(SAMPLE.last); setAc(SAMPLE.ac);
    submit(null, SAMPLE);
  }

  const setOne = (i, v) => setUnits(units.map((u, j) => (j === i ? v : u)));

  return (
    <>
      <div className="page-intro">
        <h2>Your electricity bill</h2>
        <p>Enter the units from your recent MSEDCL bills. You'll see where your money goes slab by slab, your carbon footprint, and what a year looks like for homes like yours.</p>
      </div>
      <div className="grid-main">
        <form className="card sticky" onSubmit={submit}>
          <h3>Your bills</h3>
          <div className="sub">Units (kWh) are printed on the bill. Oldest first, newest last.</div>
          <div className="field">
            <label htmlFor="lastm">Month of your latest bill</label>
            <select id="lastm" className="input" value={last} onChange={(e) => setLast(Number(e.target.value))}>
              {MONTHS_LONG.map((m, i) => <option key={m} value={i}>{m}</option>)}
            </select>
          </div>
          <div className="field">
            <span className="label">Units used (from your last 1 to 12 electricity bills)</span>
            <div className="units-grid">
              {units.map((u, i) => (
                <div className="cell" key={i}>
                  <span>{monthOf(i)}</span>
                  <input className="input" inputMode="decimal" aria-label={`Units for ${monthOf(i)}`} value={u}
                    onChange={(e) => setOne(i, e.target.value)} placeholder="–" />
                </div>
              ))}
            </div>
            <div className="btns" style={{ marginTop: 8 }}>
              {n < 12 && <button type="button" className="btn small ghost" onClick={() => setUnits(["", ...units])}>+ older month</button>}
              {n > 1 && <button type="button" className="btn small ghost" onClick={() => setUnits(units.slice(1))}>− remove oldest</button>}
            </div>
          </div>
          <div className="field">
            <span className="label">Do you have an AC?</span>
            <Seg label="AC" value={ac} onChange={setAc} options={[[true, "Yes"], [false, "No"]]} />
          </div>
          <div className="field">
            <label className="check"><input type="checkbox" checked={sm} onChange={(e) => setSm(e.target.checked)} />
              <span>I have a smart / time-of-day meter <span className="hint" style={{ display: "block", marginTop: 0 }}>MSEDCL gives these homes ₹0.80 off per unit used 9am–5pm.</span></span></label>
          </div>
          <ErrorBox error={err} />
          <div className="btns" style={{ marginTop: 12 }}>
            <button className="btn primary" disabled={busy}>{busy && <Spin />}Calculate</button>
            <button type="button" className="btn" onClick={sample} disabled={busy}>Try a sample home</button>
          </div>
        </form>

        <div className="stack">
          {!res && <Empty title="Your results will appear here">Fill in at least one bill, or try the sample home.</Empty>}
          {res && <BillResults r={res} />}
        </div>
      </div>
    </>
  );
}

function BillResults({ r }) {
  const b = r.bill.last_month;
  const avg = r.bill.history.reduce((s, h) => s + h.units, 0) / r.bill.history.length;
  return (
    <>
      <div className="stats">
        <Stat k={`Latest bill (${r.months[r.months.length - 1]})`} v={rs(b.bill.estimated_bill_rs)} n={`${num(b.units)} units`} tone="accent" />
        <Stat k="Your slab" v={`${r.bill.slab_status.slab}`} n={`Each unit you cut saves ${rs2(r.bill.slab_status.each_unit_cut_saves_rs)}`} tone="amber" />
        <Stat k="Carbon footprint" v={`${num(b.carbon.kg_co2)} kg`} n="CO₂ from that bill's electricity" />
        {r.bill.history.length > 1 && <Stat k={`Average of ${r.bill.history.length} bills`} v={`${num(avg)} units`} n={rs(r.bill.history.reduce((s, h) => s + h.bill_rs, 0) / r.bill.history.length) + " a month"} />}
      </div>

      <div className="row2">
        <Card title="Where the money goes" sub="Telescopic slabs: each rate applies only to the units inside that slab.">
          <SlabTable breakdown={b.bill.breakdown} />
        </Card>
        {r.bill.history.length > 1 ? (
          <Card title="Your bills" sub="Units per month">
            <BillHistoryChart history={r.bill.history} months={r.months} />
          </Card>
        ) : (
          <Card title="Why your slab matters" sub="">
            <p className="muted">You're in the <b>{r.bill.slab_status.slab}</b> slab, so every unit you save is worth <b>{rs2(r.bill.slab_status.each_unit_cut_saves_rs)}</b> including the wheeling charge.
              {b.bill.units_to_next_slab_line > 0 && b.bill.units_to_next_slab_line < 40 && <> You're only <b>{num(b.bill.units_to_next_slab_line)} units</b> away from the next, pricier slab.</>}</p>
          </Card>
        )}
      </div>

      <SavingsLine s={b.expected_savings_if_tips_followed} />

      {r.like ? <LikeYours like={r.like} /> : r.likeErr && <Notice kind="warn"><span>ℹ</span><span>"Homes like yours" isn't available right now: {r.likeErr}</span></Notice>}

      <Card title="Want a forecast from your own readings?" sub="">
        <p className="muted">A monthly bill is too coarse for an honest forecast. Note your meter reading every day for a week and WattWise's machine-learning model will forecast your next day, week and month, with a personal tip.</p>
        <div className="btns" style={{ marginTop: 10 }}>
          <a className="btn primary" href="#daily" style={{ textDecoration: "none" }}>Daily forecast →</a>
        </div>
      </Card>
    </>
  );
}

function LikeYours({ like }) {
  const y = like.year_summary;
  const d = like.typical_day;
  const p = like.typical_day_peak_month;
  return (
    <Card title={<>Homes like yours <span className="badge-sim">simulated</span></>}
      sub={`We matched your bills to the ${like.matched.homes} closest simulated Pune homes${like.matched.with_ac === true ? " with an AC" : like.matched.with_ac === false ? " without an AC" : ""}.`}>
      <Notice kind="sim"><span>◇</span><span>{like.data_label}</span></Notice>
      {like.inputs_defaulted.filter((x) => x.startsWith("warning")).map((w) => (
        <div key={w} style={{ marginTop: 10 }}><Notice kind="warn"><span>⚠</span><span>{w.replace("warning: ", "")}</span></Notice></div>
      ))}
      <div className="stats" style={{ margin: "16px 0" }}>
        <Stat k="A year for a home like yours" v={`${num(y.units)} units`} n={`about ${rs(y.bill_rs)}`} />
        <Stat k="Highest month" v={y.highest_month} n={`${num(y.highest_month_units)} units · slab ${y.highest_month_slab}`} tone="amber" />
        <Stat k="Yearly carbon" v={`${num(y.kg_co2 / 1000, 2)} t`} n="CO₂ (about 0.73 kg per unit)" />
      </div>
      <h3 style={{ fontSize: "1rem", marginTop: 4 }}>Month by month</h3>
      <YearChart year={like.year_outlook} />
      {d && (
        <>
          <h3 style={{ fontSize: "1rem", marginTop: 18 }}>A typical day</h3>
          <p className="muted" style={{ fontSize: "0.86rem", marginBottom: 6 }}>
            In {d.month}, homes like yours use the most around <b>{hourLabel(d.peak_hour)}</b> (~{num(d.peak_watts)} W).
            Overnight (1–5am) they still draw ~{num(d.night_watts_1_to_5am)} W{p && p.month !== d.month && <>; in {p.month} the peak is ~{num(p.peak_watts)} W around {hourLabel(p.peak_hour)}</>}.
          </p>
          <DayChart a={d} b={p} />
        </>
      )}
      <p className="small-print" style={{ marginTop: 10 }}>{like.how_good_is_this}</p>
    </Card>
  );
}
