/* ── Pedidos ──────────────────────────────────────────────── */

let editingOrderId = null;

const orderState = {
  orders: [],
  teamNames: {},
  sortKey: "order_date",
  sortDir: "asc",
  page: 1,
  pageSize: 25,
};

const ORDER_MONTHS = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function closeAllRowMenus() {
  document.querySelectorAll(".row-menu.open").forEach(menu => menu.classList.remove("open"));
  document.querySelectorAll(".menu-trigger[aria-expanded='true']").forEach(button => button.setAttribute("aria-expanded", "false"));
}

function toggleOrderMenu(event, orderId) {
  event.stopPropagation();
  const menu = qs(`menu-order-${orderId}`);
  if (!menu) return;
  const wasOpen = menu.classList.contains("open");
  closeAllRowMenus();
  if (!wasOpen) menu.classList.add("open");
  event.currentTarget.setAttribute("aria-expanded", String(!wasOpen));
}

document.addEventListener("click", closeAllRowMenus);

function escapeOrderHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function getFilteredSortedOrders() {
  const year = val("fYear").trim();
  const month = val("fMonth");
  const query = val("fSearch").trim().toLocaleLowerCase();
  const type = val("fTipo");
  const status = val("fStatus");
  const priorityOnly = qs("fPriority").checked;

  const rows = orderState.orders.filter(order =>
    (!year || String(order.planning_year) === year) &&
    (!month || String(order.planning_month) === month) &&
    (!query || String(order.customer_name ?? "").toLocaleLowerCase().includes(query)) &&
    (!type || order.tipo_pedido === type) &&
    (!priorityOnly || Boolean(order.is_priority)) &&
    (!status || (status === "unplanned"
      ? !order.calculated_delivery_date
      : order.lateness_status === status))
  );

  const { sortKey, sortDir } = orderState;
  rows.sort((left, right) => {
    const a = orderSortValue(left, sortKey);
    const b = orderSortValue(right, sortKey);
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;

    let comparison;
    if (typeof a === "string" && typeof b === "string") {
      comparison = a.localeCompare(b, "es", { numeric: true, sensitivity: "base" });
    } else {
      comparison = a > b ? 1 : a < b ? -1 : 0;
    }
    return comparison * (sortDir === "asc" ? 1 : -1);
  });
  return rows;
}

function orderSortValue(order, key) {
  if (key === "period") return Number(order.planning_year) * 100 + Number(order.planning_month);
  if (key === "team_name") return order.team_name ?? "";
  if (key === "quantity_requested") return Number(order.quantity_requested);
  if (key === "days_late") return order.calculated_delivery_date == null || order.days_late == null ? null : Number(order.days_late);
  if (key === "is_priority") return Boolean(order.is_priority);
  return order[key] ?? null;
}

function orderStatusMarkup(order) {
  if (!order.calculated_delivery_date) {
    return '<span class="orders-status-unplanned">Sin planear</span>';
  }
  const days = Number(order.days_late) || 0;
  const suffix = days > 0 ? ` +${days} d` : "";
  if (order.lateness_status === "critical") return `<span class="danger-text">🔴 Crítico${suffix}</span>`;
  if (order.lateness_status === "warning") return `<span class="warn-text">🟡 Atrasado${suffix}</span>`;
  if (order.lateness_status === "on_time") return '<span class="highlight">🟢 A tiempo</span>';
  return "—";
}

async function loadOrders() {
  const [orders, teams] = await Promise.all([
    api("/orders"),
    api("/teams").catch(() => []),
  ]);
  orderState.teamNames = Object.fromEntries(teams.map(team => [team.id, team.name]));
  orderState.orders = orders.map(order => ({
    ...order,
    team_name: orderState.teamNames[order.entry_team_id] ?? `#${order.entry_team_id}`,
  }));
  renderOrders();
}

function renderOrders() {
  const rows = getFilteredSortedOrders();
  const pages = Math.max(1, Math.ceil(rows.length / orderState.pageSize));
  orderState.page = Math.min(Math.max(orderState.page, 1), pages);
  const start = (orderState.page - 1) * orderState.pageSize;
  const pageRows = rows.slice(start, start + orderState.pageSize);
  const tons = rows.reduce((sum, order) => sum + (Number(order.quantity_requested) || 0), 0);
  const lateCount = rows.filter(order => ["warning", "critical"].includes(order.lateness_status)).length;

  qs("ordersSummary").textContent =
    `${rows.length.toLocaleString("es-MX")} pedidos · ${tons.toLocaleString("es-MX", { maximumFractionDigits: 0 })} ton · ${lateCount.toLocaleString("es-MX")} atrasados`;

  const body = qs("ordersBody");
  body.innerHTML = "";
  if (!pageRows.length) {
    body.innerHTML = '<tr><td class="orders-empty" colspan="12">No hay pedidos que coincidan con estos filtros.</td></tr>';
  } else {
    pageRows.forEach(order => {
      const id = Number(order.id);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeOrderHTML(order.id)}</td>
        <td>${escapeOrderHTML(order.customer_name)}</td>
        <td class="num">${escapeOrderHTML(order.quantity_requested)}</td>
        <td>${escapeOrderHTML(order.team_name)}</td>
        <td>${escapeOrderHTML(order.order_date)}</td>
        <td>${escapeOrderHTML(order.requested_delivery_date ?? "—")}</td>
        <td>${escapeOrderHTML(order.tipo_pedido ?? "—")}</td>
        <td>${order.is_priority ? '<span class="warn-text">★</span>' : "—"}</td>
        <td>${escapeOrderHTML(order.planning_year)}-${String(order.planning_month).padStart(2, "0")}</td>
        <td>${escapeOrderHTML(order.calculated_delivery_date ?? "—")}</td>
        <td>${orderStatusMarkup(order)}</td>
        <td class="orders-actions-cell">
          <button type="button" class="btn small menu-trigger" aria-label="Acciones del pedido ${id}" aria-expanded="false" aria-controls="menu-order-${id}" title="Editar o eliminar pedido" onclick="toggleOrderMenu(event, ${id})">⋯</button>
          <div class="row-menu" id="menu-order-${id}">
            <button type="button" onclick="startEditOrder(${id}); closeAllRowMenus();">Editar</button>
            <button type="button" class="danger" onclick="deleteOrderRow(${id}); closeAllRowMenus();">Eliminar</button>
          </div>
        </td>`;
      body.appendChild(tr);
    });
  }

  qs("pageInfo").textContent = `Página ${orderState.page} de ${pages}`;
  qs("btnPrevPage").disabled = orderState.page <= 1;
  qs("btnNextPage").disabled = orderState.page >= pages;

  document.querySelectorAll("#view-orders th[data-sort]").forEach(th => {
    if (!th.dataset.sortLabel) th.dataset.sortLabel = th.textContent.trim();
    const active = th.dataset.sort === orderState.sortKey;
    th.textContent = th.dataset.sortLabel + (active ? (orderState.sortDir === "asc" ? " ▲" : " ▼") : "");
    th.setAttribute("aria-sort", active ? (orderState.sortDir === "asc" ? "ascending" : "descending") : "none");
  });
}

for (let month = 1; month <= 12; month++) {
  const option = document.createElement("option");
  option.value = String(month);
  option.textContent = ORDER_MONTHS[month - 1];
  qs("fMonth").appendChild(option);
}

["fYear", "fMonth", "fSearch", "fTipo", "fStatus", "fPriority"].forEach(id => {
  const control = qs(id);
  const applyFilter = () => { orderState.page = 1; renderOrders(); };
  control.addEventListener("input", applyFilter);
  control.addEventListener("change", applyFilter);
});

function updateOrderSort(header) {
  const key = header.dataset.sort;
  orderState.sortDir = orderState.sortKey === key && orderState.sortDir === "asc" ? "desc" : "asc";
  orderState.sortKey = key;
  renderOrders();
}

document.querySelectorAll("#view-orders th[data-sort]").forEach(header => {
  header.addEventListener("click", () => updateOrderSort(header));
  header.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      updateOrderSort(header);
    }
  });
});

qs("btnPrevPage").addEventListener("click", () => {
  if (orderState.page > 1) { orderState.page--; renderOrders(); }
});
qs("btnNextPage").addEventListener("click", () => {
  const pages = Math.max(1, Math.ceil(getFilteredSortedOrders().length / orderState.pageSize));
  if (orderState.page < pages) { orderState.page++; renderOrders(); }
});

function startEditOrder(orderId) {
  api(`/orders`).then(orders => {
    const order = orders.find(o => o.id === orderId);
    if (!order) return;

    editingOrderId = orderId;
    qs("orderFormTitle").textContent = `Editando pedido #${orderId}`;
    qs("orderCust").value = order.customer_name;
    qs("orderQty").value = order.quantity_requested;
    qs("orderTeam").value = order.entry_team_id;
    qs("orderDate").value = order.order_date;
    qs("orderReqDate").value = order.requested_delivery_date ?? "";
    qs("orderTipo").value = order.tipo_pedido ?? "";
    qs("orderPriority").checked = !!order.is_priority;
    qs("btnCreateOrder").textContent = "Guardar cambios";
    qs("btnCancelEditOrder").style.display = "inline-block";

    if (order.calculated_delivery_date) {
      setStatus("orderStatus", "Nota: este pedido ya fue planeado -- guardar cambios borrará su fecha calculada y requerirá volver a ejecutar la planeación.");
    }
  });
}

function cancelEditOrder() {
  editingOrderId = null;
  qs("orderFormTitle").textContent = "Nuevo pedido";
  qs("orderCust").value = "";
  qs("orderQty").value = "";
  qs("orderDate").value = "";
  qs("orderReqDate").value = "";
  qs("orderTipo").value = "";
  qs("orderPriority").checked = false;
  qs("btnCreateOrder").textContent = "Crear";
  qs("btnCancelEditOrder").style.display = "none";
  setStatus("orderStatus", "");
}

async function deleteOrderRow(orderId) {
  try {
    await api(`/orders/${orderId}`, { method: "DELETE" });
    setStatus("orderStatus", `Pedido #${orderId} eliminado.`);
    if (editingOrderId === orderId) cancelEditOrder();
    await loadOrders();
  } catch (e) { setStatus("orderStatus", e.message, true); }
}

qs("btnCancelEditOrder").addEventListener("click", cancelEditOrder);

qs("btnCreateOrder").addEventListener("click", async () => {
  try {
    const params = new URLSearchParams({
      customer_name: val("orderCust"), quantity_requested: val("orderQty"),
      entry_team_id: val("orderTeam"), order_date: val("orderDate"),
      is_priority: qs("orderPriority").checked,
    });
    const reqDate = val("orderReqDate");
    if (reqDate) params.set("requested_delivery_date", reqDate);
    const tipo = val("orderTipo");
    if (tipo) params.set("tipo_pedido", tipo);

    if (editingOrderId) {
      await api(`/orders/${editingOrderId}?` + params, { method: "PUT" });
      setStatus("orderStatus", `Pedido #${editingOrderId} actualizado.`);
      cancelEditOrder();
    } else {
      await api("/orders?" + params, { method: "POST" });
      setStatus("orderStatus", "Pedido creado.");
    }
    await loadOrders();
  } catch (e) { setStatus("orderStatus", e.message, true); }
});