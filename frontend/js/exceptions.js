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
    setStatus("holidayStatus", `${data.holidays_imported} semana(s) festiva(s) importada(s).`);
    await loadExceptions();
  } catch (e) { setStatus("holidayStatus", e.message, true); }
});

