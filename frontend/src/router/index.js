import { createRouter, createWebHistory } from "vue-router";
import { clearSession, getToken, getUser, refreshSessionUser } from "../services/session";
import DashboardPage from "../pages/DashboardPage.vue";
import LoginPage from "../pages/LoginPage.vue";
import StrategyPickerPage from "../pages/StrategyPickerPage.vue";
import StrategyPolicyDetailPage from "../pages/StrategyPolicyDetailPage.vue";
import WatchlistPage from "../pages/WatchlistPage.vue";
import AdminPage from "../pages/AdminPage.vue";

const routes = [
  { path: "/login", name: "login", component: LoginPage, meta: { guestOnly: true } },
  { path: "/", name: "dashboard", component: DashboardPage, meta: { requiresAuth: true } },
  { path: "/strategy-picker", name: "strategy-picker", component: StrategyPickerPage, meta: { requiresAuth: true } },
  { path: "/strategy-picker/:id", name: "strategy-picker-detail", component: StrategyPolicyDetailPage, meta: { requiresAuth: true } },
  { path: "/watchlist", name: "watchlist", component: WatchlistPage, meta: { requiresAuth: true } },
  { path: "/users", name: "users", component: AdminPage, meta: { requiresAuth: true } },
  { path: "/admin", redirect: { name: "users" } }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach(async (to) => {
  const token = getToken();
  let user = getUser();

  if (to.meta.requiresAuth && !token) {
    return { name: "login" };
  }
  if (token && (!user || user.is_super_admin === undefined)) {
    try {
      user = await refreshSessionUser();
    } catch {
      return { name: "login" };
    }
  }
  if (to.meta.guestOnly && token) {
    return { name: "dashboard" };
  }
  if (!token) {
    clearSession();
  }
  if (token && user && to.name === "watchlist" && !user.has_mx_api_key) {
    return { name: "users", query: { notice: "mx_key_required" } };
  }
  return true;
});

export default router;
