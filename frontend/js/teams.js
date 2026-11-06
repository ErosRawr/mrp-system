/* ── Equipos ───────────────────────────────────────────────────
   The production route, stage by stage. Everything shown comes from GET /route:
   the capacities and efficiencies as configured, plus what they add up to
   (the bottleneck, the plant's real weekly output, the route's overall yield). */

const teamState = { autoSequence: null };

const teamNum = (n, digits = 0) => (n === null || n === undefined) ? "—"
  : Number(n).toLocaleString("es-MX", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/* Same colors as Ocupación and the Dashboard: how busy would this stage be? */
function teamLevel(pct) {
  if (pct >= 99.95) return "full";
  if (pct >= 85) return "high";
  if (pct >= 50) return "ok";
  return "low";
}

function teamHoliday(share) {
  if (share <= 0) return { text: "Se detiene", cls: "stop" };
  if (share >= 1) return { text: "Opera normal", cls: "run" };
  return { text: `Plantilla reducida (${Math.round(share * 100)}%)`, cls: "partial" };
}

async function loadTeams() {
  const route = await api("/route");
  renderTeamsKpis(route);
  renderTeamsRoute(route);
  renderTeamsTable(route);

  // Propose the next stage in the form, unless the user typed something else
  const next = route.teams.length ? Math.max(...route.teams.map(t => t.sequence_order)) + 1 : 1;
  const field = qs("teamSeq");
  if (field.value === "" || field.value === String(teamState.autoSequence)) field.value = next;
  teamState.autoSequence = next;
}

/* ── Summary cards ───────────────────────────────────────── */

function teamCard(label, value, sub, tone = "") {
  return `<article class="teams-kpi ${tone}"><div class="teams-kpi-label">${label}</div>` +
         `<div class="teams-kpi-value">${value}</div><div class="teams-kpi-sub">${sub}</div></article>`;
}

function renderTeamsKpis(route) {
  const empty = !route.teams.length;
  qs("teamsRouteSection").style.display = empty ? "none" : "";
  qs("teamsListSection").style.display = empty ? "none" : "";
  if (empty) {
    qs("teamsKpis").innerHTML = '<div class="teams-empty">Aún no hay equipos. Agrega el primero abajo: cada equipo es una etapa de la ruta, de la materia prima al producto terminado.</div>';
    return;
  }

  const stages = route.teams, last = stages[stages.length - 1];
  const bottleneck = stages.find(t => t.is_bottleneck);
  qs("teamsKpis").innerHTML = `<div class="teams-kpi-grid">
    ${teamCard("Etapas en la ruta", teamNum(stages.length), `de ${escapeHtml(stages[0].team_name)} a ${escapeHtml(last.team_name)}`)}
    ${teamCard("Capacidad real de la planta", `${teamNum(route.finished_capacity_week)} t`, `de producto terminado por semana · ≈ ${teamNum(route.finished_capacity_month)} t al mes`, "good")}
    ${teamCard("Cuello de botella", escapeHtml(bottleneck.team_name), `${teamNum(bottleneck.weekly_capacity)} t por semana: la etapa que limita a la planta`, "warn")}
    ${teamCard("Rendimiento global", `${teamNum(route.overall_yield * 100, 1)}%`, `${teamNum(route.raw_per_100_t, 1)} t de materia prima por cada 100 t terminadas`)}
  </div>`;
}

/* ── The route as a flow ─────────────────────────────────── */

function renderTeamsRoute(route) {
  if (!route.teams.length) { qs("teamsRoute").innerHTML = ""; return; }
  const arrow = '<div class="route-arrow" aria-hidden="true"></div>';

  const stages = route.teams.map(t => {
    const holiday = teamHoliday(t.holiday_staffing);
    const scrap = (1 - t.efficiency) * 100;
    return `
      <article class="route-stage${t.is_bottleneck ? " bottleneck" : ""} lvl-${teamLevel(t.load_at_full_rate_pct)}"
               aria-label="Etapa ${t.sequence_order}: ${escapeHtml(t.team_name)}">
        ${t.is_bottleneck ? '<span class="route-badge route-badge-tag">Cuello de botella</span>' : ""}
        <header class="route-stage-head">
          <span class="route-step">${t.sequence_order}</span>
          <strong class="route-name">${escapeHtml(t.team_name)}</strong>
        </header>
        <div class="route-capacity">${teamNum(t.weekly_capacity)} <small>t/sem</small></div>
        <dl class="route-facts">
          <div><dt>Rendimiento</dt><dd>${teamNum(t.efficiency * 100, 1)}% <span class="route-scrap">(descarta ${teamNum(scrap, 1)}%)</span></dd></div>
          <div><dt>En festivos</dt><dd><span class="route-chip ${holiday.cls}">${holiday.text}</span></dd></div>
        </dl>
        <div class="route-load" title="Cuánto se usaría este equipo mientras el cuello de botella trabaja a su máximo">
          <div class="route-load-label"><span>Uso a ritmo máximo</span><strong>${teamNum(t.load_at_full_rate_pct, 0)}%</strong></div>
          <div class="route-load-track"><span style="width:${Math.min(t.load_at_full_rate_pct, 100)}%"></span></div>
        </div>
      </article>`;
  }).join(arrow);

  const lost = 100 - route.overall_yield * 100;
  qs("teamsRoute").innerHTML = `
    <div class="route-strip">
      <div class="route-strip-end"><span>Entra</span><strong>${teamNum(route.raw_per_100_t, 1)} t</strong><span>de materia prima</span></div>
      <div class="route-strip-line"><span>${stagesLabel(route.teams.length)}, se descarta ${teamNum(lost, 1)}% del material</span></div>
      <div class="route-strip-end finished"><span>Sale</span><strong>100 t</strong><span>de producto terminado</span></div>
    </div>
    <div class="route-stages">${stages}</div>`;
}

const stagesLabel = n => n === 1 ? "Pasa por 1 etapa" : `Pasa por ${n} etapas`;

/* ── Configuration table ─────────────────────────────────── */

function renderTeamsTable(route) {
  const widest = Math.max(1, ...route.teams.map(t => t.weekly_capacity));
  qs("teamsBody").innerHTML = route.teams.map(t => {
    const holiday = teamHoliday(t.holiday_staffing);
    return `
      <tr class="${t.is_bottleneck ? "is-bottleneck" : ""}">
        <td class="center">${t.sequence_order}</td>
        <td><strong>${escapeHtml(t.team_name)}</strong> <span class="teams-id">#${t.team_id}</span>
            ${t.is_bottleneck ? '<span class="route-badge">Cuello de botella</span>' : ""}</td>
        <td class="num">${teamNum(t.monthly_capacity)} t</td>
        <td class="num">${t.weeks_available}</td>
        <td><div class="teams-bar-cell"><span class="teams-bar"><span style="width:${(t.weekly_capacity / widest * 100).toFixed(1)}%"></span></span>
            <span class="teams-bar-value">${teamNum(t.weekly_capacity)} t</span></div></td>
        <td class="num">${teamNum(t.efficiency * 100, 1)}%</td>
        <td><span class="route-chip ${holiday.cls}">${holiday.text}</span></td>
        <td class="num">${teamNum(t.finished_capacity_week)} t</td>
      </tr>`;
  }).join("");
}

/* ── Adding a team ───────────────────────────────────────── */

function teamFormProblem() {
  if (!val("teamName").trim()) return "Escribe el nombre del equipo.";
  if (!val("teamSeq")) return "Indica el orden del equipo en la ruta.";
  if (!(parseFloat(val("teamCap")) > 0)) return "Indica la capacidad mensual (mayor que 0).";
  return null;
}

/* The API answers 400: {"detail": "..."}; show just the sentence. */
function teamErrorText(error) {
  const match = String(error.message).match(/^\d+: ([\s\S]*)$/);
  try {
    const detail = JSON.parse(match[1]).detail;
    if (typeof detail === "string") return detail;
  } catch (_) { /* not JSON: fall through */ }
  return error.message;
}

qs("btnCreateTeam").addEventListener("click", async () => {
  const problem = teamFormProblem();
  if (problem) { setStatus("teamStatus", problem, true); return; }
  const done = setLoading("btnCreateTeam", "Agregando");
  try {
    const params = new URLSearchParams({
      name: val("teamName"), sequence_order: val("teamSeq"),
      monthly_capacity: val("teamCap"), weeks_available: val("teamWeeks"),
      efficiency: val("teamEff"),
      holiday_staffing: parseFloat(val("teamHoliday") || "0") / 100,
    });
    await api("/teams?" + params, { method: "POST" });
    setStatus("teamStatus", "Equipo agregado. Los planes ya guardados no cambian solos: vuelve a ejecutar la planeación de los meses que lo necesiten.");
    qs("teamName").value = "";
    qs("teamCap").value = "";
    qs("teamWeeks").value = 4;
    qs("teamEff").value = 0.95;
    qs("teamHoliday").value = 0;
    qs("teamSeq").value = "";
    await loadTeams();
  } catch (e) { setStatus("teamStatus", teamErrorText(e), true); }
  finally { done(); }
});
