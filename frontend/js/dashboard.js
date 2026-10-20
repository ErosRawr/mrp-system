/* ── Dashboard ────────────────────────────────────────────── */

/* Counts lateness using the backend's lateness_status -- never re-derive it here. */
function countLateness(orders) {
  const planned = orders.filter(o => o.lateness_status);
  const onTime = planned.filter(o => o.lateness_status === "on_time").length;
  const warning = planned.filter(o => o.lateness_status === "warning").length;
  const critical = planned.filter(o => o.lateness_status === "critical").length;
  return { onTime, warning, critical, late: warning + critical };
}

async function loadDashboard() {
  try {
    const year = val("dashYear");
    const month = val("dashMonth");
    setStatus("dashStatus", "Cargando…");

    const [orders, teams, plannedMonths] = await Promise.all([api("/orders"), api("/teams"), api("/planning/months")]);

    // Orders in the selected planning period
    const monthOrders = orders.filter(o =>
      String(o.planning_year) === String(year) && String(o.planning_month) === String(month)
    );

    const isMonthPlanned = plannedMonths.some(p =>
      String(p.planning_year) === String(year) && String(p.planning_month) === String(month)
    );

    const totalOrders = monthOrders.length;
    const totalTonnage = monthOrders.reduce((sum, o) => sum + parseFloat(o.quantity_requested), 0);

    const { onTime, late, critical } = countLateness(monthOrders);

    // Occupancy across all teams for this month
    const occResults = await Promise.all(
      teams.map(t => api(`/teams/${t.id}/occupancy?year=${year}&month=${month}`))
    );

    const avgOccupancies = occResults.map(o => o.overall_occupancy_pct ?? 0);
    const plantAvgOccupancy = avgOccupancies.length
      ? (avgOccupancies.reduce((a, b) => a + b, 0) / avgOccupancies.length).toFixed(1)
      : "—";

    let bottleneck = null;
    occResults.forEach(o => {
      if (!bottleneck || (o.overall_occupancy_pct ?? 0) > (bottleneck.overall_occupancy_pct ?? 0)) {
        bottleneck = o;
      }
    });

    // KPI cards
    const kpis = [
      { label: "Pedidos este mes", value: totalOrders, cls: "" },
      { label: "A tiempo / Atrasados", value: `${onTime} / ${late}`,
        sub: critical > 0 ? `${critical} crítico(s)` : "",
        cls: critical > 0 ? "danger" : (late > 0 ? "warn" : "good") },
      { label: "Ocupación promedio", value: `${plantAvgOccupancy}%`, cls: plantAvgOccupancy > 90 ? "danger" : "" },
      { label: "Cuello de botella", value: bottleneck ? bottleneck.team_name : "—",
        sub: bottleneck ? `${bottleneck.overall_occupancy_pct}% ocupación` : "", cls: "warn" },
      { label: "Tonelaje total", value: totalTonnage.toLocaleString(undefined, {maximumFractionDigits: 0}), sub: "ton solicitadas", cls: "" },
    ];

    const grid = qs("kpiGrid");
    grid.innerHTML = "";
    kpis.forEach(k => {
      const card = document.createElement("div");
      card.className = "kpi-card " + k.cls;
      card.innerHTML = `
        <div class="kpi-label">${k.label}</div>
        <div class="kpi-value">${k.value}</div>
        ${k.sub ? `<div class="kpi-sub">${k.sub}</div>` : ""}`;
      grid.appendChild(card);
    });

    // Per-team occupancy summary. Distinguish an unplanned month from a
    // planned month where a team simply has no work assigned.
    const body = qs("dashOccBody");
    body.innerHTML = "";
    occResults.forEach(o => {
      const weeklyBreakdown = o.weekly_breakdown ?? [];
      const allocatedTonnage = weeklyBreakdown.reduce(
        (sum, week) => sum + Number(week.allocated ?? 0), 0
      );
      const busiestWeek = weeklyBreakdown
        .filter(week => Number(week.allocated ?? 0) > 0)
        .reduce((max, week) =>
          Number(week.occupancy_pct ?? 0) > Number(max?.occupancy_pct ?? -1) ? week : max,
          null
        );

      let occupancyLabel = "Sin planear";
      let busiestWeekLabel = "Sin planear";
      if (isMonthPlanned) {
        occupancyLabel = o.overall_occupancy_pct == null
          ? "Sin datos de capacidad"
          : `${Number(o.overall_occupancy_pct).toFixed(1)}% (${Math.round(allocatedTonnage).toLocaleString()} t asignadas)`;
        busiestWeekLabel = busiestWeek
          ? `Semana ${busiestWeek.week_number} (${busiestWeek.occupancy_pct ?? "—"}%)`
          : "Sin carga asignada";
      }

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${o.team_name}</td>
        <td class="num">${occupancyLabel}</td>
        <td>${busiestWeekLabel}</td>`;
      body.appendChild(tr);
    });

    setStatus("dashStatus", "Listo.");
  } catch (e) { setStatus("dashStatus", e.message, true); }
}

qs("btnLoadDashboard").addEventListener("click", loadDashboard);

/* ── Quarterly view ───────────────────────────────────────── */

const MONTH_NAMES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

async function loadQuarterData(year, quarter) {
  const startMonth = (quarter - 1) * 3 + 1;
  const months = [startMonth, startMonth + 1, startMonth + 2];

  const [allOrders, teams] = await Promise.all([api("/orders"), api("/teams")]);

  const monthlyStats = [];
  for (const month of months) {
    const monthOrders = allOrders.filter(o =>
      String(o.planning_year) === String(year) && String(o.planning_month) === String(month)
    );
    const { onTime, late } = countLateness(monthOrders);

    const occResults = await Promise.all(
      teams.map(t => api(`/teams/${t.id}/occupancy?year=${year}&month=${month}`))
    );
    const occValues = occResults.map(o => o.overall_occupancy_pct ?? 0);
    const avgOcc = occValues.length ? occValues.reduce((a,b) => a+b, 0) / occValues.length : 0;

    monthlyStats.push({ month, onTime, late, avgOcc });
  }
  return monthlyStats;
}

function renderOrdersBarChart(stats, containerId) {
  const width = 520, height = 200, barWidth = 60, gap = 40;
  const maxCount = Math.max(1, ...stats.map(s => s.onTime + s.late));
  const chartHeight = 140;
  const baseY = 160;

  let bars = "";
  stats.forEach((s, i) => {
    const x = 50 + i * (barWidth + gap);
    const onTimeH = (s.onTime / maxCount) * chartHeight;
    const lateH = (s.late / maxCount) * chartHeight;
    const onTimeY = baseY - onTimeH;
    const lateY = onTimeY - lateH;

    bars += `
      <rect x="${x}" y="${onTimeY}" width="${barWidth}" height="${onTimeH}" fill="#5fb87a" />
      <rect x="${x}" y="${lateY}" width="${barWidth}" height="${lateH}" fill="#d9695a" />
      <text x="${x + barWidth/2}" y="${baseY + 20}" text-anchor="middle" fill="#838d94" font-size="11" font-family="ui-monospace, monospace">${MONTH_NAMES[s.month - 1]}</text>
      <text x="${x + barWidth/2}" y="${lateY - 6}" text-anchor="middle" fill="#d7dbde" font-size="11" font-family="ui-monospace, monospace">${s.onTime + s.late}</text>`;
  });

  qs(containerId).innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" style="width:100%; max-width:520px;">
      <line x1="40" y1="${baseY}" x2="${width - 20}" y2="${baseY}" stroke="#262c31" stroke-width="1" />
      ${bars}
    </svg>
    <div class="chart-legend">
      <span><span class="legend-swatch" style="background:#5fb87a;"></span>A tiempo</span>
      <span><span class="legend-swatch" style="background:#d9695a;"></span>Atrasados</span>
    </div>`;
}

function renderOccupancyLineChart(stats, containerId) {
  const width = 520, height = 200;
  const chartTop = 20, chartBottom = 160, chartLeft = 50, chartRight = width - 20;
  const usableWidth = chartRight - chartLeft;

  const points = stats.map((s, i) => {
    const x = chartLeft + (i / (stats.length - 1 || 1)) * usableWidth;
    const y = chartBottom - (Math.min(s.avgOcc, 100) / 100) * (chartBottom - chartTop);
    return { x, y, label: MONTH_NAMES[s.month - 1], value: s.avgOcc.toFixed(1) };
  });

  const pathD = points.map((p, i) => (i === 0 ? "M" : "L") + `${p.x},${p.y}`).join(" ");

  let dots = "";
  points.forEach(p => {
    dots += `
      <circle cx="${p.x}" cy="${p.y}" r="3.5" fill="#4a9eda" />
      <text x="${p.x}" y="${p.y - 10}" text-anchor="middle" fill="#d7dbde" font-size="11" font-family="ui-monospace, monospace">${p.value}%</text>
      <text x="${p.x}" y="${chartBottom + 20}" text-anchor="middle" fill="#838d94" font-size="11" font-family="ui-monospace, monospace">${p.label}</text>`;
  });

  // 100% reference line
  const fullLineY = chartBottom - (chartBottom - chartTop);

  qs(containerId).innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" style="width:100%; max-width:520px;">
      <line x1="${chartLeft}" y1="${chartBottom}" x2="${chartRight}" y2="${chartBottom}" stroke="#262c31" stroke-width="1" />
      <line x1="${chartLeft}" y1="${fullLineY}" x2="${chartRight}" y2="${fullLineY}" stroke="#262c31" stroke-width="1" stroke-dasharray="3,3" />
      <text x="${chartRight}" y="${fullLineY - 4}" text-anchor="end" fill="#5a636a" font-size="10" font-family="ui-monospace, monospace">100%</text>
      <path d="${pathD}" fill="none" stroke="#4a9eda" stroke-width="2" />
      ${dots}
    </svg>`;
}

qs("btnLoadQuarter").addEventListener("click", async () => {
  try {
    const year = val("qYear");
    const quarter = parseInt(val("qQuarter"));
    setStatus("qStatus", "Cargando…");

    const stats = await loadQuarterData(year, quarter);
    renderOrdersBarChart(stats, "qOrdersChart");
    renderOccupancyLineChart(stats, "qOccChart");

    setStatus("qStatus", "Listo.");
  } catch (e) { setStatus("qStatus", e.message, true); }
});