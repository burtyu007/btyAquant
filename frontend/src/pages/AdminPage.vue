<template>
  <AppShell title="用户管理" subtitle="每个人都在这里维护自己的 MX Key。">
    <section class="panel hero-panel">
      <div class="panel-head">
        <div>
          <div class="panel-kicker">我的 MX Key</div>
          <h3>配置东财key</h3>
          <p class="note">当前遮罩 Key：{{ currentUser?.masked_mx_api_key || "未配置" }}</p>
        </div>
        <div class="badge">{{ currentUser?.has_mx_api_key ? "已配置" : "未配置" }}</div>
      </div>

      <form class="analysis-form key-inline-form" @submit.prevent="handleMxKeyAction">
        <label class="analysis-span-2">
          <span>MX Key</span>
          <input
            v-model="mxKeyForm.api_key"
            :disabled="currentUser?.has_mx_api_key && !editingMxKey"
            type="password"
            :placeholder="currentUser?.has_mx_api_key ? (editingMxKey ? '请输入新的 MX API Key' : currentUser?.masked_mx_api_key || '已配置') : '请输入当前用户自己的 MX API Key'"
          />
        </label>
        <button class="primary-btn" :disabled="savingMxKey">
          {{ savingMxKey ? "处理中..." : currentUser?.has_mx_api_key ? (editingMxKey ? "更新" : "编辑") : "保存" }}
        </button>
      </form>

      <p v-if="mxKeyNotice" class="hero-note">{{ mxKeyNotice }}</p>
      <p class="hero-note">系统默认只展示打星后的 Key；复制自己的 Key 时，需要再次输入当前登录密码。</p>
      <p v-if="mxKeyMessage" class="note">{{ mxKeyMessage }}</p>
      <p v-if="mxKeyError" class="error-text">{{ mxKeyError }}</p>
    </section>

    <section v-if="currentUser?.is_admin" class="panel hero-panel">
      <div class="panel-head">
        <div>
          <div class="panel-kicker">账号管理</div>
          <h3>创建账号</h3>
        </div>
      </div>

      <form class="analysis-form admin-form" @submit.prevent="createUser">
        <label>
          <span>用户名</span>
          <input v-model="form.username" type="text" />
        </label>
        <label>
          <span>密码</span>
          <input v-model="form.password" type="password" />
        </label>
        <label v-if="currentUser?.is_super_admin" class="checkbox-field">
          <input v-model="form.is_admin" type="checkbox" />
          <span>设为管理员</span>
        </label>
        <div v-else class="note admin-note">普通管理员只能创建普通用户，不能设置管理员或超级管理员。</div>
        <button class="primary-btn" :disabled="submitting">{{ submitting ? "创建中..." : "创建用户" }}</button>
      </form>
      <p v-if="error" class="error-text">{{ error }}</p>
    </section>

    <section class="panel history-panel">
      <div class="panel-head">
        <div>
          <div class="panel-kicker">账号列表</div>
          <h3>{{ currentUser?.is_super_admin ? "全量用户" : currentUser?.is_admin ? "可管理用户" : "我的账号" }}</h3>
        </div>
        <button class="ghost-btn small" @click="fetchUsers">刷新</button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>角色</th>
            <th>MX Key</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in users" :key="item.id">
            <td>{{ item.id }}</td>
            <td>{{ item.username }}</td>
            <td>{{ item.role_label }}</td>
            <td>{{ item.masked_mx_api_key || "未配置" }}</td>
            <td>{{ item.created_at.slice(0, 19).replace('T', ' ') }}</td>
            <td class="table-actions">
              <button class="ghost-btn small" :disabled="!item.can_copy_mx_key" @click="copyOwnMxKey(item)">复制 Key</button>
              <button class="ghost-btn small danger" :disabled="!item.can_delete" @click="deleteUser(item.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="copyMessage" class="note">{{ copyMessage }}</p>
      <p v-if="copyError" class="error-text">{{ copyError }}</p>
    </section>

    <div v-if="copyModalOpen" class="modal-overlay" @click.self="closeCopyModal">
      <div class="modal-card">
        <div class="panel-kicker">安全校验</div>
        <h3>请输入登录密码</h3>
        <p class="note">确认身份后，系统会复制当前登录用户自己的 MX Key。</p>

        <form class="form-grid" @submit.prevent="confirmCopyMxKey">
          <label>
            <span>登录密码</span>
            <input v-model="copyForm.password" type="password" placeholder="请输入当前登录密码" autofocus />
          </label>
          <div class="modal-actions">
            <button type="button" class="ghost-btn" @click="closeCopyModal">取消</button>
            <button type="submit" class="primary-btn" :disabled="copyingKey">{{ copyingKey ? "复制中..." : "确认复制" }}</button>
          </div>
        </form>
        <p v-if="copyModalError" class="error-text">{{ copyModalError }}</p>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppShell from "../components/AppShell.vue";
import api from "../services/api";
import { getToken, saveSession, useSessionUser } from "../services/session";

const currentUser = useSessionUser();
const route = useRoute();
const router = useRouter();
const users = ref([]);
const submitting = ref(false);
const savingMxKey = ref(false);
const editingMxKey = ref(false);
const error = ref("");
const mxKeyMessage = ref("");
const mxKeyError = ref("");
const copyMessage = ref("");
const copyError = ref("");
const copyModalOpen = ref(false);
const copyingKey = ref(false);
const copyModalError = ref("");
const copyTarget = ref(null);
const mxKeyNotice = ref("");
const form = reactive({ username: "", password: "", is_admin: false });
const mxKeyForm = reactive({ api_key: "" });
const copyForm = reactive({ password: "" });

async function fetchUsers() {
  const { data } = await api.get("/users");
  users.value = data;
}

async function saveMxKey() {
  const { data } = await api.post("/auth/mx-key", mxKeyForm);
  saveSession(getToken(), data);
  mxKeyForm.api_key = "";
  editingMxKey.value = false;
  mxKeyMessage.value = "MX Key 已更新。";
  mxKeyNotice.value = "";
  if (route.query.notice) {
    router.replace({ name: "users" });
  }
  await fetchUsers();
}

async function handleMxKeyAction() {
  savingMxKey.value = true;
  mxKeyMessage.value = "";
  mxKeyError.value = "";
  try {
    if (currentUser.value?.has_mx_api_key && !editingMxKey.value) {
      editingMxKey.value = true;
      mxKeyMessage.value = "请输入新的 MX Key 后再次点击“更新”。";
      return;
    }
    await saveMxKey();
  } catch (err) {
    mxKeyError.value = err.response?.data?.detail || "保存 MX Key 失败";
  } finally {
    savingMxKey.value = false;
  }
}

async function createUser() {
  submitting.value = true;
  error.value = "";
  try {
    await api.post("/users", form);
    form.username = "";
    form.password = "";
    form.is_admin = false;
    await fetchUsers();
  } catch (err) {
    error.value = err.response?.data?.detail || "创建用户失败";
  } finally {
    submitting.value = false;
  }
}

async function deleteUser(id) {
  await api.delete(`/users/${id}`);
  await fetchUsers();
}

async function copyOwnMxKey(item) {
  copyMessage.value = "";
  copyError.value = "";
  if (!item.can_copy_mx_key) {
    copyError.value = "只能复制当前登录用户自己的 MX Key。";
    return;
  }
  copyTarget.value = item;
  copyForm.password = "";
  copyModalError.value = "";
  copyModalOpen.value = true;
}

function closeCopyModal() {
  copyModalOpen.value = false;
  copyingKey.value = false;
  copyForm.password = "";
  copyModalError.value = "";
  copyTarget.value = null;
}

async function confirmCopyMxKey() {
  if (!copyTarget.value?.can_copy_mx_key) {
    copyModalError.value = "只能复制当前登录用户自己的 MX Key。";
    return;
  }
  if (!copyForm.password) {
    copyModalError.value = "请输入登录密码。";
    return;
  }
  copyingKey.value = true;
  try {
    const { data } = await api.post("/auth/mx-key/reveal", { password: copyForm.password });
    await copyText(data.api_key);
    copyMessage.value = "MX Key 已复制到剪贴板。";
    closeCopyModal();
  } catch (err) {
    copyModalError.value = err.response?.data?.detail || "复制 MX Key 失败";
  } finally {
    copyingKey.value = false;
  }
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Fallback to execCommand below when browser blocks async clipboard.
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  textarea.style.pointerEvents = "none";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) {
    throw new Error("copy_failed");
  }
}

onMounted(async () => {
  if (route.query.notice === "mx_key_required") {
    mxKeyNotice.value = "进入东财智选前需要先配置 MX Key，请先在这里完成配置。";
  }
  await fetchUsers();
});
</script>
