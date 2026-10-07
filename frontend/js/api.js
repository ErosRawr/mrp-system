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

async function populateTeamDropdown(selectId) {
  const teams = await api("/teams");
  const sel = qs(selectId);
  sel.innerHTML = "";
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