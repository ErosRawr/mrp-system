/* ── Planeación (unified workspace) ──────────────────────── */

const CRITERION_LABELS = {
  peps: "PEPS (FIFO)",
  prioritario: "Prioritario",
  heuristica: "Heurística",
  manual: "Manual",
};
const CRITERION_DESC = {
  peps: "Ordena estrictamente por fecha solicitada.",
  prioritario: "Pedidos prioritarios primero, luego por fecha.",
  heuristica: "Prioridad → tonelaje (15k+) → tipo de pedido → fecha.",
};

/* ── State ───────────────────────────────────────────────── */

let planMonthOrders = [];       // raw orders for current month
let previewResults = null;      // last preview results (unsaved)
let previewStrategy = null;     // criterion or "manual"
let planSavedCriterion = null;  // what's actually saved

/* ── Tab switching ───────────────────────────────────────── */

document.querySelectorAll(".plan-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".plan-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".plan-tab-panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    const panel = qs("panel" + capitalize(tab.dataset.tab));
    if (panel) panel.classList.add("active");
  });
});

function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

/* ── Load month ──────────────────────────────────────────── */

qs("btnLoadPlanMonth").addEventListener("click", loadPlanMonth);

async function loadPlanMonth() {
  const done = setLoading("btnLoadPlanMonth", "Cargando");
  try {
    const year = val("planYear"), month = val("planMonth");

    // Fetch orders and planning status in parallel
    const [allOrders, months] = await Promise.all([
      api("/orders"),
      api("/planning/months"),
    ]);

    planMonthOrders = allOrders.filter(
      o => o.planning_year == year && o.planning_month == month
    );

    const mp = months.find(m => m.planning_year == year && m.planning_month == month);
    planSavedCriterion = mp ? mp.criterion : null;

    // Show saved badge
    const badge = qs("planSavedBadge");
    if (planSavedCriterion) {
      badge.style.display = "inline-flex";
      qs("planSavedCriterion").textContent = CRITERION_LABELS[planSavedCriterion] || planSavedCriterion;
    } else {
      badge.style.display = "none";
    }

    setStatus("planHeaderStatus", `${planMonthOrders.length} pedido(s) en ${year}-${String(month).padStart(2, "0")}.`);

    // Populate manual blocks. A month planned by hand comes back as it was
    // saved; any other month starts with every order in Standard.
    const sequence = planSavedCriterion === "manual"
      ? await api(`/planning/manual-sequence?year=${year}&month=${month}`)
      : null;
    populateManualBlocks(planMonthOrders, sequence);

    // Clear previous results
    clearResults();
  } catch (e) { setStatus("planHeaderStatus", e.message, true); }
  finally { done(); }
}

/* ── Compare strategies ──────────────────────────────────── */

qs("btnCompareStrategies").addEventListener("click", async () => {
  const done = setLoading("btnCompareStrategies", "Comparando");
  try {
    const year = val("planYear"), month = val("planMonth");
    setStatus("compareStatus", "Comparando…");
    const data = await api(`/planning/compare?year=${year}&month=${month}`);

    setStatus("compareStatus", "Listo. Nada fue guardado — esto es solo una comparación.");

    const container = qs("criteriaColumns");
    container.innerHTML = "";

    Object.entries(data.comparison).forEach(([criterion, info]) => {
      const col = document.createElement("div");
      col.className = "criterion-col";

      const s = info.summary;
      let rowsHtml = "";
      info.results.forEach(r => {
        if (r.error) {
          rowsHtml += `<div class="criterion-order-row"><span class="oname danger-text">#${r.order_id} ${r.customer_name ?? ""} — error</span></div>`;
          return;
        }
        let dot = "⚪";
        if (r.lateness_status === "on_time") dot = "🟢";
        else if (r.lateness_status === "warning") dot = "🟡";
        else if (r.lateness_status === "critical") dot = "🔴";
        const priorityMark = r.is_priority ? "★ " : "";
        rowsHtml += `
          <div class="criterion-order-row">
            <span class="oname">${dot} ${priorityMark}#${r.order_id} ${r.customer_name}</span>
            <span class="odate">${r.calculated_delivery_date}</span>
          </div>`;
      });

      col.innerHTML = `
        <div class="criterion-col-title">${CRITERION_LABELS[criterion]}</div>
        <div class="criterion-col-sub">${CRITERION_DESC[criterion]}</div>
        <div class="criterion-summary">
          <span class="criterion-badge">🟢 ${s.on_time} a tiempo</span>
          <span class="criterion-badge">🟡 ${s.warning} atrasado</span>
          <span class="criterion-badge">🔴 ${s.critical} crítico</span>
        </div>
        ${rowsHtml}`;
      container.appendChild(col);
    });

    qs("compareCommitPanel").style.display = "block";
  } catch (e) { setStatus("compareStatus", e.message, true); }
  finally { done(); }
});

/* ── Commit a strategy ───────────────────────────────────── */

qs("btnCommitCriterion").addEventListener("click", async () => {
  const done = setLoading("btnCommitCriterion", "Guardando");
  try {
    const year = val("planYear"), month = val("planMonth"), criterion = val("commitCriterion");
    setStatus("commitStatus", "Ejecutando y guardando…");
    const data = await api(`/planning/run?year=${year}&month=${month}&criterion=${criterion}`, { method: "POST" });
    setStatus("commitStatus", `Guardado. ${data.orders_planned} pedido(s) planeado(s) con criterio "${data.criterion}".`);

    // Highlight selected column
    document.querySelectorAll(".criterion-col").forEach(c => c.classList.remove("selected"));
    const idx = ["peps", "prioritario", "heuristica"].indexOf(criterion);
    const cols = document.querySelectorAll(".criterion-col");
    if (cols[idx]) cols[idx].classList.add("selected");

    // Update saved state
    planSavedCriterion = criterion;
    qs("planSavedBadge").style.display = "inline-flex";
    qs("planSavedCriterion").textContent = CRITERION_LABELS[criterion] || criterion;

    // Show results
    showResults(data.results, `Planeación ${year}-${String(month).padStart(2, "0")} (${data.criterion}) — ${data.orders_planned} pedidos`);
    clearPreviewState();
  } catch (e) { setStatus("commitStatus", e.message, true); }
  finally { done(); }
});

/* ── Manual blocks: drag & drop + filters ────────────────── */

function populateManualBlocks(orders, sequence = null) {
  const containers = {
    expedite: qs("panelManual").querySelector('[data-block-id="expedite"]'),
    standard: qs("panelManual").querySelector('[data-block-id="standard"]'),
    hold: qs("panelManual").querySelector('[data-block-id="hold"]'),
  };
  Object.values(containers).forEach(c => { if (c) c.innerHTML = ""; });

  // Saved sequence first (planned orders, then Hold). The backend stores one flat
  // order, so Expedite vs Standard is not remembered: everything planned lands in
  // Standard. Anything not in the sequence (an order added after saving) goes at
  // the end of Standard, which is also where the planner puts it.
  const byId = new Map(orders.map(o => [o.id, o]));
  const placed = new Set();
  const place = (id, container) => {
    const order = byId.get(id);
    if (!order || placed.has(id)) return;
    container.appendChild(createOrderCard(order));
    placed.add(id);
  };
  if (sequence) {
    sequence.order_ids.forEach(id => place(id, containers.standard));
    sequence.hold_ids.forEach(id => place(id, containers.hold));
  }
  orders.forEach(o => place(o.id, containers.standard));

  updateBlockCounts();
  applyManualFilters();
}

function createOrderCard(o) {
  const card = document.createElement("div");
  card.className = "order-card";
  card.draggable = true;
  card.dataset.orderId = o.id;
  card.dataset.priority = o.is_priority ? "1" : "0";
  card.dataset.tipo = o.tipo_pedido || "";
  card.dataset.status = o.lateness_status || "unplanned";
  card.dataset.customer = o.customer_name.toLowerCase();

  const priorityMark = o.is_priority ? '<span class="priority-star">★</span> ' : "";
  const tipoLabel = o.tipo_pedido ? `<span class="order-tipo">${o.tipo_pedido}</span>` : "";
  const tons = parseFloat(o.quantity_requested).toLocaleString();

  let statusDot = "";
  if (o.lateness_status === "on_time") statusDot = "🟢";
  else if (o.lateness_status === "warning") statusDot = "🟡";
  else if (o.lateness_status === "critical") statusDot = "🔴";

  card.innerHTML = `
    <span class="order-card-grip" title="Arrastrar">☰</span>
    <span class="order-card-info">
      ${priorityMark}#${o.id} ${o.customer_name}
      <span class="order-card-meta">${tons} t ${tipoLabel}</span>
    </span>
    <span class="order-card-date">${o.requested_delivery_date ?? "—"}</span>
    <span class="order-card-status">${statusDot}</span>
    <span class="order-card-actions">
      <button class="btn small order-move-up" title="Mover arriba">▲</button>
      <button class="btn small order-move-down" title="Mover abajo">▼</button>
    </span>`;

  // Drag events
  card.addEventListener("dragstart", e => {
    e.dataTransfer.setData("text/plain", o.id);
    card.classList.add("dragging");
  });
  card.addEventListener("dragend", () => card.classList.remove("dragging"));

  // Move up/down buttons
  card.querySelector(".order-move-up").addEventListener("click", e => {
    e.stopPropagation();
    const prev = card.previousElementSibling;
    if (prev) card.parentNode.insertBefore(card, prev);
    updateBlockCounts();
  });
  card.querySelector(".order-move-down").addEventListener("click", e => {
    e.stopPropagation();
    const next = card.nextElementSibling;
    if (next) card.parentNode.insertBefore(next, card);
    updateBlockCounts();
  });

  return card;
}

// Drop zone setup for each block container
document.querySelectorAll(".plan-block-orders").forEach(container => {
  container.addEventListener("dragover", e => {
    e.preventDefault();
    const dragging = document.querySelector(".order-card.dragging");
    if (!dragging) return;
    const afterElement = getDragAfterElement(container, e.clientY);
    if (afterElement) {
      container.insertBefore(dragging, afterElement);
    } else {
      container.appendChild(dragging);
    }
  });
  container.addEventListener("drop", e => {
    e.preventDefault();
    updateBlockCounts();
  });
});

function getDragAfterElement(container, y) {
  const cards = [...container.querySelectorAll(".order-card:not(.dragging)")];
  return cards.reduce((closest, child) => {
    const box = child.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closest.offset) {
      return { offset, element: child };
    }
    return closest;
  }, { offset: Number.NEGATIVE_INFINITY }).element;
}

function updateBlockCounts() {
  document.querySelectorAll(".plan-block").forEach(block => {
    const count = block.querySelector(".plan-block-orders").childElementCount;
    const countEl = block.querySelector(".plan-block-count");
    if (countEl) countEl.textContent = `${count} pedido(s)`;
  });
}

/* ── Filters ─────────────────────────────────────────────── */

["manualSearch", "manualFilterPriority", "manualFilterTipo", "manualFilterStatus"].forEach(id => {
  qs(id).addEventListener("input", applyManualFilters);
  qs(id).addEventListener("change", applyManualFilters);
});

function applyManualFilters() {
  const search = val("manualSearch").toLowerCase().trim();
  const priority = val("manualFilterPriority");
  const tipo = val("manualFilterTipo");
  const status = val("manualFilterStatus");

  document.querySelectorAll(".order-card").forEach(card => {
    let show = true;
    if (search && !card.dataset.customer.includes(search) && !card.dataset.orderId.includes(search)) show = false;
    if (priority && card.dataset.priority !== priority) show = false;
    if (tipo && card.dataset.tipo !== tipo) show = false;
    if (status && card.dataset.status !== status) show = false;
    card.style.display = show ? "" : "none";
  });
}

/* ── Manual preview ──────────────────────────────────────── */

qs("btnPreviewManual").addEventListener("click", async () => {
  const done = setLoading("btnPreviewManual", "Previsualizando");
  try {
    const year = parseInt(val("planYear")), month = parseInt(val("planMonth"));

    // Collect order IDs from Expedite + Standard blocks (in visual order)
    const orderIds = getBlockOrderIds("expedite").concat(getBlockOrderIds("standard"));
    const holdIds = getBlockOrderIds("hold");

    if (orderIds.length === 0 && holdIds.length === 0) {
      setStatus("manualStatus", "No hay pedidos para previsualizar.", true);
      return;
    }

    setStatus("manualStatus", "Previsualizando…");
    const data = await api("/planning/preview-manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year, month, order_ids: orderIds, hold_ids: holdIds }),
    });

    previewResults = data;
    previewStrategy = "manual";

    // Show unsaved banner
    qs("planUnsavedBanner").style.display = "flex";
    qs("unsavedStrategyLabel").textContent = "Secuencia manual";

    // Show impact KPIs
    showImpact(data.summary);

    // Show results table
    showResults(data.results,
      `Vista previa — ${data.results.length} pedido(s), ${holdIds.length} en Hold`);

    // Enable save button
    qs("btnSaveManual").disabled = false;

    setStatus("manualStatus", "Vista previa lista. Revisa el resultado y guarda si estás conforme.");
  } catch (e) { setStatus("manualStatus", e.message, true); }
  finally { done(); }
});

function getBlockOrderIds(blockId) {
  const container = qs("panelManual").querySelector(`[data-block-id="${blockId}"]`);
  if (!container) return [];
  return [...container.querySelectorAll(".order-card")].map(c => parseInt(c.dataset.orderId));
}

/* ── Manual save ─────────────────────────────────────────── */

qs("btnSaveManual").addEventListener("click", () => {
  if (!previewResults) return;
  // Show confirmation modal
  const summary = previewResults.summary;
  qs("saveModalBody").innerHTML = `
    <p><strong>Estrategia:</strong> Secuencia manual</p>
    <p><strong>Pedidos planificados:</strong> ${previewResults.results.length}</p>
    <p><strong>En Hold (excluidos):</strong> ${(previewResults.held_order_ids || []).length}</p>
    <p>🟢 ${summary.on_time} a tiempo · 🟡 ${summary.warning} atrasados · 🔴 ${summary.critical} críticos</p>
    <p>¿Guardar este plan?</p>`;
  qs("saveModal").style.display = "flex";
});

qs("btnCancelSave").addEventListener("click", () => {
  qs("saveModal").style.display = "none";
});

qs("btnConfirmSave").addEventListener("click", async () => {
  qs("saveModal").style.display = "none";
  const done = setLoading("btnSaveManual", "Guardando");
  try {
    const year = parseInt(val("planYear")), month = parseInt(val("planMonth"));
    const orderIds = getBlockOrderIds("expedite").concat(getBlockOrderIds("standard"));
    const holdIds = getBlockOrderIds("hold");

    const data = await api("/planning/run-manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year, month, order_ids: orderIds, hold_ids: holdIds }),
    });

    // Update saved state
    planSavedCriterion = "manual";
    qs("planSavedBadge").style.display = "inline-flex";
    qs("planSavedCriterion").textContent = "Manual";

    showResults(data.results,
      `Planeación ${year}-${String(month).padStart(2, "0")} (manual) — ${data.orders_planned} pedidos`);
    clearPreviewState();

    setStatus("manualStatus", `Guardado. ${data.orders_planned} pedido(s) planeado(s) con secuencia manual.`);
  } catch (e) { setStatus("manualStatus", e.message, true); }
  finally { done(); }
});

/* ── Dismiss preview ─────────────────────────────────────── */

qs("btnDismissPreview").addEventListener("click", () => {
  clearPreviewState();
  clearResults();
});

function clearPreviewState() {
  previewResults = null;
  previewStrategy = null;
  qs("planUnsavedBanner").style.display = "none";
  qs("btnSaveManual").disabled = true;
}

/* ── Results display (shared) ────────────────────────────── */

function showResults(results, summaryText) {
  const summary = qs("planSummary");
  summary.style.display = "block";
  summary.innerHTML = summaryText;

  const body = qs("planBody");
  body.innerHTML = "";

  results.forEach(r => {
    const tr = document.createElement("tr");
    if (r.error) {
      tr.innerHTML = `<td>${r.order_id}</td><td>${r.customer_name ?? "—"}</td><td colspan="6" class="danger-text">${r.error}</td>`;
      body.appendChild(tr);
      return;
    }

    let statusLabel = "—";
    if (r.lateness_status === "critical") statusLabel = '<span class="danger-text">🔴 ATRASO CRÍTICO</span>';
    else if (r.lateness_status === "warning") statusLabel = '<span class="warn-text">⚠ Atrasado</span>';
    else if (r.lateness_status === "on_time") statusLabel = '<span class="highlight">A tiempo</span>';

    const tons = r.quantity_requested ? parseFloat(r.quantity_requested).toLocaleString() : "—";
    const priorityMark = r.is_priority ? "★" : "";

    tr.style.cursor = "pointer";
    tr.innerHTML = `
      <td>${r.order_id}</td><td>${r.customer_name}</td>
      <td class="num">${tons}</td>
      <td>${r.tipo_pedido ?? "—"}</td><td>${priorityMark}</td>
      <td>${r.requested_delivery_date ?? "—"}</td><td>${r.calculated_delivery_date}</td>
      <td>${statusLabel}</td>`;
    tr.addEventListener("click", () => togglePlanRouteDiagram(r, tr));
    body.appendChild(tr);
  });

  qs("planResultsTable").style.display = "table";
}

function showImpact(summary) {
  qs("impactOnTime").textContent = summary.on_time;
  qs("impactWarning").textContent = summary.warning;
  qs("impactCritical").textContent = summary.critical;
  qs("impactBottleneck").textContent = summary.bottleneck || "—";
  qs("planImpact").style.display = "block";
}

function clearResults() {
  qs("planSummary").style.display = "none";
  qs("planImpact").style.display = "none";
  qs("planResultsTable").style.display = "none";
  qs("planBody").innerHTML = "";
}

/* ── Route diagram (unchanged) ───────────────────────────── */

function togglePlanRouteDiagram(result, rowEl) {
  const existing = rowEl.nextElementSibling;
  if (existing && existing.classList.contains("plan-diagram-row")) {
    existing.remove();
    return;
  }
  document.querySelectorAll(".plan-diagram-row").forEach(r => r.remove());

  const diagramRow = document.createElement("tr");
  diagramRow.className = "plan-diagram-row";
  const cell = document.createElement("td");
  cell.colSpan = 8;
  cell.innerHTML = `<div class="chart-block" style="margin:.6rem 0;">
    <div class="chart-title">Ruta de proceso — pedido #${result.order_id}, semanas asignadas</div>
    <div class="plan-diagram-target"></div>
  </div>`;
  diagramRow.appendChild(cell);
  rowEl.insertAdjacentElement("afterend", diagramRow);

  renderPlanWeekDiagram(result.team_schedule, cell.querySelector(".plan-diagram-target"));
}

function renderPlanWeekDiagram(teamSchedule, container) {
  const production = [...teamSchedule].reverse();
  const boxWidth = 160, boxHeight = 70, gap = 60;
  const width = production.length * boxWidth + (production.length - 1) * gap + 40;
  const height = 150;
  const y = 30;

  let svg = "";
  let x = 20;

  production.forEach((s, i) => {
    const hasError = !!s.error;
    const fillColor = hasError ? "#2a1c1c" : "#1d2226";
    const strokeColor = hasError ? "#d9695a" : "#4a9eda";
    const weekLabel = hasError ? "—" :
      (s.weeks_elapsed === 1 ? `Sem ${s.breakdown?.[0]?.week_number ?? "?"}` :
       `Sem ${s.breakdown?.[0]?.week_number ?? "?"}–${s.end_week}`);

    svg += `
      <g>
        <rect x="${x}" y="${y}" width="${boxWidth}" height="${boxHeight}" rx="3"
              fill="${fillColor}" stroke="${strokeColor}" stroke-width="1.5" />
        <text x="${x + boxWidth/2}" y="${y + 24}" text-anchor="middle" fill="#fff"
              font-size="13" font-family="-apple-system, sans-serif" font-weight="600">${s.team_name}</text>
        <text x="${x + boxWidth/2}" y="${y + 44}" text-anchor="middle" fill="#4a9eda"
              font-size="12" font-family="ui-monospace, monospace">${weekLabel}</text>
        <text x="${x + boxWidth/2}" y="${y + 60}" text-anchor="middle" fill="#838d94"
              font-size="10" font-family="ui-monospace, monospace">${s.fully_scheduled ? "completo" : "parcial"}</text>
      </g>`;

    if (i < production.length - 1) {
      const arrowX1 = x + boxWidth;
      const arrowX2 = x + boxWidth + gap;
      const arrowY = y + boxHeight / 2;
      svg += `
        <line x1="${arrowX1}" y1="${arrowY}" x2="${arrowX2 - 8}" y2="${arrowY}" stroke="#5a636a" stroke-width="1.5" />
        <polygon points="${arrowX2-8},${arrowY-5} ${arrowX2},${arrowY} ${arrowX2-8},${arrowY+5}" fill="#5a636a" />`;
    }
    x += boxWidth + gap;
  });

  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" style="width:100%; max-width:${width}px;">${svg}</svg>`;
}
