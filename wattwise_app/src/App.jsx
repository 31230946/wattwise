import { useEffect, useState } from "react";
import { api } from "./api.js";
import BillPage from "./pages/BillPage.jsx";
import ForecastPage from "./pages/ForecastPage.jsx";
import AboutPage from "./pages/AboutPage.jsx";

const PAGES = [
  ["bill", "Your bill"],
  ["daily", "Daily forecast", "ML"],
  ["how", "How it works"],
];
const pageFromHash = () => {
  const h = window.location.hash.replace("#", "");
  return PAGES.some(([k]) => k === h) ? h : "bill";
};

export default function App() {
  const [page, setPage] = useState(pageFromHash());
  const [online, setOnline] = useState(null);
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    const on = () => { setPage(pageFromHash()); window.scrollTo({ top: 0 }); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  useEffect(() => {
    let stop = false;
    const check = () => api.health().then(() => !stop && setOnline(true)).catch(() => !stop && setOnline(false));
    check();
    const t = setInterval(check, 15000);
    api.meta().then(setMeta).catch(() => {});
    return () => { stop = true; clearInterval(t); };
  }, []);

  useEffect(() => { if (online && !meta) api.meta().then(setMeta).catch(() => {}); }, [online, meta]);

  return (
    <div className="wrap">
      <header className="header">
        <a className="brand" href="#bill" style={{ textDecoration: "none" }}>
          <img src="/favicon.svg" alt="" width="42" height="42" />
          <div>
            <h1>WattWise</h1>
            <span>Bills · forecasts · carbon for Maharashtra homes</span>
          </div>
        </a>
        <span className="status" title="Connection to the WattWise model service">
          <span className={`dot ${online === true ? "on" : online === false ? "off" : ""}`} />
          {online === null ? "Connecting…" : online ? "Model online" : "Model offline"}
        </span>
      </header>

      {online === false && (
        <div className="notice err" style={{ marginBottom: 16 }}>
          <span>⚠</span>
          <span><b>The WattWise model service isn't running.</b> Start it (see LAUNCH.md, step "Start everything") and this page will reconnect by itself.</span>
        </div>
      )}

      <nav className="tabs" aria-label="Sections">
        {PAGES.map(([k, label, tag]) => (
          <a key={k} href={`#${k}`} className={`tab ${page === k ? "active" : ""}`} style={{ textDecoration: "none" }}
            aria-current={page === k ? "page" : undefined}>{label}{tag && <small>{tag}</small>}</a>
        ))}
      </nav>

      {/* All pages stay mounted so your inputs and results survive switching tabs. */}
      <main>
        <div hidden={page !== "bill"}><BillPage /></div>
        <div hidden={page !== "daily"}><ForecastPage meta={meta} /></div>
        <div hidden={page !== "how"}><AboutPage /></div>
      </main>

      <footer className="footer">
        <span>WattWise · B.Tech Computer Engineering major project, Vishwakarma University, Pune (2026-27)</span>
        <span>Bills exclude electricity duty and FAC · Carbon: CEA 0.727 kg CO₂/kWh</span>
      </footer>
    </div>
  );
}
