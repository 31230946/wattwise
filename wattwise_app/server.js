// WattWise backend (Node + Express): serves the built React site (dist/) and forwards
// five /api/... routes to the Python ML service. The browser only talks to this server.
// Settings: PORT (default 5050), ML_URL (default http://localhost:8000).

import express from "express";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 5050);
const ML_URL = (process.env.ML_URL || "http://localhost:8000").replace(/\/$/, "");
const DIST = path.join(__dirname, "dist");

const app = express();
app.use(express.json({ limit: "100kb" }));

// The only ML routes the website may call (keeps the ML service from being exposed as-is).
const ROUTES = {
  "GET /api/health": "/health",
  "GET /api/meta": "/meta",
  "POST /api/bill": "/bill",
  "POST /api/forecast/daily": "/forecast/daily",
  "POST /api/homes-like-yours": "/homes-like-yours",
};

for (const [key, target] of Object.entries(ROUTES)) {
  const [method, route] = key.split(" ");
  app[method.toLowerCase()](route, async (req, res) => {
    try {
      const r = await fetch(ML_URL + target, {
        method,
        headers: { "Content-Type": "application/json" },
        body: method === "POST" ? JSON.stringify(req.body ?? {}) : undefined,
        signal: AbortSignal.timeout(60000),
      });
      const text = await r.text();
      res.status(r.status).type("application/json").send(text);
    } catch (e) {
      res.status(503).json({
        detail: `The WattWise ML service is not reachable at ${ML_URL}. Start it with: python -m uvicorn api:app --port 8000`,
      });
    }
  });
}

app.all("/api/*", (req, res) => res.status(404).json({ detail: "Unknown API route" }));

if (fs.existsSync(DIST)) {
  app.use(express.static(DIST));
  app.get("*", (req, res) => res.sendFile(path.join(DIST, "index.html")));
} else {
  app.get("*", (req, res) =>
    res.status(500).send("The website is not built yet. Run: npm run build, then npm start."));
}

app.listen(PORT, () => {
  console.log(`WattWise website: http://localhost:${PORT}`);
  console.log(`Talking to the ML service at ${ML_URL}`);
});
