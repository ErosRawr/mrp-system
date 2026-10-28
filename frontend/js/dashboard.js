/* ── Dashboard ────────────────────────────────────────────────
   Five indicators and four charts for one month. Every number comes from a single
   request, GET /dashboard: nothing is calculated here that the backend decides
   (lateness, occupancy and material totals all match the other tabs). */

const DASH_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                     "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const DASH_MONTHS_SHORT = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const dash = { data: null, opened: false, request: 0 };

const dashN = (n, digits = 0) => Number(n).toLocaleString("es-MX", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const dashCap = text => text.charAt(0).toUpperCase() + text.slice(1);
const dashMonth = m => DASH_MONTHS[m - 1];
const dashIsoToMs = iso => Date.parse(iso + "T00:00:00Z");
const dashPlural = (n, one, many) => `${dashN(n)} ${n === 1 ? one : many}`;

/* ── Loading ─────────────────────────────────────────────── */

async function loadDashboard() {
  const ticket = ++dash.request;
  const done = setLoading("btnLoadDashboard", "Actualizando");
  try {
    // The first time the page opens, let the backend pick the month (the latest planned one).
    let query = "";
    if (dash.opened) {
      const year = parseInt(val("dashYear"), 10), month = parseInt(val("dashMonth"), 10);
      if (!(year >= 1970 && year <= 2200)) { setStatus("dashStatus", "El año debe estar entre 1970 y 2200.", true); return; }
      if (!(month >= 1 && month <= 12)) { setStatus("dashStatus", "El mes debe estar entre 1 y 12.", true); return; }
      query = `?year=${year}&month=${month}`;
    }
    setStatus("dashStatus", "Cargando…");
    const data = await api("/dashboard" + query);
    if (ticket !== dash.request) return;                 // a newer request replaced this one
    dash.data = data;
    dash.opened = true;
    qs("dashYear").value = data.year;
    qs("dashMonth").value = data.month;
    renderDashboard(data);
    setStatus("dashStatus", "");
  } catch (e) {
    if (ticket === dash.request) setStatus("dashStatus", e.message, true);
  } finally { done(); }
}

function dashSelectMonth(month) {
  qs("dashMonth").value = month;
  loadDashboard();
}

function dashShiftMonth(delta) {
  let year = parseInt(val("dashYear"), 10), month = parseInt(val("dashMonth"), 10) + delta;
  if (month < 1) { month = 12; year -= 1; }
  if (month > 12) { month = 1; year += 1; }
  qs("dashYear").value = year;
  qs("dashMonth").value = month;
  loadDashboard();
}

/* ── Rendering ───────────────────────────────────────────── */

function renderDashboard(data) {
  const name = dashMonth(data.month), previous = dashMonth(data.previous.month);
  qs("dashKpiTitle").textContent = `Indicadores de ${name} de ${data.year}`;
  qs("dashKpiSub").textContent = `Con la variación frente a ${previous}.`;
  renderDashNote(data);
  renderDashKpis(data);
  renderDashDelivery(data);
  renderDashLoad(data);
  renderDashTrend(data);
  renderDashAttention(data);
}

function renderDashNote(data) {
  const name = dashMonth(data.month), orders = data.kpis.orders;
  let text = "";
  if (orders.total === 0) text = `No hay pedidos con periodo de planeación en ${name} de ${data.year}.`;
  else if (!data.is_planned) text = `${dashCap(name)} todavía no está planeado: los indicadores de entrega aparecerán cuando guardes un plan en Planeación mensual. La ocupación que ves viene de semanas compartidas con meses vecinos.`;
  qs("dashNote").innerHTML = text ? `<div class="dash-note" role="note">${text}</div>` : "";
}

/* Month-over-month change. `better` says which direction is good news ("neutral": just information). */
function dashDelta(now, before, previousName, { kind = "points", better = "up" } = {}) {
  const none = `<div class="kpi-delta flat">sin dato de ${previousName}</div>`;
  if (now === null || now === undefined || before === null || before === undefined) return none;
  let diff = now - before;
  if (kind === "percent") { if (before === 0) return none; diff = diff / before * 100; }
  if (Math.abs(diff) < 0.05) return `<div class="kpi-delta flat">igual que ${previousName}</div>`;

  const up = diff > 0;
  const tone = better === "neutral" ? "flat" : (up === (better === "up") ? "good" : "bad");
  const amount = kind === "count" ? dashN(Math.abs(diff)) : dashN(Math.abs(diff), 1);
  const unit = kind === "percent" ? "%" : kind === "points" ? " pts" : "";
  return `<div class="kpi-delta ${tone}" aria-label="${up ? "sube" : "baja"} ${amount}${unit} frente a ${previousName}">` +
         `<span aria-hidden="true">${up ? "▲" : "▼"}</span> ${amount}${unit} vs ${previousName}</div>`;
}

function dashCard({ label, hint, value, sub, delta = "", tone = "" }) {
  return `<article class="kpi-card ${tone}" title="${escapeHtml(hint)}">
    <div class="kpi-label">${label}</div>
    <div class="kpi-value">${value}</div>
    <div class="kpi-sub">${sub}</div>
    ${delta}
  </article>`;
}

function renderDashKpis(data) {
  const k = data.kpis, previous = dashMonth(data.previous.month);
  const onTime = k.on_time, tons = k.tons, occupancy = k.occupancy;
  const bottleneckTeam = k.bottleneck && data.teams.find(t => t.team_name === k.bottleneck.team_name);
  const bottleneckPeak = bottleneckTeam && bottleneckTeam.peak_week;

  const complianceTone = onTime.pct === null ? "" : onTime.pct >= 90 ? "good" : onTime.pct >= 75 ? "warn" : "danger";
  const loadTone = pct => pct === null || pct === undefined ? "" : pct > 100.05 ? "danger" : pct >= 85 ? "warn" : "";

  qs("kpiGrid").innerHTML = [
    dashCard({
      label: "Pedidos del mes", hint: "Pedidos que pertenecen al periodo de planeación seleccionado.",
      value: dashN(k.orders.total),
      sub: `${dashN(k.orders.scheduled)} planeados · ${dashN(k.orders.unplanned)} sin planear`,
      delta: dashDelta(k.orders.total, k.orders.previous_total, previous, { kind: "count", better: "neutral" }),
      tone: k.orders.total > 0 && k.orders.unplanned > 0 ? "warn" : "",
    }),
    dashCard({
      label: "Entregas a tiempo", hint: "Cumplimiento de entrega: de los pedidos planeados, cuántos se entregan a tiempo.",
      value: onTime.pct === null ? "—" : `${dashN(onTime.pct)}%`,
      sub: onTime.evaluated ? `${dashN(onTime.on_time)} de ${dashN(onTime.evaluated)} a tiempo${onTime.critical ? ` · ${dashN(onTime.critical)} críticos` : ""}` : "sin pedidos planeados",
      delta: dashDelta(onTime.pct, onTime.previous_pct, previous, { better: "up" }),
      tone: complianceTone,
    }),
    dashCard({
      label: "Ocupación de planta", hint: "Promedio de la ocupación de todos los equipos en las semanas del mes.",
      value: occupancy.pct === null ? "—" : `${dashN(occupancy.pct, 1)}%`,
      sub: "promedio de los equipos",
      delta: dashDelta(occupancy.pct, occupancy.previous_pct, previous, { better: "neutral" }),
      tone: loadTone(occupancy.pct),
    }),
    dashCard({
      label: "Cuello de botella", hint: "El equipo con mayor ocupación en las semanas del mes.",
      value: k.bottleneck ? escapeHtml(k.bottleneck.team_name) : "—",
      sub: k.bottleneck ? `${dashN(k.bottleneck.pct, 1)}% de ocupación` : "sin carga en las semanas del mes",
      delta: bottleneckPeak ? `<div class="kpi-delta flat">semana más cargada: S${bottleneckPeak.week} (${dashN(bottleneckPeak.pct)}%)</div>` : "",
      tone: k.bottleneck ? loadTone(k.bottleneck.pct) : "",
    }),
    dashCard({
      label: "Tonelaje pedido", hint: "Toneladas de producto terminado pedidas, y la materia prima que requieren.",
      value: `${dashN(tons.ordered)} t`,
      sub: tons.raw ? `${dashN(tons.raw)} t de materia prima · ${dashN(tons.overall_yield * 100, 1)}% rendimiento` : "sin pedidos",
      delta: dashDelta(tons.ordered, tons.previous_ordered, previous, { kind: "percent", better: "neutral" }),
    }),
  ].join("");
}

/* ── Chart 1: deliveries, twelve months ──────────────────── */

function renderDashDelivery(data) {
  const MAX_PX = 150;
  const max = Math.max(1, ...data.months.map(m => m.orders));
  const px = n => n ? Math.max(2, Math.round(n / max * MAX_PX)) : 0;

  qs("dashDelivery").innerHTML = `
    <div class="dash-cols" role="group" aria-label="Pedidos por mes">
      ${data.months.map(m => {
        const other = m.orders - m.on_time - m.warning - m.critical - m.unplanned;   // planned, but no requested date to judge by
        const segs = [["on_time", m.on_time], ["warning", m.warning], ["critical", m.critical], ["unplanned", m.unplanned], ["other", other]]
          .filter(([, n]) => n > 0).map(([cls, n]) => `<span class="dash-seg ${cls}" style="height:${px(n)}px"></span>`).join("");
        const detail = `${dashCap(dashMonth(m.month))}: ${dashPlural(m.orders, "pedido", "pedidos")} · ${m.on_time} a tiempo · ${m.warning} atrasados · ${m.critical} críticos · ${m.unplanned} sin planear`;
        return `<button type="button" class="dash-col${m.month === data.month ? " selected" : ""}" data-month="${m.month}"
                        title="${escapeHtml(detail)}" aria-label="${escapeHtml(detail)}" aria-pressed="${m.month === data.month}">
          <span class="dash-col-total">${m.orders || ""}</span>
          <span class="dash-col-stack">${segs}</span>
          <span class="dash-col-label">${DASH_MONTHS_SHORT[m.month - 1]}</span>
        </button>`;
      }).join("")}
    </div>
    <div class="chart-legend dash-legend">
      <span><span class="dash-key on_time"></span>a tiempo</span>
      <span><span class="dash-key warning"></span>atrasado</span>
      <span><span class="dash-key critical"></span>crítico</span>
      <span><span class="dash-key unplanned"></span>sin planear</span>
    </div>`;

  const cur = data.months[data.month - 1], name = dashCap(dashMonth(data.month));
  let sub;
  if (!cur.orders) sub = `${name}: sin pedidos.`;
  else if (data.kpis.on_time.evaluated) {
    sub = `${name}: ${cur.on_time} a tiempo, ${cur.warning} atrasados, ${cur.critical} críticos` + (cur.unplanned ? `, ${cur.unplanned} sin planear.` : ".");
  } else sub = `${name}: ${dashPlural(cur.unplanned, "pedido", "pedidos")} sin planear.`;
  qs("dashDeliverySub").textContent = sub;
}

/* ── Chart 2: load per team, selected month ──────────────── */

function dashLevel(pct) {
  if (pct === null || pct === undefined || pct <= 0) return "none";
  if (pct > 100.05) return "over";
  if (pct >= 99.95) return "full";
  if (pct >= 85) return "high";
  if (pct >= 50) return "ok";
  return "low";
}

function renderDashLoad(data) {
  const teams = data.teams;
  if (!teams.length) {
    qs("dashLoad").innerHTML = '<div class="dash-empty">Aún no hay equipos. Créalos en la pestaña Equipos.</div>';
    qs("dashLoadSub").textContent = "";
    return;
  }
  const top = Math.max(100, ...teams.map(t => t.occupancy_pct ?? 0));
  const limit = 100 / top * 100;

  qs("dashLoad").innerHTML = `
    <div class="dash-bars">
      ${teams.map(t => {
        const pct = t.occupancy_pct;
        const peak = t.peak_week ? `pico S${t.peak_week.week} · ${dashN(t.peak_week.pct)}%` : "sin carga";
        return `<div class="dash-bar-row" title="${escapeHtml(`${t.team_name}: ${dashN(t.allocated)} t asignadas de ${dashN(t.capacity)} t de capacidad`)}">
          <div class="dash-bar-name"><strong>${escapeHtml(t.team_name)}</strong><small>${peak}</small></div>
          <div class="dash-bar-track">
            <span class="dash-bar-fill lvl-${dashLevel(pct)}" style="width:${Math.min((pct ?? 0) / top * 100, 100)}%"></span>
            <span class="dash-bar-limit" style="left:${limit}%"></span>
          </div>
          <div class="dash-bar-value">${pct === null ? "—" : dashN(pct, 1) + "%"}</div>
        </div>`;
      }).join("")}
    </div>
    <div class="chart-legend dash-legend">
      <span><span class="dash-key-line"></span>100% = capacidad de la semana</span>
      <span><span class="dash-key lvl-low"></span>baja</span>
      <span><span class="dash-key lvl-ok"></span>normal</span>
      <span><span class="dash-key lvl-high"></span>alta</span>
      <span><span class="dash-key lvl-over"></span>excedida</span>
    </div>`;

  const b = data.kpis.bottleneck, name = dashMonth(data.month);
  qs("dashLoadSub").textContent = b
    ? `${b.team_name} es el cuello de botella en ${name}, con ${dashN(b.pct, 1)}% de ocupación.`
    : `Ningún equipo tiene carga asignada en las semanas de ${name}.`;
}

/* ── Chart 3: plant occupancy over the year ──────────────── */

function renderDashTrend(data) {
  const values = data.months.map(m => m.occupancy_pct);
  const known = values.filter(v => v !== null);
  if (!known.length) {
    qs("dashTrend").innerHTML = '<div class="dash-empty">Todavía no hay carga planeada en este año.</div>';
    qs("dashTrendSub").textContent = "";
    return;
  }

  const W = 520, H = 232, L = 40, R = 12, T = 18, B = 30;
  const top = Math.max(100, Math.ceil(Math.max(...known) / 10) * 10);
  const colW = (W - L - R) / 12;
  const x = i => L + (i + 0.5) * colW;
  const y = v => T + (1 - v / top) * (H - T - B);
  const baseline = y(0);

  // Contiguous runs of known months: a month with nothing planned is a gap, not a drop to 0%
  const runs = [];
  values.forEach((v, i) => {
    if (v === null) return;
    if (i > 0 && values[i - 1] !== null) runs[runs.length - 1].push(i); else runs.push([i]);
  });
  const path = run => run.map((i, n) => `${n ? "L" : "M"}${x(i).toFixed(1)},${y(values[i]).toFixed(1)}`).join(" ");

  const gridValues = [0, 50, 100, ...(top > 100 ? [top] : [])];
  const grid = gridValues.map(g => `
    <line class="dash-grid-line" x1="${L}" x2="${W - R}" y1="${y(g)}" y2="${y(g)}"/>
    <text class="dash-axis" x="${L - 6}" y="${y(g) + 3}" text-anchor="end">${g}%</text>`).join("");

  const selected = data.month - 1;
  qs("dashTrend").innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" class="dash-svg" role="img" aria-label="Ocupación promedio de la planta por mes">
      <rect class="dash-band" x="${L + selected * colW}" y="${T - 8}" width="${colW}" height="${H - T - B + 8}" rx="3"/>
      ${grid}
      <line class="dash-limit-line" x1="${L}" x2="${W - R}" y1="${y(100)}" y2="${y(100)}"/>
      ${runs.map(run => run.length > 1 ? `<path class="dash-area" d="${path(run)} L${x(run[run.length - 1]).toFixed(1)},${baseline} L${x(run[0]).toFixed(1)},${baseline} Z"/>` : "").join("")}
      ${runs.map(run => `<path class="dash-line" d="${path(run)}"/>`).join("")}
      ${values.map((v, i) => v === null ? "" : `<circle class="dash-dot${i === selected ? " sel" : ""}" cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="${i === selected ? 5 : 3.2}"/>`).join("")}
      ${values[selected] === null ? "" : `<text class="dash-value-label" x="${x(selected).toFixed(1)}" y="${(y(values[selected]) - 11).toFixed(1)}" text-anchor="middle">${dashN(values[selected], 1)}%</text>`}
      ${DASH_MONTHS_SHORT.map((label, i) => `<text class="dash-axis${i === selected ? " sel" : ""}" x="${x(i).toFixed(1)}" y="${H - 10}" text-anchor="middle">${label}</text>`).join("")}
      ${values.map((v, i) => `<rect class="dash-hit" data-month="${i + 1}" x="${L + i * colW}" y="${T - 8}" width="${colW}" height="${H - T - B + 8}">
        <title>${dashCap(dashMonth(i + 1))}: ${v === null ? "sin carga planeada" : dashN(v, 1) + "% de ocupación"}</title></rect>`).join("")}
    </svg>
    <div class="chart-legend dash-legend">
      <span><span class="dash-key-line"></span>100% = capacidad de la planta</span>
      <span>Los meses sin carga planeada quedan en blanco.</span>
    </div>`;

  const name = dashCap(dashMonth(data.month)), previous = dashMonth(data.previous.month);
  const now = data.kpis.occupancy.pct, before = data.kpis.occupancy.previous_pct;
  qs("dashTrendSub").textContent = values[selected] === null
    ? `${name}: sin carga planeada.`
    : `${name}: ${dashN(now, 1)}%` + (before !== null ? ` frente a ${dashN(before, 1)}% en ${previous}.` : ".");
}

/* ── Chart 4: late orders that need attention ────────────── */

function renderDashAttention(data) {
  const { total, orders } = data.attention, name = dashMonth(data.month);
  const evaluated = data.kpis.on_time.evaluated;

  if (!orders.length) {
    qs("dashAttention").innerHTML = `<div class="dash-empty ${evaluated ? "good" : ""}">${evaluated
      ? `Ningún pedido atrasado en ${name}.`
      : `Aún no hay pedidos planeados en ${name}.`}</div>`;
    qs("dashAttentionSub").textContent = evaluated ? "Todos los pedidos planeados llegan a tiempo." : "";
    return;
  }

  const maxDays = Math.max(...orders.map(o => o.days_late));
  qs("dashAttention").innerHTML = `
    <div class="dash-late">
      ${orders.map(o => {
        const asked = shortDate(dashIsoToMs(o.requested_delivery_date)), due = shortDate(dashIsoToMs(o.calculated_delivery_date));
        const dates = `Solicitado para el ${asked} · entrega calculada ${due} · ${dashN(o.quantity_requested)} t`;
        return `<div class="dash-late-row" title="${escapeHtml(dates)}">
          <div class="dash-late-name">
            <span><strong>#${o.order_id}</strong> ${escapeHtml(o.customer_name)}</span>
            <small>pedido para ${asked} · entrega ${due}</small>
          </div>
          <div class="dash-late-bar"><span class="${o.lateness_status}" style="width:${Math.max(o.days_late / maxDays * 100, 6)}%"></span></div>
          <div class="dash-late-days ${o.lateness_status}">+${o.days_late} d</div>
        </div>`;
      }).join("")}
    </div>
    ${total > orders.length ? `<p class="dash-more">y ${dashPlural(total - orders.length, "pedido más", "pedidos más")} con atraso. Revisa la lista completa en Pedidos.</p>` : ""}
    <div class="chart-legend dash-legend">
      <span><span class="dash-key warning"></span>atrasado</span>
      <span><span class="dash-key critical"></span>crítico</span>
      <span>Los días se cuentan después de la fecha solicitada.</span>
    </div>`;
  qs("dashAttentionSub").textContent = `${dashPlural(total, "pedido tiene", "pedidos tienen")} atraso en ${name}${total > 1 ? "; estos son los más urgentes" : ""}.`;
}

/* ── Wiring ──────────────────────────────────────────────── */

qs("btnLoadDashboard").addEventListener("click", loadDashboard);
qs("btnDashPrev").addEventListener("click", () => dashShiftMonth(-1));
qs("btnDashNext").addEventListener("click", () => dashShiftMonth(1));
["dashYear", "dashMonth"].forEach(id => qs(id).addEventListener("change", loadDashboard));
qs("view-dashboard").addEventListener("click", e => {
  const target = e.target.closest("[data-month]");
  if (target) dashSelectMonth(Number(target.dataset.month));
});
