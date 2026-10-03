/* ── Requerimientos ───────────────────────────────────────── */

qs("btnCalcReq").addEventListener("click", async () => {
  try {
    const orderId = val("reqOrder");
    if (!orderId) { setStatus("reqStatus", "Selecciona un pedido.", true); return; }
    setStatus("reqStatus", "Calculando…");
    const data = await api(`/orders/${orderId}/requirements`);

    if (data.error) {
      setStatus("reqStatus", data.error, true);
      qs("reqSummary").style.display = "none";
      qs("reqBody").innerHTML = "";
      return;
    }

    setStatus("reqStatus", "Listo.");
    const summary = qs("reqSummary");
    summary.style.display = "block";
    summary.innerHTML = `
      Pedido #${data.order_id} — ${data.customer_name} · ${data.quantity_requested} ton · entra en ${data.entry_team}<br>
      F. solicitada: ${data.requested_delivery_date ?? "—"} · F. calculada: ${data.calculated_delivery_date ?? "— (ejecuta la planeación)"}<br>
      <span class="big-num">${data.total_raw_material_needed}</span> ton de materia prima requeridas en total`;

    const body = qs("reqBody");
    body.innerHTML = "";
    data.steps.forEach(s => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${s.team_name}</td><td class="num">${s.sequence_order}</td>
        <td class="num">${s.output_needed}</td><td class="num">${s.input_needed ?? "—"}</td>
        <td class="num">${s.efficiency}</td><td class="num">${s.monthly_capacity}</td><td class="num">${s.weekly_capacity}</td>`;
      body.appendChild(tr);
    });
  } catch (e) { setStatus("reqStatus", e.message, true); }
});

