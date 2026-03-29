<template>
  <div class="app-shell">
    <aside class="side-nav">
      <div class="brand-block">
        <div class="brand-badge">btyAquant</div>
        <h1>btyAquant 工作台</h1>
        <p>新闻、策略、自选与用户权限统一在一个平台里。</p>
      </div>

      <nav class="nav-list">
        <RouterLink to="/" class="nav-link">量化分析</RouterLink>
        <RouterLink to="/strategy-picker" class="nav-link">策略选股</RouterLink>
        <RouterLink to="/watchlist" class="nav-link">东财智选</RouterLink>
        <RouterLink to="/users" class="nav-link">用户管理</RouterLink>
      </nav>

      <div class="user-panel">
        <div class="user-title-row">
          <div class="user-greeting">
            <span class="user-label">您好，</span>
            <span class="user-name">{{ user?.username }}</span>
          </div>
          <button class="ghost-btn small user-logout-inline" @click="logout">退出</button>
        </div>
        <div class="user-panel-grid">
          <div class="user-glance">
            <div class="user-glance-label">用户身份</div>
            <div class="user-glance-value">{{ user?.role_label || (user?.is_admin ? "管理员" : "普通用户") }}</div>
            <div class="user-glance-note">{{ user?.is_super_admin ? "全局最高权限" : user?.is_admin ? "负责账号维护" : "查看个人内容" }}</div>
          </div>
          <div class="user-glance">
            <div class="user-glance-label">工作状态</div>
            <div class="user-glance-value">{{ user?.has_mx_api_key ? "已接入 MX" : "待配置 MX" }}</div>
            <div class="user-glance-note">{{ user?.is_super_admin ? "超级管理员" : user?.is_admin ? "管理员账号" : "工作台用户" }}</div>
          </div>
        </div>
      </div>
    </aside>

    <section class="content-area">
      <header class="topbar">
        <div class="topbar-copy">
          <div class="eyebrow">{{ title }}</div>
          <h2>您好，{{ user?.username }}</h2>
          <p class="topbar-subtitle">{{ subtitle }}</p>
        </div>
        <slot name="header-extra" />
      </header>

      <main class="page-body">
        <slot />
      </main>
    </section>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { clearSession, useSessionUser } from "../services/session";

defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, required: true }
});

const router = useRouter();
const sessionUser = useSessionUser();
const user = computed(() => sessionUser.value);

function logout() {
  clearSession();
  router.push("/login");
}
</script>
