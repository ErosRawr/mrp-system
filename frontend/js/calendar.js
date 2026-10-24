/* ── Calendario ───────────────────────────────────────────────
   One team, one ISO year, week by week, grouped by month. A week belongs to the
   month of its Thursday (the ISO rule), so every week sits in exactly one month
   and a 53-week year really shows 53 weeks. */

const CAL_MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
const CAL_MONTHS_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const CAL_DAY_MS = 86400000;

const calDay = ms => { const d = new Date(ms); return `${d.getUTCDate()} ${CAL_MONTHS_SHORT[d.getUTCMonth()]}`; };

/* Every week of `year`, with its capacity for the selected team. */
function calBuildWeeks(year, exceptionsByWeek) {
  const weeks = [];
  for (let week = 1; week <= isoWeeksInYear(year); week++) {
    const monday = isoWeekMonday(year, week);
    const exc = exceptionsByWeek[week];
    const mult = exc ? parseFloat(exc.capacity_multiplier) : 1.0;
    weeks.push({
      week, monday, mult,
      pct: Math.round(mult * 100),
      reason: exc?.reason ?? "",
      month: new Date(monday + 3 * CAL_DAY_MS).getUTCMonth(),   // month of the Thursday
      state: mult === 0 ? "off" : mult < 1 ? "reduced" : "full",
      range: `${calDay(monday)} – ${calDay(monday + 6 * CAL_DAY_MS)}`,
    });
  }
  return weeks;
}

function calCell(wk, isCurrent) {
  const title = `Semana ${wk.week} · ${wk.range} · ${wk.pct}% de capacidad` + (wk.reason ? ` · ${wk.reason}` : "");
  return `
    <div class="cal-week ${wk.state}${isCurrent ? " current" : ""}" title="${escapeHtml(title)}">
      <span class="cal-week-num">S${wk.week}</span>
      <span class="cal-week-date">${calDay(wk.monday)}</span>
      <span class="cal-week-pct">${wk.pct}%</span>
      <span class="cal-week-bar"><span style="width:${wk.pct}%"></span></span>
    </div>`;
}

function calStat(value, label, tone) {
  return `<div class="cal-stat ${tone}"><div class="cal-stat-value">${value}</div><div class="cal-stat-label">${label}</div></div>`;
}

function renderCalendar(year, exceptionsByWeek) {
  const weeks = calBuildWeeks(year, exceptionsByWeek);
  const now = isoWeekOfMs(Date.now());

  // Summary
  const count = state => weeks.filter(w => w.state === state).length;
  const avg = weeks.reduce((sum, w) => sum + w.mult, 0) / weeks.length * 100;
  qs("calSummary").innerHTML = `
    <div class="cal-summary">
      ${calStat(weeks.length, `semanas en ${year}`, "")}
      ${calStat(count("full"), "a capacidad completa", "good")}
      ${calStat(count("reduced"), "con capacidad reducida", count("reduced") ? "warn" : "")}
      ${calStat(count("off"), "sin disponibilidad", count("off") ? "danger" : "")}
      ${calStat(avg.toFixed(1) + "%", "capacidad promedio", "")}
    </div>
    <div class="chart-legend cal-legend">
      <span><span class="cal-key full"></span>completa</span>
      <span><span class="cal-key reduced"></span>reducida</span>
      <span><span class="cal-key off"></span>sin disponibilidad</span>
      <span><span class="cal-key current"></span>semana actual</span>
    </div>`;

  // Month blocks
  const byMonth = CAL_MONTHS.map(() => []);
  weeks.forEach(w => byMonth[w.month].push(w));
  qs("calMonths").innerHTML = byMonth.map((list, m) => {
    const monthAvg = list.reduce((sum, w) => sum + w.mult, 0) / list.length * 100;
    const cells = list.map(w => calCell(w, year === now.year && w.week === now.week)).join("");
    return `
      <section class="cal-month">
        <header class="cal-month-head">
          <span class="cal-month-name">${CAL_MONTHS[m]}</span>
          <span class="cal-month-avg${monthAvg < 100 ? " dip" : ""}">${Math.round(monthAvg)}%</span>
        </header>
        <div class="cal-month-weeks">${cells}</div>
      </section>`;
  }).join("");

  // The weeks that are not at full capacity, with their reasons
  const affected = weeks.filter(w => w.state !== "full");
  qs("calExceptions").innerHTML = affected.length ? `
    <div class="cal-section-title">Semanas con capacidad reducida (${affected.length})</div>
    <div class="cal-list">
      ${affected.map(w => `
        <div class="cal-list-row ${w.state}">
          <span class="cal-list-week">S${w.week}</span>
          <span class="cal-list-range">${w.range}</span>
          <span class="cal-list-pct">${w.pct}%</span>
          <span class="cal-list-reason">${w.reason ? escapeHtml(w.reason) : "—"}</span>
        </div>`).join("")}
    </div>` : `
    <div class="cal-section-title">Sin excepciones</div>
    <div class="cal-empty">Este equipo trabaja a capacidad completa durante todo ${year}.</div>`;
}

async function loadCalendar() {
  try {
    const teamId = val("calTeam");
    const year = parseInt(val("calYear"), 10);
    if (!teamId) { setStatus("calStatus", "Selecciona un equipo.", true); return; }
    if (!(year >= 1970 && year <= 2200)) { setStatus("calStatus", "El año debe estar entre 1970 y 2200.", true); return; }
    setStatus("calStatus", "Cargando…");

    const all = await api("/team-week-exceptions");
    const exceptionsByWeek = {};
    all.filter(x => String(x.team_id) === String(teamId) && Number(x.year) === year)
       .forEach(x => { exceptionsByWeek[x.week_number] = x; });

    renderCalendar(year, exceptionsByWeek);
    setStatus("calStatus", "");
  } catch (e) { setStatus("calStatus", e.message, true); }
}

qs("btnLoadCalendar").addEventListener("click", loadCalendar);
qs("calTeam").addEventListener("change", loadCalendar);
qs("calYear").addEventListener("change", loadCalendar);
