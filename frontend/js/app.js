/* ── App bootstrap ────────────────────────────────────────────
   Loads view HTML fragments, THEN loads each view's script (so their
   top-level qs("...").addEventListener() calls find real elements),
   THEN wires up navigation and does the initial refresh.

   This ordering is the whole reason this file exists as a module:
   plain <script> tags all run immediately in document order, but the
   view-specific scripts need the view HTML to exist first, and that
   HTML now loads asynchronously via fetch(). */

const VIEW_FILES = [
  "dashboard", "teams", "orders", "exceptions",
  "calendar", "requirements", "planning", "heuristica", "occupancy",
];

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.body.appendChild(s);
  });
}

async function bootstrap() {
  // 1. Fetch and inject all view HTML fragments
  const fragments = await Promise.all(
    VIEW_FILES.map(name => fetch(`views/${name}.html`).then(r => r.text()))
  );
  document.getElementById("mainContent").innerHTML = fragments.join("\n");

  // 2. Now load each view's script -- their qs(...) calls will find
  //    real elements since the HTML above is already in the DOM.
  for (const name of VIEW_FILES) {
    await loadScript(`js/${name}.js`);
  }

  // 3. Wire up navigation (same logic that used to live in main.js)
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("view-" + btn.dataset.view).classList.add("active");
      refresh(btn.dataset.view);
    });
  });

  // 4. Initial load
  refresh("dashboard");
}

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

bootstrap();
