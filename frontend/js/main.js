/* ── Navigation & view dispatch ───────────────────────────── */

document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    btn.classList.add("active");
    qs("view-" + btn.dataset.view).classList.add("active");
    refresh(btn.dataset.view);
  });
});

async function refresh(view) {
  try {
    if (view === "dashboard") await loadDashboard();
    if (view === "teams") await loadTeams();
    if (view === "orders") { await populateTeamDropdown("orderTeam"); await loadOrders(); }
    if (view === "exceptions") {
      await populateTeamDropdown("excTeam");
      await populateTeamDropdown("holidayTeam");
      await loadExceptions();
    }
    if (view === "calendar") await populateTeamDropdown("calTeam");
    if (view === "requirements") await populateOrderDropdown("reqOrder");
  } catch (e) { console.error(e); }
}

/* ── Initial load ─────────────────────────────────────────── */
refresh("dashboard");
