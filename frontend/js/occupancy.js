/* ── Ocupación ────────────────────────────────────────────────
   A heat map of team × week for one month. Click a week to see which orders fill it.
   Occupancy = tons already allocated that ISO week (any month's orders) ÷ the team's
   capacity that week (after holidays, maintenance and productivity drops). */

const OCC_FULL = 99.95;    // shows as 100%
const OCC_OVER = 100.05;   // genuinely above capacity

const occ = {
  model: null,                // { year, month, weeks, teams }
  selected: null,             // { teamId, key }
  orders: new Map(),          // order id -> order
  allocations: new Map(),     // team id -> its capacity allocations (loaded on demand)
  request: 0,                 // lets a slow response be ignored once a newer one started
};

const occTons = n => Math.round(Number(n)).toLocaleString("es-MX");
const occPad = n => String(n).padStart(2, "0");

/* How busy is it? `capacity` 0 means the team is closed that week. */
function occLevelOf(pct, capacity = 1) {
  if (capacity <= 0) return { cls: "closed", label: "Cerrada" };
  if (pct > OCC_OVER) return { cls: "over", label: "Excede la capacidad" };
  if (pct >= OCC_FULL) return { cls: "full", label: "Al límite" };
  if (pct >= 85) return { cls: "high", label: "Alta" };
  if (pct >= 50) return { cls: "ok", label: "Normal" };
  if (pct > 0) return { cls: "low", label: "Baja" };
  return { cls: "none", label: "Sin carga" };
}

/* ── Data ────────────────────────────────────────────────── */

function occBuildModel(year, month, responses) {
  const weeks = responses[0].weekly_breakdown.map(w => ({ year: w.year, week: w.week_number, key: `${w.year}-${w.week_number}` }));
  const teams = responses.map(r => {
    const cells = new Map();
    r.weekly_breakdown.forEach(w => {
      const cell = {
        teamId: r.team_id, teamName: r.team_name,
        year: w.year, week: w.week_number, key: `${w.year}-${w.week_number}`,
        allocated: w.allocated, capacity: w.capacity, multiplier: w.capacity_multiplier, reason: w.reason,
        pct: w.occupancy_pct ?? 0,
      };
      cell.level = occLevelOf(cell.pct, cell.capacity);
      cells.set(cell.key, cell);
    });
    return { id: r.team_id, name: r.team_name, overall: r.overall_occupancy_pct, cells };
  });
  return { year, month, weeks, teams };
}

async function occAllocations(teamId) {
  if (!occ.allocations.has(teamId)) occ.allocations.set(teamId, await api(`/teams/${teamId}/capacity-allocations`));
  return occ.allocations.get(teamId);
}

async function loadOccupancy() {
  const year = parseInt(val("occYear"), 10), month = parseInt(val("occMonth"), 10);
  if (!(year >= 1970 && year <= 2200)) { setStatus("occStatus", "El año debe estar entre 1970 y 2200.", true); return; }
  if (!(month >= 1 && month <= 12)) { setStatus("occStatus", "El mes debe estar entre 1 y 12.", true); return; }

  const ticket = ++occ.request;
  const done = setLoading("btnGetOccupancy", "Cargando");
  qs("occMap").classList.add("is-loading");
  try {
    setStatus("occStatus", "Cargando…");
    const [teams, orders] = await Promise.all([api("/teams"), api("/orders")]);
    if (!teams.length) {
      qs("occKpis").innerHTML = '<div class="occ-empty">Aún no hay equipos. Créalos en la pestaña Equipos.</div>';
      qs("occMap").innerHTML = ""; qs("occDetail").innerHTML = "";
      setStatus("occStatus", "");
      return;
    }
    const responses = await Promise.all(teams.map(t => api(`/teams/${t.id}/occupancy?year=${year}&month=${month}`)));
    if (ticket !== occ.request) return;                       // a newer request replaced this one

    occ.orders = new Map(orders.map(o => [o.id, o]));
    occ.allocations = new Map();                              // the plan may have changed since last time
    occ.model = occBuildModel(year, month, responses);
    occ.selected = null;
    renderOccupancy();
    setStatus("occStatus", "");
  } catch (e) {
    if (ticket === occ.request) setStatus("occStatus", e.message, true);
  } finally {
    done();
    if (ticket === occ.request) qs("occMap").classList.remove("is-loading");
  }
}

function occShiftMonth(delta) {
  let year = parseInt(val("occYear"), 10), month = parseInt(val("occMonth"), 10) + delta;
  if (month < 1) { month = 12; year -= 1; }
  if (month > 12) { month = 1; year += 1; }
  qs("occYear").value = year;
  qs("occMonth").value = month;
  loadOccupancy();
}

/* ── Rendering ───────────────────────────────────────────── */

function occCard(label, value, sub, tone = "") {
  return `<div class="kpi-card ${tone}"><div class="kpi-label">${label}</div>` +
         `<div class="kpi-value">${value}</div><div class="kpi-sub">${sub}</div></div>`;
}

function renderOccupancy() {
  const { teams, weeks, year, month } = occ.model;
  const cells = teams.flatMap(t => [...t.cells.values()]);
  const open = cells.filter(c => c.capacity > 0);
  const totalAllocated = cells.reduce((sum, c) => sum + c.allocated, 0);

  // Summary cards
  const avgs = teams.map(t => t.overall).filter(v => v !== null);
  const plantAvg = avgs.length ? avgs.reduce((a, b) => a + b, 0) / avgs.length : null;
  const busiest = [...teams].filter(t => t.overall !== null).sort((a, b) => b.overall - a.overall)[0];
  const peak = [...open].sort((a, b) => b.pct - a.pct)[0];
  const atLimit = open.filter(c => c.pct >= OCC_FULL).length;
  const over = open.filter(c => c.pct > OCC_OVER).length;
  const idle = totalAllocated === 0;
  const avgTone = { over: "danger", full: "danger", high: "warn" }[occLevelOf(plantAvg ?? 0).cls] || "";

  qs("occKpis").innerHTML = `<div class="kpi-grid occ-kpis">
    ${occCard("Ocupación promedio de planta", plantAvg === null ? "—" : plantAvg.toFixed(1) + "%", `${teams.length} equipos · ${weeks.length} semanas`, avgTone)}
    ${occCard("Cuello de botella", idle || !busiest ? "—" : escapeHtml(busiest.name), idle || !busiest ? "sin carga planeada" : `${busiest.overall.toFixed(1)}% de ocupación promedio`, idle ? "" : "warn")}
    ${occCard("Semana más cargada", idle || !peak ? "—" : Math.round(peak.pct) + "%", idle || !peak ? "sin carga planeada" : `${escapeHtml(peak.teamName)} · semana ${peak.week}`,
              idle || !peak ? "" : peak.pct > OCC_OVER ? "danger" : peak.pct >= 85 ? "warn" : "")}
    ${occCard("Semanas al límite", atLimit, over ? `${over} por encima de su capacidad` : `de ${open.length} semanas-equipo`, over ? "danger" : atLimit ? "warn" : "good")}
  </div>`;

  // Heat map
  const head = '<div></div>' + weeks.map(w =>
    `<div class="occ-map-week"><strong>S${w.week}</strong><span>${weekRangeLabel(w.year, w.week)}</span></div>`).join("") +
    '<div class="occ-map-week"><strong>Promedio</strong><span>del mes</span></div>';

  const rows = teams.map((team, i) => {
    const cellsHtml = weeks.map(w => occCellHtml(team.cells.get(w.key))).join("");
    const avgPct = team.overall;
    const lvl = occLevelOf(avgPct ?? 0, avgPct === null ? 0 : 1);
    return `<div class="occ-map-team"><span class="occ-map-step">${i + 1}</span>${escapeHtml(team.name)}</div>${cellsHtml}
      <div class="occ-map-avg lvl-${lvl.cls}" title="Ocupación promedio de ${escapeHtml(team.name)} en el mes">
        <span class="occ-avg-value">${avgPct === null ? "—" : avgPct.toFixed(1) + "%"}</span>
        <span class="occ-cell-bar"><span style="width:${Math.min(avgPct ?? 0, 100)}%"></span></span>
      </div>`;
  }).join("");

  const plantRow = (() => {
    const cellsHtml = weeks.map(w => {
      const open = teams.map(t => t.cells.get(w.key)).filter(c => c.capacity > 0);
      const pct = open.length ? open.reduce((sum, c) => sum + c.pct, 0) / open.length : null;
      const { cls } = occLevelOf(pct ?? 0, pct === null ? 0 : 1);
      return `<div class="occ-foot occ-foot-cell lvl-${cls}" title="Promedio de los equipos en la semana ${w.week}">
        <span class="occ-foot-pct">${pct === null ? "—" : Math.round(pct) + "%"}</span>
        ${pct ? `<span class="occ-cell-bar"><span style="width:${Math.min(pct, 100)}%"></span></span>` : ""}</div>`;
    }).join("");
    const { cls } = occLevelOf(plantAvg ?? 0, plantAvg === null ? 0 : 1);
    return `<div class="occ-foot occ-map-team occ-foot-label"><span class="occ-map-step"></span>Planta</div>${cellsHtml}
      <div class="occ-foot occ-map-avg lvl-${cls}"><span class="occ-avg-value">${plantAvg === null ? "—" : plantAvg.toFixed(1) + "%"}</span></div>`;
  })();

  const legend = [["none", "sin carga"], ["low", "< 50%"], ["ok", "50–85%"], ["high", "85–100%"], ["full", "al límite"], ["over", "excedida"], ["closed", "cerrada"]]
    .map(([cls, text]) => `<span><span class="occ-key lvl-${cls}"></span>${text}</span>`).join("");

  qs("occMap").innerHTML = `
    <div class="occ-card-head">
      <div class="occ-card-title">Ocupación por equipo y semana · ${year}-${occPad(month)}</div>
      <div class="occ-card-hint">Haz clic en una semana para ver qué pedidos la ocupan</div>
    </div>
    <div class="occ-map-scroll">
      <div class="occ-map" style="--occ-cols:${weeks.length}">${head}${rows}${plantRow}</div>
    </div>
    <div class="chart-legend occ-legend">${legend}</div>`;

  // Pick the busiest week so the detail panel is never empty when there is something to show
  if (idle) {
    qs("occDetail").innerHTML = `<div class="occ-empty">Este mes todavía no tiene carga asignada. Ejecuta la planeación del mes en la pestaña Planeación mensual para ver la ocupación.</div>`;
  } else if (peak) {
    occSelect(peak.teamId, peak.key);
  }
}

function occCellHtml(cell) {
  const { cls, label } = cell.level;
  const closed = cls === "closed";
  const reduced = cell.multiplier > 0 && cell.multiplier < 1;
  const detail = `${cell.teamName} · semana ${cell.week} · ${closed ? "cerrada" : cell.pct.toFixed(1) + "% (" + label.toLowerCase() + ")"} · ` +
                 `${occTons(cell.allocated)} de ${occTons(cell.capacity)} t` + (cell.reason ? ` · ${cell.reason}` : "");
  return `
    <button type="button" class="occ-cell lvl-${cls}" data-team="${cell.teamId}" data-week="${cell.key}" aria-pressed="false"
            aria-label="${escapeHtml(detail)}" title="${escapeHtml(detail)}">
      ${reduced ? `<span class="occ-cell-flag">cap. ${Math.round(cell.multiplier * 100)}%</span>` : ""}
      <span class="occ-cell-pct">${closed ? "Cerrada" : cls === "none" ? "—" : Math.round(cell.pct) + "%"}</span>
      ${cls === "none" || (closed && !cell.allocated) ? "" : `<span class="occ-cell-tons">${occTons(cell.allocated)} t</span>`}
      ${closed || cls === "none" ? "" : `<span class="occ-cell-bar"><span style="width:${Math.min(cell.pct, 100)}%"></span></span>`}
    </button>`;
}

/* ── Drill-down: which orders fill this team's week ─────── */

async function occSelect(teamId, key) {
  const team = occ.model.teams.find(t => t.id === teamId);
  const cell = team && team.cells.get(key);
  if (!cell) return;
  occ.selected = { teamId, key };
  document.querySelectorAll(".occ-cell").forEach(b =>
    b.setAttribute("aria-pressed", String(Number(b.dataset.team) === teamId && b.dataset.week === key)));

  qs("occDetail").innerHTML = occDetailHtml(cell, null);
  const allocations = await occAllocations(teamId);
  if (!occ.selected || occ.selected.teamId !== teamId || occ.selected.key !== key) return;   // the user moved on
  qs("occDetail").innerHTML = occDetailHtml(cell, allocations);
}

function occDetailHtml(cell, allocations) {
  const { cls, label } = cell.level;
  const closed = cls === "closed";
  const free = Math.max(cell.capacity - cell.allocated, 0);

  let capacityNote = "";
  if (cell.multiplier < 1) {
    capacityNote = `<div class="occ-stat-note">${closed ? "Equipo sin disponibilidad esta semana" : `Capacidad al ${Math.round(cell.multiplier * 100)}%`}${cell.reason ? " — " + escapeHtml(cell.reason) : ""}</div>`;
  }

  let ordersHtml = '<div class="occ-loading">Cargando pedidos…</div>';
  let orderCount = "—";
  if (allocations) {
    const byOrder = new Map();
    allocations.filter(a => a.year === cell.year && a.week_number === cell.week)
      .forEach(a => byOrder.set(a.order_id, (byOrder.get(a.order_id) || 0) + Number(a.quantity_allocated)));
    const list = [...byOrder].sort((a, b) => b[1] - a[1]);
    orderCount = list.length;
    ordersHtml = list.length ? list.map(([orderId, tons]) => {
      const order = occ.orders.get(orderId);
      const share = cell.capacity > 0 ? tons / cell.capacity * 100 : null;
      return `
        <div class="occ-order">
          <div class="occ-order-name">
            <span>#${orderId} ${order ? escapeHtml(order.customer_name) : "(pedido eliminado)"}</span>
            ${order ? `<span class="occ-order-month">planeación ${order.planning_year}-${occPad(order.planning_month)}</span>` : ""}
          </div>
          <div class="occ-order-bar"><span style="width:${Math.min(share ?? 0, 100)}%"></span></div>
          <div class="occ-order-tons">${occTons(tons)} t</div>
          <div class="occ-order-share">${share === null ? "—" : share.toFixed(1) + "%"}</div>
        </div>`;
    }).join("") : '<div class="occ-loading">Ningún pedido tiene carga asignada en esta semana.</div>';
  }

  const alert = cls === "over" ? `
    <div class="occ-alert">Esta semana tiene más trabajo asignado (${occTons(cell.allocated)} t) del que permite su capacidad (${occTons(cell.capacity)} t).
      Suele pasar al cambiar la disponibilidad después de planear: vuelve a ejecutar la planeación del mes.</div>` : "";

  return `
    <section class="occ-card occ-detail lvl-${cls}">
      <div class="occ-detail-head">
        <div>
          <div class="occ-detail-title">${escapeHtml(cell.teamName)} · semana ${cell.week}</div>
          <div class="occ-detail-sub">${weekRangeLabel(cell.year, cell.week)} ${cell.year}</div>
        </div>
        <span class="occ-pill">${closed ? label : `${label} · ${cell.pct.toFixed(1)}%`}</span>
      </div>
      ${alert}
      <div class="occ-stats">
        <div class="occ-stat"><span>Asignado</span><strong>${occTons(cell.allocated)} t</strong></div>
        <div class="occ-stat"><span>Capacidad de la semana</span><strong>${occTons(cell.capacity)} t</strong>${capacityNote}</div>
        <div class="occ-stat"><span>Libre</span><strong>${occTons(free)} t</strong></div>
        <div class="occ-stat"><span>Pedidos</span><strong>${orderCount}</strong></div>
      </div>
      <div class="occ-orders">${ordersHtml}</div>
    </section>`;
}

/* ── Wiring ──────────────────────────────────────────────── */

qs("btnGetOccupancy").addEventListener("click", loadOccupancy);
qs("btnOccPrev").addEventListener("click", () => occShiftMonth(-1));
qs("btnOccNext").addEventListener("click", () => occShiftMonth(1));
["occYear", "occMonth"].forEach(id => qs(id).addEventListener("change", loadOccupancy));
qs("occMap").addEventListener("click", e => {
  const button = e.target.closest(".occ-cell");
  if (button) occSelect(Number(button.dataset.team), button.dataset.week);
});
