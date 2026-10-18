/* ── Equipos ──────────────────────────────────────────────── */

async function loadTeams() {
  const teams = await api("/teams");
  const body = qs("teamsBody");
  body.innerHTML = "";
  teams.forEach(t => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${t.id}</td><td>${t.name}</td><td class="num">${t.sequence_order}</td>
      <td class="num">${t.monthly_capacity}</td><td class="num">${t.weeks_available}</td>
      <td class="num">${t.weekly_capacity}</td><td class="num">${t.efficiency}</td>
      <td class="num">${Math.round(t.holiday_staffing * 100)}%</td>`;
    body.appendChild(tr);
  });
}

qs("btnCreateTeam").addEventListener("click", async () => {
  try {
    const params = new URLSearchParams({
      name: val("teamName"), sequence_order: val("teamSeq"),
      monthly_capacity: val("teamCap"), weeks_available: val("teamWeeks"),
      efficiency: val("teamEff"),
      holiday_staffing: parseFloat(val("teamHoliday") || "0") / 100,
    });
    await api("/teams?" + params, { method: "POST" });
    setStatus("teamStatus", "Equipo creado.");
    await loadTeams();
  } catch (e) { setStatus("teamStatus", e.message, true); }
});
