/**
 * Hestia Eats — Hono/Node.js demo with injected unbounded fetchAll bug.
 *
 * BUG: GET /api/orders/history loads ALL orders into memory with no LIMIT.
 * Under concurrent load with a large dataset, this causes memory exhaustion
 * and slow responses as the in-memory array grows unbounded.
 */
const { Hono } = require("hono");
const { serve } = require("@hono/node-server");

const app = new Hono();
const VALID_TOKEN = "test-token-hestia";

// ── In-memory data store ──
const restaurants = [
  { id: 1, name: "Olympus Grill", cuisine: "Greek", rating: 4.8, delivery_time: 30 },
  { id: 2, name: "Athena's Kitchen", cuisine: "Mediterranean", rating: 4.5, delivery_time: 25 },
  { id: 3, name: "Hermes Express", cuisine: "Fast Food", rating: 4.2, delivery_time: 15 },
  { id: 4, name: "Poseidon Seafood", cuisine: "Seafood", rating: 4.7, delivery_time: 40 },
  { id: 5, name: "Apollo Bakery", cuisine: "Bakery", rating: 4.9, delivery_time: 20 },
];

const menuItems = [
  { id: 1, restaurant_id: 1, name: "Souvlaki", price: 12.99, category: "Main" },
  { id: 2, restaurant_id: 1, name: "Tzatziki", price: 4.99, category: "Side" },
  { id: 3, restaurant_id: 2, name: "Hummus Plate", price: 8.99, category: "Starter" },
  { id: 4, restaurant_id: 2, name: "Falafel Wrap", price: 10.99, category: "Main" },
  { id: 5, restaurant_id: 3, name: "Burger", price: 9.99, category: "Main" },
  { id: 6, restaurant_id: 4, name: "Grilled Salmon", price: 22.99, category: "Main" },
  { id: 7, restaurant_id: 5, name: "Croissant", price: 3.99, category: "Pastry" },
];

// Seed orders — large dataset to make the fetchAll bug visible
const orders = [];
for (let i = 1; i <= 500; i++) {
  orders.push({
    id: i,
    user_id: (i % 10) + 1,
    restaurant_id: (i % 5) + 1,
    items: [{ menu_item_id: (i % 7) + 1, quantity: 1, price: 9.99 }],
    total: 9.99,
    status: i % 3 === 0 ? "delivered" : i % 3 === 1 ? "preparing" : "pending",
    created_at: new Date(Date.now() - i * 60000).toISOString(),
  });
}

let nextOrderId = orders.length + 1;

function requireAuth(c, next) {
  const auth = c.req.header("authorization");
  if (auth !== `Bearer ${VALID_TOKEN}`) {
    return c.json({ detail: "Unauthorized" }, 401);
  }
  return next();
}

app.get("/api/health", (c) => c.json({ status: "ok", service: "hestia-eats" }));

app.get("/api/restaurants", requireAuth, (c) => {
  const { cuisine } = c.req.query();
  const result = cuisine
    ? restaurants.filter((r) => r.cuisine.toLowerCase().includes(cuisine.toLowerCase()))
    : restaurants;
  return c.json({ restaurants: result });
});

app.get("/api/restaurants/:id", requireAuth, (c) => {
  const r = restaurants.find((r) => r.id === parseInt(c.req.param("id")));
  if (!r) return c.json({ detail: "Restaurant not found" }, 404);
  return c.json(r);
});

app.get("/api/restaurants/:id/menu", requireAuth, (c) => {
  const id = parseInt(c.req.param("id"));
  const items = menuItems.filter((m) => m.restaurant_id === id);
  return c.json({ items });
});

app.post("/api/orders", requireAuth, async (c) => {
  const body = await c.req.json();
  const { restaurant_id, items } = body;
  if (!restaurant_id || !items?.length) {
    return c.json({ detail: "restaurant_id and items required" }, 400);
  }
  const restaurant = restaurants.find((r) => r.id === restaurant_id);
  if (!restaurant) return c.json({ detail: "Restaurant not found" }, 404);

  const total = items.reduce((sum, item) => sum + item.price * item.quantity, 0);
  const order = {
    id: nextOrderId++,
    user_id: 1,
    restaurant_id,
    items,
    total: Math.round(total * 100) / 100,
    status: "pending",
    created_at: new Date().toISOString(),
  };
  orders.push(order);
  return c.json(order, 201);
});

app.get("/api/orders/:id", requireAuth, (c) => {
  const order = orders.find((o) => o.id === parseInt(c.req.param("id")));
  if (!order) return c.json({ detail: "Order not found" }, 404);
  return c.json(order);
});

// BUG: loads ALL orders into memory — no LIMIT, no pagination
// Under concurrent load this is slow and memory-intensive
app.get("/api/orders/history", requireAuth, (c) => {
  const { user_id } = c.req.query();
  // BUG: fetchAll — loads entire orders array, filters in memory
  const allOrders = orders.slice(); // copies all 500+ orders
  const userOrders = user_id
    ? allOrders.filter((o) => o.user_id === parseInt(user_id))
    : allOrders;
  return c.json({ orders: userOrders, total: userOrders.length });
});

app.get("/api/orders/history/stats", requireAuth, (c) => {
  // BUG: also unbounded — iterates all orders for stats
  const allOrders = orders.slice();
  const stats = {
    total_orders: allOrders.length,
    total_revenue: allOrders.reduce((s, o) => s + o.total, 0),
    by_status: {
      pending: allOrders.filter((o) => o.status === "pending").length,
      preparing: allOrders.filter((o) => o.status === "preparing").length,
      delivered: allOrders.filter((o) => o.status === "delivered").length,
    },
  };
  return c.json(stats);
});

serve({ fetch: app.fetch, port: 8080 }, () =>
  console.log("Hestia Eats running on :8080")
);
