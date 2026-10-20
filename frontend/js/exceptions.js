/* ── Disponibilidad ───────────────────────────────────────── */

async function loadExceptions() {
  const exceptions = await api("/team-week-exceptions");
  const body = qs("excBody");
  body.innerHTML = "";
  exceptions.forEach(x => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${x.id}</td><td class="num">${x.team_id}</td><td class="num">${x.year}</td>
      <td class="num">${x.week_number}</td><td class="num">${x.capacity_multiplier}</td>
      <td>${x.reason ?? "—"}</td>
      <td><button class="btn small" onclick="deleteException(${x.id})">Eliminar</button></td>`;
    body.appendChild(tr);
  });
}

qs("btnSetExc").addEventListener("click", async () => {
  try {
    const params = new URLSearchParams({
      team_id: val("excTeam"), year: val("excYear"), week_number: val("excWeek"),
      capacity_multiplier: val("excMultiplier"),
    });
    const reason = val("excReason");
    if (reason) params.set("reason", reason);
    await api("/team-week-exceptions?" + params, { method: "POST" });
    setStatus("excStatus", "Excepción guardada.");
    await loadExceptions();
  } catch (e) { setStatus("excStatus", e.message, true); }
});

async function deleteException(id) {
  try {
    await api(`/team-week-exceptions/${id}`, { method: "DELETE" });
    await loadExceptions();
  } catch (e) { setStatus("excStatus", e.message, true); }
}

qs("btnImportHolidays").addEventListener("click", async () => {
  try {
    const params = new URLSearchParams({
      team_id: val("holidayTeam"), year: val("holidayYear"),
      working_days_per_week: val("holidayWorkDays"),
    });
    setStatus("holidayStatus", "Importando…");
    const data = await api("/team-week-exceptions/import-mexican-holidays?" + params, { method: "POST" });
    const staffing = Math.round(data.holiday_staffing * 100);
    setStatus("holidayStatus", data.holidays_imported > 0
      ? `${data.holidays_imported} semana(s) festiva(s) importada(s) (el equipo opera al ${staffing}% en festivos).`
      : `Sin cambios: el equipo opera al ${staffing}% en festivos, o ya estaban importados.`);
    await loadExceptions();
  } catch (e) { setStatus("holidayStatus", e.message, true); }
});

/* ── Interrupciones aleatorias ────────────────────────────── */

qs("btnGenerateDisruptions")?.addEventListener("click", async () => {
  const done = setLoading("btnGenerateDisruptions", "Generando");
  try {
    const params = new URLSearchParams({
      year: val("distYear"),
      probability: parseFloat(val("distProb")) / 100,
      min_drop: parseFloat(val("distMin")) / 100,
      max_drop: parseFloat(val("distMax")) / 100,
    });
    if (val("distSeed")) params.set("seed", val("distSeed"));
    if (val("distTeam")) params.set("team_id", val("distTeam"));
    setStatus("distStatus", "Generando…");
    const data = await api("/team-week-exceptions/generate-disruptions?" + params, { method: "POST" });
    setStatus("distStatus", `${data.weeks_affected} semana(s) de equipo afectada(s). Los planes ya guardados no cambian solos: pulsa "Replanificar todo".`);
    await loadExceptions();
  } catch (e) { setStatus("distStatus", e.message, true); }
  finally { done(); }
});

qs("btnReplanAll")?.addEventListener("click", async () => {
  const done = setLoading("btnReplanAll", "Replanificando");
  try {
    setStatus("distStatus", "Replanificando…");
    const data = await api("/planning/replan-all", { method: "POST" });
    const n = data.months_replanned.length;
    const failed = data.months_replanned.reduce((sum, m) => sum + (m.orders_failed || 0), 0);
    setStatus("distStatus", n
      ? `Listo. ${n} mes(es) replanificado(s) en orden, cada uno con su criterio.`
        + (failed ? ` ${failed} pedido(s) NO se pudieron planear: revisa Planeación Mensual.` : "")
      : "No hay meses planeados todavía.", failed > 0);
  } catch (e) { setStatus("distStatus", e.message, true); }
  finally { done(); }
});
