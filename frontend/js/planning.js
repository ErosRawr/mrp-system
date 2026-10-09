/* ── Planeación ───────────────────────────────────────────── */

qs("btnRunPlanning").addEventListener("click", async () => {
  const done = setLoading("btnRunPlanning", "Ejecutando");
  try {
    const year = val("planYear"), month = val("planMonth"), criterion = val("planCriterion");
    setStatus("planStatus", "Ejecutando…");
    const data = await api(`/planning/run?year=${year}&month=${month}&criterion=${criterion}`, { method: "POST" });

    setStatus("planStatus", `Listo. ${data.orders_planned} pedido(s) planeado(s) con criterio "${data.criterion}".`);
    const summary = qs("planSummary");
    summary.style.display = "block";
    summary.innerHTML = `Planeación ${data.planning_year}-${String(data.planning_month).padStart(2,"0")} (${data.criterion}) — <span class="big-num">${data.orders_planned}</span> pedidos`;

    const body = qs("planBody");
    body.innerHTML = "";
    data.results.forEach(r => {
      const tr = document.createElement("tr");
      if (r.error) {
        tr.innerHTML = `<td>${r.order_id}</td><td>${r.customer_name ?? "—"}</td><td colspan="3" class="danger-text">${r.error}</td>`;
        body.appendChild(tr);
        return;
      }

      let statusLabel = "—";
      if (r.lateness_status === "critical") statusLabel = '<span class="danger-text">🔴 ATRASO CRÍTICO</span>';
      else if (r.lateness_status === "warning") statusLabel = '<span class="warn-text">⚠ Atrasado</span>';
      else if (r.lateness_status === "on_time") statusLabel = '<span class="highlight">A tiempo</span>';

      tr.style.cursor = "pointer";
      tr.innerHTML = `
        <td>${r.order_id}</td><td>${r.customer_name}</td>
        <td>${r.requested_delivery_date ?? "—"}</td><td>${r.calculated_delivery_date}</td>
        <td>${statusLabel}</td>`;
      tr.addEventListener("click", () => togglePlanRouteDiagram(r, tr));
      body.appendChild(tr);
    });
  } catch (e) { setStatus("planStatus", e.message, true); }
  finally { done(); }
});

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
  cell.colSpan = 5;
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