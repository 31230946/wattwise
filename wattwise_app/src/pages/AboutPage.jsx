export default function AboutPage() {
  return (
    <div className="prose">
      <div className="page-intro">
        <h2>How WattWise works</h2>
        <p>What's real, what's estimated, and where every number comes from.</p>
      </div>

      <section className="card">
        <h3>The two screens</h3>
        <ul>
          <li><b>Your bill</b> works out your MSEDCL bill slab by slab, its carbon footprint, and what each unit you save is worth. No machine learning; it's exact maths on the official tariff.</li>
          <li><b>Daily forecast</b> (7–28 days of readings) predicts tomorrow, the next 7 days and the next 30 days.</li>
        </ul>
        <p>Every forecast comes with a <b>likely range</b>, the bill it leads to, its carbon footprint and <b>one tip</b> with the rupees and CO₂ it saves.</p>

        <h3>The machine learning</h3>
        <ul>
          <li>The forecasts use <b>XGBoost</b> (plus an <b>LSTM</b> neural network for tomorrow). They predict how your use will <i>change</i> from your own recent average, so they work for small and large homes alike.</li>
          <li>They were trained on <b>148 real homes</b> with half-hourly smart meters (Low Carbon London, 2013). We tested them only on homes they had never seen: about 19% average error for tomorrow and 13–14% for the next 7 or 30 days, a little better than simply repeating your recent average.</li>
          <li>The tip is chosen by a <b>contextual bandit (LinUCB)</b> that looks at your usage compared with similar homes, how much you use in the evening, and your always-on load.</li>
        </ul>

        <h3>Homes like yours (simulated)</h3>
        <p>No open daily dataset of Indian homes was available, so we built <b>simulated Pune homes</b>: real London homes kept as they behave day to day, but reshaped to match published smart-meter averages for Pune (Prayas Energy Group): typical usage, daily pattern and the AC summer. "Homes like yours" matches your bills to the closest of these. It shows a typical picture, not a forecast from your own data, and it's always labelled.</p>

        <h3>Please keep in mind</h3>
        <ul>
          <li>The forecast models learned from London homes; Indian homes may behave differently. Near the end of the AC season (June) the 30-day forecast is weakest.</li>
          <li>Bills include energy, wheeling and fixed charges (MSEDCL FY 2026-27) but <b>not</b> electricity duty or the fuel adjustment charge.</li>
          <li>Carbon uses one yearly average for the Indian grid: 0.727 kg CO₂ per unit (CEA, 2023-24).</li>
          <li>"Homes that follow tips use 4–7% less" comes from other studies, not from WattWise users.</li>
          <li>The appliance split (under “Advanced”) is an estimate from what you enter: typical energy use, or the BEE star-label figure for ACs, fridges and fans, × your hours, scaled to your meter. It is not a measurement.</li>
        </ul>

        <h3>Sources</h3>
        <ul className="small-print">
          <li>MSEDCL tariff: MERC Multi-Year Tariff Order press note, March 2025 (Annexure 3; time-of-day rebate in Section 12).</li>
          <li>Carbon factor: Central Electricity Authority, CO₂ Baseline Database, User Guide v20.0.</li>
          <li>Training data: Low Carbon London smart meter data (UK Power Networks, CC-BY; refactored by TU Delft).</li>
          <li>Pune averages for the simulated homes: Prayas (Energy Group), "Insights from smart metering data".</li>
          <li>Savings range: Nguyen et al., Energy Policy 195 (2024); Malaviya & Chandiwala, WRI (2018); Allcott, J. Public Economics (2011).</li>
        </ul>
      </section>
    </div>
  );
}
