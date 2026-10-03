/* ── Pedidos ──────────────────────────────────────────────── */

let editingOrderId = null;

function closeAllRowMenus() {
  document.querySelectorAll(".row-menu.open").forEach(m => m.classList.remove("open"));
}

function toggleOrderMenu(event, orderId) {
  event.stopPropagation();
  const menu = qs(`menu-order-${orderId}`);
  const wasOpen = menu.classList.contains("open");
  closeAllRowMenus();
  if (!wasOpen) menu.classList.add("open");
}

document.addEventListener("click", closeAllRowMenus);

async function loadOrders() {
  const orders = await api("/orders");
  const body = qs("ordersBody");
  body.innerHTML = "";
  orders.forEach(o => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${o.id}</td><td>${o.customer_name}</td><td class="num">${o.quantity_requested}</td>
      <td class="num">${o.entry_team_id}</td><td>${o.order_date}</td>
      <td>${o.requested_delivery_date ?? "—"}</td>
      <td>${o.tipo_pedido ?? "—"}</td>
      <td>${o.is_priority ? '<span class="warn-text">★</span>' : "—"}</td>
      <td>${o.planning_year}-${String(o.planning_month).padStart(2,"0")}</td>
      <td>${o.calculated_delivery_date ?? "—"}</td>
      <td style="position:relative;">
        <button class="btn small menu-trigger" onclick="toggleOrderMenu(event, ${o.id})">⋯</button>
        <div class="row-menu" id="menu-order-${o.id}">
          <button onclick="startEditOrder(${o.id}); closeAllRowMenus();">Editar</button>
          <button class="danger" onclick="deleteOrderRow(${o.id}); closeAllRowMenus();">Eliminar</button>
        </div>
      </td>`;
    body.appendChild(tr);
  });
}

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

