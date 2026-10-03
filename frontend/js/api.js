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
