/* ── Disponibilidad ────────────────────────────────────────────
   When each team can work. A year map (team × week) on top, the tools that change
   availability (manual exception, Mexican holidays, random disruptions), and the
   list of what is registered. Availability changes do not move saved plans by
   themselves, so the page says when a replan is needed (and how many weeks of the
   saved plan no longer fit, from GET /availability/overloads). */

const avail = {
  initialized: false,
  teams: [],
  all: [],              // every registered exception, any year
  overloads: [],        // team-weeks of the selected year where the plan no longer fits
  dirty: false,         // availability changed in this session and plans were not rerun
  notice: null,         // { text, tone } result of the last replan
  shown: 20,            // rows of the list currently visible
};

const AVAIL_DAY_MS = 86400000;
const AVAIL_MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const availN = (n, d = 0) => Number(n).toLocaleString("es-MX", { minimumFractionDigits: d, maximumFractionDigits: d });
const availPlural = (n, one, many) => `${availN(n)} ${n === 1 ? one : many}`;
const availYear = () => parseInt(val("availYear"), 10);
const availKey = (teamId, week) => `${teamId}-${week}`;

/* ── Loading ─────────────────────────────────────────────── */

async function loadExceptions() {
  const [teams, all] = await Promise.all([api("/teams"), api("/team-week-exceptions")]);
  avail.teams = teams;
  avail.all = all;

  // The first time, open on the latest year that has anything registered
  if (!avail.initialized) {
    if (all.length) qs("availYear").value = Math.max(...all.map(x => x.year));
    avail.initialized = true;
  }
  const year = availYear();
  if (!(year >= 1970 && year <= 2200)) { setStatus("excStatus", "El año debe estar entre 1970 y 2200.", true); return; }

  avail.overloads = await api(`/availability/overloads?year=${year}`);
  fillAvailSelects();
  renderAvail();
}

function fillAvailSelects() {
  const options = (first) => (first ? `<option value="">${first}</option>` : "") +
    avail.teams.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join("");
  for (const [id, first] of [["excTeam", null], ["holidayTeam", null], ["distTeam", "Todos los equipos"], ["availTeamFilter", "Todos los equipos"]]) {
    const select = qs(id), previous = select.value;
    select.innerHTML = options(first);
    if ([...select.options].some(o => o.value === previous)) select.value = previous;
  }
}

function renderAvail() {
  renderAvailKpis();
  renderAvailBanner();
  renderAvailMap();
  renderAvailList();
  updateAvailHints();
}

/* What this year looks like, for the rows that exist */
function availYearData() {
  const year = availYear();
  const byKey = new Map();
  avail.all.filter(x => x.year === year).forEach(x => byKey.set(availKey(x.team_id, x.week_number), x));
  const over = new Map(avail.overloads.map(o => [availKey(o.team_id, o.week_number), o]));
  return { year, weeks: isoWeeksInYear(year), byKey, over };
}

/* ── Summary cards ───────────────────────────────────────── */

function availCard(label, value, sub, tone = "") {
  return `<article class="avail-kpi ${tone}"><div class="avail-kpi-label">${label}</div>` +
         `<div class="avail-kpi-value">${value}</div><div class="avail-kpi-sub">${sub}</div></article>`;
}

function renderAvailKpis() {
  const { year, weeks, byKey } = availYearData();
  if (!avail.teams.length) {
    qs("availKpis").innerHTML = '<div class="avail-empty">Aún no hay equipos. Créalos en la pestaña Equipos y vuelve aquí para registrar su disponibilidad.</div>';
    return;
  }
  const slots = avail.teams.length * weeks;
  const rows = [...byKey.values()].map(x => ({ ...x, mult: parseFloat(x.capacity_multiplier) }));
  const reduced = rows.filter(x => x.mult < 1), closed = rows.filter(x => x.mult === 0);
  const lost = slots ? rows.reduce((sum, x) => sum + (1 - x.mult), 0) / slots * 100 : 0;
  const over = avail.overloads.length;

  qs("availKpis").innerHTML = `<div class="avail-kpi-grid">
    ${availCard("Semanas con capacidad reducida", availN(reduced.length), `de ${availN(slots)} semanas-equipo de ${year} (${availN(slots ? reduced.length / slots * 100 : 0, 1)}%)`)}
    ${availCard("Semanas cerradas", availN(closed.length), closed.length ? "equipos sin disponibilidad total" : "ningún equipo se detiene por completo", closed.length ? "warn" : "")}
    ${availCard("Capacidad perdida", `${availN(lost, 1)}%`, "promedio de todos los equipos y semanas del año")}
    ${availCard("Plan fuera de disponibilidad", availN(over), over ? `${availPlural(over, "semana-equipo", "semanas-equipo")} con más carga de la que permiten` : "los planes guardados respetan la disponibilidad", over ? "danger" : "good")}
  </div>`;
}

/* ── "Replan" prompt ─────────────────────────────────────── */

function renderAvailBanner() {
  const over = avail.overloads.length;
  let html = "";
  if (avail.notice) {
    html = `<div class="avail-banner ${avail.notice.tone}" role="status"><span>${avail.notice.text}</span></div>`;
  } else if (over || avail.dirty) {
    const text = over
      ? `El plan guardado tiene ${availPlural(over, "semana-equipo", "semanas-equipo")} con más carga de la que permite la disponibilidad actual. Vuelve a ejecutar la planeación para ajustarlo.`
      : "Cambiaste la disponibilidad. Los planes guardados no se actualizan solos: vuelve a ejecutar la planeación para que la usen.";
    html = `<div class="avail-banner warn" role="status"><span>${text}</span>
      <button class="btn" id="btnReplanAll" type="button">Replanificar todo</button></div>`;
  }
  qs("availBanner").innerHTML = html;
}

async function availReplanAll() {
  const done = setLoading("btnReplanAll", "Replanificando");
  try {
    const data = await api("/planning/replan-all", { method: "POST" });
    const months = data.months_replanned.length;
    const failed = data.months_replanned.reduce((sum, m) => sum + (m.orders_failed || 0), 0);
    avail.dirty = false;
    avail.notice = months
      ? { tone: failed ? "bad" : "good", text: `Listo: ${availPlural(months, "mes replanificado", "meses replanificados")}, en orden y cada uno con su criterio.` +
          (failed ? ` ${availPlural(failed, "pedido no se pudo planear", "pedidos no se pudieron planear")}: revisa Planeación mensual.` : "") }
      : { tone: "good", text: "No hay meses planeados todavía, así que no había nada que replanificar." };
    await loadExceptions();
  } catch (e) {
    avail.notice = { tone: "bad", text: `No se pudo replanificar: ${escapeHtml(apiErrorText(e))}` };
    renderAvailBanner();
  } finally { done(); }
}

function availChanged() {          // called after every change to the registered availability
  avail.dirty = true;
  avail.notice = null;
}

/* ── Year map: team × week ───────────────────────────────── */

function renderAvailMap() {
  const { year, weeks, byKey, over } = availYearData();
  if (!avail.teams.length) { qs("availMap").innerHTML = ""; return; }

  // Month labels over the weeks (a week belongs to the month of its Thursday)
  const runs = [];
  for (let w = 1; w <= weeks; w++) {
    const month = new Date(isoWeekMonday(year, w) + 3 * AVAIL_DAY_MS).getUTCMonth();
    if (runs.length && runs[runs.length - 1].month === month) runs[runs.length - 1].len++;
    else runs.push({ month, start: w, len: 1 });
  }
  const head = '<div></div>' + runs.map(r =>
    `<div class="avail-month" style="grid-column:${r.start + 1} / span ${r.len}">${AVAIL_MONTHS[r.month]}</div>`).join("");

  const rows = avail.teams.map(team => {
    let cells = "";
    for (let w = 1; w <= weeks; w++) {
      const exc = byKey.get(availKey(team.id, w));
      const mult = exc ? parseFloat(exc.capacity_multiplier) : 1;
      const state = mult === 0 ? "closed" : mult < 1 ? "reduced" : "full";
      const overloaded = over.has(availKey(team.id, w));
      const label = `${team.name} · semana ${w} (${weekRangeLabel(year, w)}) · ` +
        (mult === 1 ? "capacidad completa" : `${Math.round(mult * 100)}% de capacidad`) +
        (exc && exc.reason ? ` · ${exc.reason}` : "") + (overloaded ? " · el plan guardado tiene más carga de la que permite" : "");
      cells += `<button type="button" class="avail-cell ${state}${overloaded ? " over" : ""}" style="--loss:${(1 - mult).toFixed(2)}"
                  data-team="${team.id}" data-week="${w}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"></button>`;
    }
    return `<div class="avail-team" title="${escapeHtml(team.name)}">${escapeHtml(team.name)}</div>${cells}`;
  }).join("");

  qs("availMap").innerHTML = `
    <div class="avail-map-scroll">
      <div class="avail-map" style="--avail-weeks:${weeks}">${head}${rows}</div>
    </div>
    <div class="chart-legend avail-legend">
      <span><span class="avail-key full"></span>capacidad completa</span>
      <span><span class="avail-key reduced"></span>reducida (más intenso = más pérdida)</span>
      <span><span class="avail-key closed"></span>cerrada</span>
      <span><span class="avail-key over"></span>el plan guardado ya no cabe</span>
    </div>`;
}

/* ── Registered list ─────────────────────────────────────── */

function renderAvailList() {
  const { year, weeks, byKey, over } = availYearData();
  const names = new Map(avail.teams.map(t => [t.id, t]));
  const teamFilter = val("availTeamFilter"), search = val("availSearch").trim().toLocaleLowerCase();

  const rows = [...byKey.values()]
    .filter(x => !teamFilter || String(x.team_id) === teamFilter)
    .filter(x => !search || String(x.reason ?? "").toLocaleLowerCase().includes(search))
    .sort((a, b) => a.week_number - b.week_number || (names.get(a.team_id)?.sequence_order ?? 0) - (names.get(b.team_id)?.sequence_order ?? 0));

  qs("availListCount").textContent = byKey.size
    ? `${availPlural(rows.length, "excepción", "excepciones")} en ${year}` + (rows.length !== byKey.size ? ` (de ${availN(byKey.size)})` : "") + "."
    : `No hay excepciones registradas en ${year}.`;

  const visible = rows.slice(0, avail.shown);
  qs("excBody").innerHTML = visible.length ? visible.map(x => {
    const team = names.get(x.team_id), mult = parseFloat(x.capacity_multiplier), pct = Math.round(mult * 100);
    const state = mult === 0 ? "closed" : "reduced";
    return `<tr data-team="${x.team_id}" data-week="${x.week_number}">
      <td><strong>${escapeHtml(team ? team.name : "Equipo #" + x.team_id)}</strong></td>
      <td>S${x.week_number} <span class="avail-dates">${weekRangeLabel(year, x.week_number)}</span></td>
      <td><div class="avail-capacity"><span class="avail-bar ${state}"><span style="width:${pct}%"></span></span>
          <span class="avail-pct">${pct}%</span></div></td>
      <td>${x.reason ? escapeHtml(x.reason) : '<span class="avail-dates">—</span>'}
          ${over.has(availKey(x.team_id, x.week_number)) ? '<span class="avail-tag" title="El plan guardado tiene más carga de la que permite esta semana">plan fuera de límite</span>' : ""}</td>
      <td class="avail-row-actions">
        <button type="button" class="btn small" data-action="edit" aria-label="Editar la excepción de la semana ${x.week_number}">Editar</button>
        <button type="button" class="btn small danger" data-action="delete" data-id="${x.id}" aria-label="Eliminar la excepción de la semana ${x.week_number}">Eliminar</button>
      </td></tr>`;
  }).join("") : `<tr><td colspan="5" class="avail-none">${byKey.size ? "Ninguna excepción coincide con el filtro." : "Todavía no hay excepciones: todos los equipos trabajan a capacidad completa."}</td></tr>`;

  qs("btnAvailMore").hidden = rows.length <= avail.shown;
  qs("btnAvailMore").textContent = `Mostrar más (${availN(rows.length - avail.shown)} restantes)`;
}

/* ── Form helpers ────────────────────────────────────────── */

function availSelectTab(name) {
  document.querySelectorAll("[data-avail-tab]").forEach(tab => {
    const active = tab.dataset.availTab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-avail-panel]").forEach(panel => { panel.hidden = panel.dataset.availPanel !== name; });
}

function updateAvailHints() {
  // Which week is this?
  const year = availYear(), week = parseInt(val("excWeek"), 10), weeks = isoWeeksInYear(year);
  const hint = qs("excWeekHint");
  if (!val("excWeek")) hint.textContent = "Número de semana ISO del año.";
  else if (!(week >= 1 && week <= weeks)) hint.textContent = `${year} tiene ${weeks} semanas.`;
  else hint.textContent = `Semana ${week}: ${weekRangeLabel(year, week)} de ${year}.`;

  // What would a holiday cost this team?
  const team = avail.teams.find(t => String(t.id) === val("holidayTeam"));
  const days = parseInt(val("holidayWorkDays"), 10);
  const note = qs("holidayHint");
  if (!team || !(days >= 1 && days <= 7)) { note.textContent = ""; return; }
  const staffing = Number(team.holiday_staffing), cost = (1 / days) * (1 - staffing) * 100;
  note.textContent = staffing >= 1
    ? `${team.name} opera con normalidad en festivos: no se registraría ninguna reducción.`
    : `${team.name} ${staffing <= 0 ? "se detiene" : `opera con ${Math.round(staffing * 100)}% de su plantilla`} en festivos: cada festivo le quitaría ${availN(cost, 1)}% de la semana (1 de ${days} días).`;
}

/* Fill the manual form from a map cell or a list row */
function availPrefill(teamId, week) {
  const exc = availYearData().byKey.get(availKey(teamId, week));
  availSelectTab("manual");
  qs("excTeam").value = teamId;
  qs("excWeek").value = week;
  qs("excPct").value = exc ? Math.round(parseFloat(exc.capacity_multiplier) * 100) : 80;
  qs("excReason").value = exc && exc.reason ? exc.reason : "";
  updateAvailHints();
  setStatus("excStatus", exc ? "Esta semana ya tiene una excepción: al guardar se reemplaza." : "Semana sin excepción: indica cuánta capacidad queda.");
  qs("availTools").scrollIntoView?.({ behavior: "smooth", block: "center" });
  qs("excPct").focus();
}

async function availRun(button, statusId, loadingText, action) {
  const done = setLoading(button, loadingText);
  try { await action(); }
  catch (e) { setStatus(statusId, apiErrorText(e), true); }
  finally { done(); }
}

/* ── Actions ─────────────────────────────────────────────── */

qs("btnSetExc").addEventListener("click", () => {
  const year = availYear(), weeks = isoWeeksInYear(year);
  const week = parseInt(val("excWeek"), 10), pct = parseFloat(val("excPct"));
  if (!val("excTeam")) return setStatus("excStatus", "Elige un equipo.", true);
  if (!(week >= 1 && week <= weeks)) return setStatus("excStatus", `Indica una semana entre 1 y ${weeks} (${year} tiene ${weeks}).`, true);
  if (!(pct >= 0 && pct <= 100)) return setStatus("excStatus", "La capacidad disponible va de 0% (cerrado) a 100% (completa).", true);

  availRun("btnSetExc", "excStatus", "Guardando", async () => {
    const params = new URLSearchParams({ team_id: val("excTeam"), year, week_number: week, capacity_multiplier: pct / 100 });
    if (val("excReason").trim()) params.set("reason", val("excReason").trim());
    await api("/team-week-exceptions?" + params, { method: "POST" });
    setStatus("excStatus", `Excepción guardada: semana ${week} al ${Math.round(pct)}%.`);
    availChanged();
    await loadExceptions();
  });
});

qs("btnImportHolidays").addEventListener("click", () => {
  if (!val("holidayTeam")) return setStatus("holidayStatus", "Elige un equipo.", true);
  availRun("btnImportHolidays", "holidayStatus", "Importando", async () => {
    const params = new URLSearchParams({ team_id: val("holidayTeam"), year: availYear(), working_days_per_week: val("holidayWorkDays") });
    const data = await api("/team-week-exceptions/import-mexican-holidays?" + params, { method: "POST" });
    const staffing = Math.round(data.holiday_staffing * 100);
    setStatus("holidayStatus", data.holidays_imported > 0
      ? `${availPlural(data.holidays_imported, "semana festiva importada", "semanas festivas importadas")} (el equipo opera al ${staffing}% en festivos).`
      : `Sin cambios: el equipo opera al ${staffing}% en festivos, o ya estaban importados.`);
    if (data.holidays_imported > 0) availChanged();
    await loadExceptions();
  });
});

qs("btnGenerateDisruptions").addEventListener("click", () => {
  const prob = parseFloat(val("distProb")), min = parseFloat(val("distMin")), max = parseFloat(val("distMax"));
  if (!(prob >= 0 && prob <= 100)) return setStatus("distStatus", "La probabilidad va de 0% a 100%.", true);
  if (!(min > 0 && max >= min && max <= 100)) return setStatus("distStatus", "La baja mínima debe ser mayor que 0 y no mayor que la máxima (máximo 100%).", true);

  availRun("btnGenerateDisruptions", "distStatus", "Generando", async () => {
    const params = new URLSearchParams({ year: availYear(), probability: prob / 100, min_drop: min / 100, max_drop: max / 100 });
    if (val("distSeed") !== "") params.set("seed", val("distSeed"));
    if (val("distTeam")) params.set("team_id", val("distTeam"));
    const data = await api("/team-week-exceptions/generate-disruptions?" + params, { method: "POST" });
    setStatus("distStatus", data.weeks_affected
      ? `${availPlural(data.weeks_affected, "semana-equipo afectada", "semanas-equipo afectadas")}.`
      : "Sin cambios: ninguna semana nueva resultó afectada (con la misma semilla salen las mismas semanas).");
    if (data.weeks_affected) availChanged();
    await loadExceptions();
  });
});

async function availDelete(id) {
  try {
    await api(`/team-week-exceptions/${id}`, { method: "DELETE" });
    availChanged();
    await loadExceptions();
  } catch (e) { setStatus("excStatus", apiErrorText(e), true); }
}

/* ── Wiring ──────────────────────────────────────────────── */

document.querySelectorAll("[data-avail-tab]").forEach(tab => tab.addEventListener("click", () => availSelectTab(tab.dataset.availTab)));
document.querySelectorAll(".avail-preset").forEach(b => b.addEventListener("click", () => { qs("excPct").value = b.dataset.pct; }));

qs("availBanner").addEventListener("click", e => { if (e.target.closest("#btnReplanAll")) availReplanAll(); });

qs("availMap").addEventListener("click", e => {
  const cell = e.target.closest(".avail-cell");
  if (cell) availPrefill(Number(cell.dataset.team), Number(cell.dataset.week));
});

qs("excBody").addEventListener("click", e => {
  const button = e.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "delete") availDelete(Number(button.dataset.id));
  else { const row = button.closest("tr"); availPrefill(Number(row.dataset.team), Number(row.dataset.week)); }
});

qs("availYear").addEventListener("change", () => { avail.shown = 20; loadExceptions().catch(e => setStatus("excStatus", apiErrorText(e), true)); });
qs("btnAvailPrev").addEventListener("click", () => { qs("availYear").value = availYear() - 1; qs("availYear").dispatchEvent(new Event("change")); });
qs("btnAvailNext").addEventListener("click", () => { qs("availYear").value = availYear() + 1; qs("availYear").dispatchEvent(new Event("change")); });

for (const id of ["availTeamFilter", "availSearch"]) {
  qs(id).addEventListener("input", () => { avail.shown = 20; renderAvailList(); });
}
qs("btnAvailMore").addEventListener("click", () => { avail.shown += 20; renderAvailList(); });
for (const id of ["excWeek", "holidayTeam", "holidayWorkDays"]) qs(id).addEventListener("input", updateAvailHints);
