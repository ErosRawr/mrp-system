/* ── Ocupación (todos los equipos) ────────────────────────── */

qs("btnGetOccupancy").addEventListener("click", async () => {
  try {
    const year = val("occYear"), month = val("occMonth");
    setStatus("occStatus", "Cargando…");

    const teams = await api("/teams");
    const container = qs("occAllTeams");
    container.innerHTML = "";

    for (const team of teams) {
      const data = await api(`/teams/${team.id}/occupancy?year=${year}&month=${month}`);

      const block = document.createElement("div");
      block.className = "occ-team-block";
      let rowsHtml = "";
      data.weekly_breakdown.forEach(w => {
        const pct = w.occupancy_pct ?? 0;
        const displayPct = Math.min(pct, 100);
        let fillClass = "";
        if (pct > 100) fillClass = "over";
        else if (w.capacity_multiplier < 1) fillClass = "holiday";
        rowsHtml += `
          <div class="occ-bar-row">
            <div class="occ-week-label">SEM ${w.week_number}</div>
            <div class="occ-track"><div class="occ-fill ${fillClass}" style="width:${displayPct}%">${pct}%</div></div>
            <div class="occ-reason">${w.reason ?? ""}</div>
          </div>`;
      });
      block.innerHTML = `
        <div class="occ-team-name">${data.team_name} <span style="color:var(--text-faint); font-weight:400;">— ${data.overall_occupancy_pct ?? "—"}% promedio</span></div>
        ${rowsHtml}`;
      container.appendChild(block);
    }
    setStatus("occStatus", "Listo.");
  } catch (e) { setStatus("occStatus", e.message, true); }
});

