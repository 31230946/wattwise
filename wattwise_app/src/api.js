// All calls go to the Node backend (/api/...), which forwards them to the Python ML service.
async function call(method, path, body) {
  let r;
  try {
    r = await fetch(`/api${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Can't reach the WattWise server. Is it running?");
  }
  let data = null;
  try { data = await r.json(); } catch { /* not JSON */ }
  if (!r.ok) throw new Error((data && data.detail) || `Something went wrong (${r.status}).`);
  return data;
}

export const api = {
  health: () => call("GET", "/health"),
  meta: () => call("GET", "/meta"),
  bill: (b) => call("POST", "/bill", b),
  likeYours: (b) => call("POST", "/homes-like-yours", b),
  daily: (b) => call("POST", "/forecast/daily", b),
};
