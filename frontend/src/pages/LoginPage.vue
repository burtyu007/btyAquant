<template>
  <section class="login-page">
    <div class="login-card">
      <div class="panel-kicker">btyAquant</div>
      <h1>btyAquant 登录</h1>
      <p>默认管理员账号为 <code>admin/admin</code>。登录后可查看新闻、做策略分析、自选股票和用户管理；只有进入东财智选时才会校验当前用户自己的 MX Key。</p>

      <form class="form-grid" @submit.prevent="handleLogin">
        <label>
          <span>用户名</span>
          <input v-model="form.username" type="text" placeholder="请输入用户名" />
        </label>
        <label>
          <span>密码</span>
          <input v-model="form.password" type="password" placeholder="请输入密码" />
        </label>
        <button class="primary-btn" :disabled="loading">{{ loading ? "登录中..." : "登录" }}</button>
      </form>

      <p v-if="error" class="error-text">{{ error }}</p>
    </div>
  </section>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import api from "../services/api";
import { saveSession } from "../services/session";

const router = useRouter();
const loading = ref(false);
const error = ref("");
const form = reactive({ username: "admin", password: "admin" });

async function handleLogin() {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await api.post("/auth/login", form);
    saveSession(data.access_token, data.user);
    router.push("/");
  } catch (err) {
    error.value = err.response?.data?.detail || "登录失败，请检查账号密码";
  } finally {
    loading.value = false;
  }
}
</script>
