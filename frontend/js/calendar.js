/* ── Calendario ───────────────────────────────────────────── */

qs("btnLoadCalendar").addEventListener("click", async () => {
  try {
    const teamId = val("calTeam");
    const year = val("calYear");
    if (!teamId) { setStatus("calStatus", "Selecciona un equipo.", true); return; }
    setStatus("calStatus", "Cargando…");

    const allExceptions = await api("/team-week-exceptions");
    const teamExceptions = {};
    allExceptions
      .filter(x => String(x.team_id) === String(teamId) && String(x.year) === String(year))
      .forEach(x => { teamExceptions[x.week_number] = x; });

    const grid = qs("calGrid");
    grid.innerHTML = "";
    for (let week = 1; week <= 52; week++) {
      const exc = teamExceptions[week];
      const mult = exc ? parseFloat(exc.capacity_multiplier) : 1.0;
      const pct = Math.round(mult * 100);
      let cls = "full";
      if (mult === 0) cls = "off";
      else if (mult < 1) cls = "reduced";

      const cell = document.createElement("div");
      cell.className = "cal-week " + cls;
      cell.innerHTML = `
        <div class="cal-week-num">SEM ${week}</div>
        <div class="cal-week-pct">${pct}%</div>
        <div class="cal-week-reason">${exc?.reason ?? ""}</div>`;
      grid.appendChild(cell);
    }
    setStatus("calStatus", "Listo.");
  } catch (e) { setStatus("calStatus", e.message, true); }
});

