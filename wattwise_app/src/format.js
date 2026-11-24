const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const rs = (x) => (x == null ? "–" : `₹${inr.format(Math.round(x))}`);
export const rs2 = (x) => (x == null ? "–" : `₹${inr2.format(x)}`);
export const num = (x, d = 0) => (x == null ? "–" : Number(x).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }));
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// "9.1, 8.7 10.2\n9.8" -> [9.1, 8.7, 10.2, 9.8]
export function parseNumbers(text) {
  const parts = String(text).split(/[\s,;]+/).filter(Boolean);
  const nums = parts.map(Number);
  const bad = parts.filter((p, i) => !Number.isFinite(nums[i]));
  return { nums, bad };
}

export const hourLabel = (h) => (h === 0 ? "12am" : h < 12 ? `${h}am` : h === 12 ? "12pm" : `${h - 12}pm`);

export function lastMonthIndex() {
  const d = new Date();
  return (d.getMonth() + 11) % 12; // 0-based index of last calendar month
}

export function isoDate(d) {
  const z = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}
