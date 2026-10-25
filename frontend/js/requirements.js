/* ── Requerimientos ───────────────────────────────────────────
   Two views of the same pure material calculation:
     - one order: where the steel is lost, team by team
     - the whole month: totals, what each team has to process, and one line per order */

const reqNum = (n, digits = 2) => (n === null || n === undefined) ? "—"
  : Number(n).toLocaleString("es-MX", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const reqPct = fraction => (fraction === null || fraction === undefined) ? "—" : (fraction * 100).toFixed(1) + "%";

function reqCard(label, value, sub = "", tone = "") {
  return `<div class="kpi-card ${tone}"><div class="kpi-label">${label}</div>` +
         `<div class="kpi-value">${value}</div>${sub ? `<div class="kpi-sub">${sub}</div>` : ""}</div>`;
}

function reqClear() {
  ["reqCards", "reqFlow", "reqTables"].forEach(id => { qs(id).innerHTML = ""; });
}

/* The picker only lists the orders of the selected month, plus "the whole month". */
async function loadRequirementOrders() {
  const year = val("reqYear"), month = val("reqMonth");
  const all = await api("/orders");
  const monthOrders = all.filter(o => String(o.planning_year) === String(year) && String(o.planning_month) === String(month));

  const sel = qs("reqOrder");
  const previous = sel.value;
  sel.innerHTML = `<option value="">Todo el mes (${monthOrders.length} pedido${monthOrders.length === 1 ? "" : "s"})</option>` +
    monthOrders.map(o => `<option value="${o.id}">#${o.id} — ${escapeHtml(o.customer_name)} (${reqNum(o.quantity_requested, 0)} t)</option>`).join("");
  if (monthOrders.some(o => String(o.id) === previous)) sel.value = previous;
}

function reqPeriod() {
  const year = parseInt(val("reqYear"), 10), month = parseInt(val("reqMonth"), 10);
  if (!(year >= 1970 && year <= 2200)) { setStatus("reqStatus", "El año debe estar entre 1970 y 2200.", true); return null; }
  if (!(month >= 1 && month <= 12)) { setStatus("reqStatus", "El mes debe estar entre 1 y 12.", true); return null; }
  return { year, month };
}

async function calcRequirements() {
  const done = setLoading("btnCalcReq", "Calculando");
  try {
    const period = reqPeriod();
    if (!period) return;
    setStatus("reqStatus", "Calculando…");
    const orderId = val("reqOrder");
    if (orderId) renderRequirementOrder(await api(`/orders/${orderId}/requirements`));
    else renderRequirementMonth(period, await api(`/requirements?year=${period.year}&month=${period.month}`));
    setStatus("reqStatus", "");
  } catch (e) {
    reqClear();
    setStatus("reqStatus", e.message, true);
  } finally { done(); }
}

async function refreshRequirements() {
  try {
    await loadRequirementOrders();
    await calcRequirements();
  } catch (e) { setStatus("reqStatus", e.message, true); }
}

/* ── One order ───────────────────────────────────────────── */

function renderRequirementOrder(data) {
  if (data.error) {
    reqClear();
    qs("reqCards").innerHTML = `<div class="req-error">${escapeHtml(data.error)}</div>`;
    return;
  }
  const lossShare = data.total_loss / data.total_raw_material_needed;

  qs("reqCards").innerHTML = `
    <div class="req-head">
      <div>
        <div class="req-title">#${data.order_id} — ${escapeHtml(data.customer_name)}</div>
        <div class="req-sub">entra en ${escapeHtml(data.entry_team)} · F. solicitada ${data.requested_delivery_date ?? "—"} ·
          F. calculada ${data.calculated_delivery_date ?? "— (ejecuta la planeación)"}</div>
      </div>
      <button class="btn small" id="btnReqBack">← Todo el mes</button>
    </div>
    <div class="kpi-grid req-cards">
      ${reqCard("Producto terminado", reqNum(data.quantity_requested) + " t", "lo que pidió el cliente", "good")}
      ${reqCard("Materia prima requerida", reqNum(data.total_raw_material_needed) + " t", "lo que entra al primer equipo")}
      ${reqCard("Merma total", reqNum(data.total_loss) + " t", `${(lossShare * 100).toFixed(1)}% de la materia prima`, "warn")}
      ${reqCard("Rendimiento global", reqPct(data.overall_yield), "terminado ÷ materia prima")}
    </div>`;
  qs("btnReqBack").addEventListener("click", () => { qs("reqOrder").value = ""; calcRequirements(); });

  // The calculation walks backward from the entry team; the page reads in production order.
  const production = [...data.steps].reverse();
  const raw = data.total_raw_material_needed;

  qs("reqFlow").innerHTML = `
    <div class="req-section-title">Recorrido del material, de materia prima a producto terminado</div>
    <div class="req-flow">
      ${production.map((s, i) => `
        <div class="req-flow-row">
          <div class="req-flow-team"><span class="req-flow-step">${i + 1}</span>${escapeHtml(s.team_name)}</div>
          <div class="req-flow-track">
            <div class="req-flow-bar" style="width:${(s.input_needed / raw * 100).toFixed(2)}%"
                 title="Entran ${reqNum(s.input_needed)} t, salen ${reqNum(s.output_needed)} t">
              <span class="req-flow-out" style="width:${(s.output_needed / s.input_needed * 100).toFixed(2)}%"></span>
              <span class="req-flow-loss"></span>
            </div>
          </div>
          <div class="req-flow-nums">${reqNum(s.input_needed)} → ${reqNum(s.output_needed)} t
            <span class="req-flow-lost">−${reqNum(s.loss)}</span></div>
        </div>`).join("")}
    </div>
    <div class="chart-legend">
      <span><span class="req-key out"></span>toneladas que salen del equipo</span>
      <span><span class="req-key loss"></span>merma (lo que el equipo descarta)</span>
    </div>`;

  qs("reqTables").innerHTML = `
    <table>
      <thead><tr>
        <th>Equipo</th><th class="num">Seq</th><th class="num">Ton. entrada</th><th class="num">Ton. salida</th>
        <th class="num">Merma</th><th class="num">Rend.</th><th class="num">Cap. mensual</th><th class="num">Cap. semanal</th>
      </tr></thead>
      <tbody>${production.map(s => `
        <tr>
          <td>${escapeHtml(s.team_name)}</td><td class="num">${s.sequence_order}</td>
          <td class="num">${reqNum(s.input_needed)}</td><td class="num">${reqNum(s.output_needed)}</td>
          <td class="num">${reqNum(s.loss)}</td><td class="num">${(s.efficiency * 100).toFixed(1)}%</td>
          <td class="num">${reqNum(s.monthly_capacity, 0)}</td><td class="num">${reqNum(s.weekly_capacity, 0)}</td>
        </tr>`).join("")}
      </tbody>
    </table>`;
}

/* ── The whole month ─────────────────────────────────────── */

function renderRequirementMonth(period, data) {
  const label = `${period.year}-${String(period.month).padStart(2, "0")}`;
  if (!data.orders_count && !data.errors.length) {
    reqClear();
    qs("reqCards").innerHTML = `<div class="req-empty">No hay pedidos en ${label}.</div>`;
    return;
  }
  const t = data.totals;

  qs("reqCards").innerHTML = `
    <div class="kpi-grid req-cards">
      ${reqCard("Pedidos", data.orders_count, `en ${label}`)}
      ${reqCard("Producto terminado", reqNum(t.finished, 0) + " t", "tonelaje pedido", "good")}
      ${reqCard("Materia prima requerida", reqNum(t.raw, 0) + " t", "entra al primer equipo")}
      ${reqCard("Merma total", reqNum(t.loss, 0) + " t", t.raw ? `${(t.loss / t.raw * 100).toFixed(1)}% de la materia prima` : "", "warn")}
      ${reqCard("Rendimiento global", reqPct(t.overall_yield), "terminado ÷ materia prima")}
    </div>`;

  qs("reqFlow").innerHTML = `
    <div class="req-section-title">Carga del mes por equipo</div>
    <div class="req-note">Toneladas que cada equipo debe producir para estos pedidos, frente a su capacidad mensual.
      Es solo una comparación de material contra capacidad; el calendario real lo resuelve la planeación.</div>
    <div class="req-flow">
      ${data.teams.map(team => {
        const load = team.load_pct ?? 0;
        return `
        <div class="req-load-row">
          <div class="req-flow-team"><span class="req-flow-step">${team.sequence_order}</span>${escapeHtml(team.team_name)}</div>
          <div class="req-load-track"><div class="req-load-fill${load > 100 ? " over" : ""}" style="width:${Math.min(load, 100)}%"></div></div>
          <div class="req-flow-nums">${team.orders
            ? `${reqNum(team.output_needed, 0)} de ${reqNum(team.monthly_capacity, 0)} t <span class="req-load-pct${load > 100 ? " over" : ""}">${load.toFixed(1)}%</span>`
            : "sin pedidos"}</div>
        </div>`;
      }).join("")}
    </div>`;

  const errorsHtml = data.errors.length ? `
    <div class="req-error">${data.errors.length} pedido(s) no se pudieron calcular:
      ${data.errors.map(e => `#${e.order_id} ${escapeHtml(e.customer_name)}`).join(", ")}</div>` : "";

  qs("reqTables").innerHTML = `
    <div class="req-section-title">Pedidos del mes <span class="req-hint">— haz clic en uno para ver su recorrido</span></div>
    ${errorsHtml}
    <table>
      <thead><tr>
        <th>Pedido</th><th>Cliente</th><th>Entra en</th><th class="num">Ton. terminadas</th>
        <th class="num">Ton. materia prima</th><th class="num">Merma</th><th class="num">Rend.</th>
      </tr></thead>
      <tbody>${data.orders.map(o => `
        <tr class="req-row" data-order-id="${o.order_id}">
          <td>#${o.order_id}</td><td>${escapeHtml(o.customer_name)}</td><td>${escapeHtml(o.entry_team)}</td>
          <td class="num">${reqNum(o.quantity_requested)}</td><td class="num">${reqNum(o.total_raw_material_needed)}</td>
          <td class="num">${reqNum(o.total_loss)}</td><td class="num">${reqPct(o.overall_yield)}</td>
        </tr>`).join("")}
      </tbody>
    </table>`;

  qs("reqTables").querySelectorAll(".req-row").forEach(row => {
    row.addEventListener("click", () => {
      qs("reqOrder").value = row.dataset.orderId;
      calcRequirements();
      window.scrollTo({ top: 0 });
    });
  });
}

/* ── Wiring ──────────────────────────────────────────────── */

qs("btnCalcReq").addEventListener("click", refreshRequirements);
qs("reqOrder").addEventListener("change", calcRequirements);
["reqYear", "reqMonth"].forEach(id => qs(id).addEventListener("change", refreshRequirements));
