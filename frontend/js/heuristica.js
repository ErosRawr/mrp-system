/* ── Heurística (comparación) ─────────────────────────────── */

const CRITERION_LABELS = {
  peps: "PEPS (FIFO)",
  prioritario: "Prioritario",
  heuristica: "Heurística",
};
const CRITERION_DESC = {
  peps: "Ordena estrictamente por fecha solicitada.",
  prioritario: "Pedidos prioritarios primero, luego por fecha.",
  heuristica: "Prioridad → tonelaje (15k+) → tipo de pedido → fecha.",
};

qs("btnCompareHeuristics").addEventListener("click", async () => {
  try {
    const year = val("heurYear"), month = val("heurMonth");
    setStatus("heurStatus", "Comparando…");
    const data = await api(`/planning/compare?year=${year}&month=${month}`);

    setStatus("heurStatus", "Listo. Nada fue guardado — esto es solo una comparación.");

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

    qs("heurCommitPanel").style.display = "block";
  } catch (e) { setStatus("heurStatus", e.message, true); }
});

qs("btnCommitHeuristic").addEventListener("click", async () => {
  try {
    const year = val("heurYear"), month = val("heurMonth"), criterion = val("heurCommitCriterion");
    setStatus("heurCommitStatus", "Ejecutando y guardando…");
    const data = await api(`/planning/run?year=${year}&month=${month}&criterion=${criterion}`, { method: "POST" });
    setStatus("heurCommitStatus", `Guardado. ${data.orders_planned} pedido(s) planeado(s) con criterio "${data.criterion}". Revisa la pestaña Planeación Mensual para ver el detalle.`);

    document.querySelectorAll(".criterion-col").forEach(c => c.classList.remove("selected"));
    const idx = ["peps", "prioritario", "heuristica"].indexOf(criterion);
    const cols = document.querySelectorAll(".criterion-col");
    if (cols[idx]) cols[idx].classList.add("selected");
  } catch (e) { setStatus("heurCommitStatus", e.message, true); }
});

