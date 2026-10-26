const API = "http://localhost:8000";

async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

function qs(id) { return document.getElementById(id); }
function val(id) { return qs(id).value; }

function setStatus(id, msg, isError = false) {
  const el = qs(id);
  el.textContent = msg;
  el.className = "status" + (isError ? " error" : "");
}

/**
 * Shows a loading state on a button for the duration of a slow
 * operation: disables it, swaps its label to a spinner + loadingText,
 * and restores the original label and enabled state afterward -- even
 * if the operation throws. Use for anything that takes a moment
 * (planning runs, multi-request comparisons, batch loads).
 *
 * Usage:
 *   const done = setLoading("btnRunPlanning", "Ejecutando");
 *   try { ... } finally { done(); }
 */
function setLoading(buttonId, loadingText = "Cargando") {
  const btn = qs(buttonId);
  if (!btn) return () => {};
  // Already loading (a second request started before the first finished): leave it to the
  // first caller to restore the button, so the spinner text is never saved as the "original" label.
  if (btn.classList.contains("btn-loading")) return () => {};

  const originalText = btn.textContent;
  const originalDisabled = btn.disabled;

  btn.disabled = true;
  btn.classList.add("btn-loading");
  btn.innerHTML = `<span class="spinner"></span> ${loadingText}…`;

  return function restore() {
    btn.disabled = originalDisabled;
    btn.classList.remove("btn-loading");
    btn.textContent = originalText;
  };
}

async function populateTeamDropdown(selectId, allLabel = null) {
  const teams = await api("/teams");
  const sel = qs(selectId);
  sel.innerHTML = "";
  if (allLabel) {
    const all = document.createElement("option");
    all.value = "";
    all.textContent = allLabel;
    sel.appendChild(all);
  }
  teams.forEach(t => {
    const o = document.createElement("option");
    o.value = t.id;
    o.textContent = `${t.name} (#${t.id})`;
    sel.appendChild(o);
  });
}

async function populateOrderDropdown(selectId) {
  const orders = await api("/orders");
  const sel = qs(selectId);
  sel.innerHTML = "";
  orders.forEach(o => {
    const opt = document.createElement("option");
    opt.value = o.id;
    opt.textContent = `#${o.id} — ${o.customer_name} (${o.quantity_requested})`;
    sel.appendChild(opt);
  });
}

/* ── Shared helpers: HTML escaping and ISO weeks ─────────────
   Use escapeHtml for any user text that goes into innerHTML.
   ISO weeks (Monday start; week 1 is the one holding January 4th) are what the
   backend stores in CapacityAllocation and TeamWeekException. Timestamps are
   UTC milliseconds, so the browser's time zone can never shift a date. */

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* UTC milliseconds of the Monday that starts ISO week `week` of `year`. */
function isoWeekMonday(year, week) {
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const dow = jan4.getUTCDay() || 7;
  return Date.UTC(year, 0, 4 - (dow - 1) + (week - 1) * 7);
}

/* ISO { year, week } of a UTC timestamp. */
function isoWeekOfMs(ms) {
  const d = new Date(ms);
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));   // the Thursday of that week
  const year = d.getUTCFullYear();
  return { year, week: Math.ceil(((d - Date.UTC(year, 0, 1)) / 86400000 + 1) / 7) };
}

/* 52 or 53: December 28th always falls in the last ISO week of its year. */
function isoWeeksInYear(year) {
  return isoWeekOfMs(Date.UTC(year, 11, 28)).week;
}

/* "7 sep" for a UTC timestamp, and "7 sep – 13 sep" for a whole ISO week. */
function shortDate(ms) {
  const d = new Date(ms);
  const months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  return `${d.getUTCDate()} ${months[d.getUTCMonth()]}`;
}

function weekRangeLabel(year, week) {
  const monday = isoWeekMonday(year, week);
  return `${shortDate(monday)} – ${shortDate(monday + 6 * 86400000)}`;
}
