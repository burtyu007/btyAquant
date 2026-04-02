<template>
  <AppShell title="策略选股" subtitle="按数据库 policy_files 表生成策略列表，详情页会联动本地 policy 目录中的 README 和 results.json。">
    <section class="panel hero-panel">
      <div class="panel-head">
        <div>
          <div class="panel-kicker">策略维护</div>
          <h3>{{ editingId ? `编辑策略 #${editingId}` : "新增策略" }}</h3>
          <p class="note">手动维护 `policy_files` 的元数据，后续把脚本目录放到 `quant/policy/&lt;策略目录&gt;/` 即可联动展示。</p>
        </div>
        <div class="table-actions wrap-actions">
          <button v-if="editingId" class="ghost-btn small" type="button" @click="resetForm">取消编辑</button>
        </div>
      </div>

      <form class="analysis-form policy-form" @submit.prevent="submitPolicy">
        <label>
          <span>策略名称</span>
          <input v-model="form.name" type="text" placeholder="例如 布林带综合选股策略" />
        </label>
        <label>
          <span>策略目录</span>
          <input v-model="form.folder" type="text" placeholder="例如 bollinger_zzscanner" />
        </label>
        <label>
          <span>README 文件</span>
          <input v-model="form.readme" type="text" placeholder="例如 README.md" />
        </label>
        <label>
          <span>脚本路径</span>
          <input v-model="form.path" type="text" placeholder="例如 bollinger_zscore_scanner.py" />
        </label>
        <label>
          <span>结果文件</span>
          <input v-model="form.results" type="text" placeholder="例如 results.json" />
        </label>
        <label>
          <span>创建人</span>
          <select v-model="form.created_user_id">
            <option :value="null">默认当前登录用户</option>
            <option v-for="user in userOptions" :key="user.id" :value="user.id">
              {{ user.username }} (#{{ user.id }})
            </option>
          </select>
        </label>
        <label class="analysis-span-2">
          <span>列表展示字段</span>
          <input v-model="form.list_show_fields" type="text" placeholder="例如 rank,code,name,zscore,buy_score" />
        </label>
        <div class="table-actions analysis-actions">
          <button class="primary-btn" :disabled="saving">{{ saving ? "保存中..." : editingId ? "更新策略" : "新增策略" }}</button>
          <button type="button" class="ghost-btn" :disabled="saving" @click="resetForm">重置</button>
        </div>
      </form>
      <p v-if="message" class="note">{{ message }}</p>
      <p v-if="error" class="error-text">{{ error }}</p>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <div class="panel-kicker">策略目录</div>
          <h3>策略列表</h3>
          <p class="note">用户可以把自己的量化脚本放到 `quant/policy/&lt;策略目录&gt;/`，当前先支持 Python 脚本。</p>
        </div>
        <div class="table-actions wrap-actions">
          <button class="ghost-btn small" :disabled="loading" @click="fetchPolicies">
            {{ loading ? "刷新中..." : "刷新列表" }}
          </button>
        </div>
      </div>

      <div class="strategy-library-summary">
        <div class="summary-chip">
          <span>策略数量</span>
          <strong>{{ policies.length }}</strong>
        </div>
        <div class="summary-chip">
          <span>当前支持</span>
          <strong>Python 脚本</strong>
        </div>
        <div class="summary-chip">
          <span>结果约定</span>
          <strong>`fields + lists`</strong>
        </div>
      </div>

      <p v-if="error" class="error-text">{{ error }}</p>
      <div v-if="loading && !policies.length" class="empty-state">正在读取策略列表...</div>
      <div v-else-if="!policies.length" class="empty-state">当前还没有策略记录。</div>
      <table v-else class="data-table strategy-library-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>策略名称</th>
            <th>目录</th>
            <th>脚本</th>
            <th>README</th>
            <th>结果文件</th>
            <th>列表字段</th>
            <th>创建人</th>
            <th>结果条数</th>
            <th>结果类型</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in policies" :key="item.id">
            <td>{{ item.id }}</td>
            <td>
              <div class="policy-title-cell">
                <strong>{{ item.name }}</strong>
                <span>{{ item.script_language.toUpperCase() }}</span>
              </div>
            </td>
            <td>{{ item.folder || "-" }}</td>
            <td>{{ item.script_filename }}</td>
            <td>
              <span :class="item.readme_exists ? 'file-status exists' : 'file-status missing'">{{ item.readme }}</span>
            </td>
            <td>
              <span :class="item.results_exists ? 'file-status exists' : 'file-status missing'">{{ item.results || "-" }}</span>
            </td>
            <td>{{ item.list_show_fields.join(", ") || "-" }}</td>
            <td>{{ item.created_user_name || `用户#${item.created_user_id}` }}</td>
            <td>{{ item.result_count }}</td>
            <td>{{ item.results_format }}</td>
            <td>{{ formatDateTime(item.updated_at) }}</td>
            <td class="table-actions">
              <button class="primary-btn small-btn" @click="viewDetail(item.id)">查看详情</button>
              <button class="ghost-btn small" :disabled="!item.can_edit" @click="startEdit(item)">编辑</button>
              <button class="ghost-btn small danger" :disabled="!item.can_delete" @click="removePolicy(item)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </AppShell>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import AppShell from "../components/AppShell.vue";
import api from "../services/api";

const router = useRouter();
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const message = ref("");
const policies = ref([]);
const userOptions = ref([]);
const editingId = ref(null);
const form = reactive({
  name: "",
  folder: "",
  readme: "README.md",
  path: "",
  results: "results.json",
  list_show_fields: "",
  created_user_id: null,
});

function formatDateTime(value) {
  return value ? value.slice(0, 19).replace("T", " ") : "-";
}

function resetForm() {
  editingId.value = null;
  form.name = "";
  form.folder = "";
  form.readme = "README.md";
  form.path = "";
  form.results = "results.json";
  form.list_show_fields = "";
  form.created_user_id = null;
}

function viewDetail(id) {
  router.push({ name: "strategy-picker-detail", params: { id } });
}

function startEdit(item) {
  editingId.value = item.id;
  form.name = item.name || "";
  form.folder = item.folder || "";
  form.readme = item.readme || "README.md";
  form.path = item.path || "";
  form.results = item.results || "results.json";
  form.list_show_fields = Array.isArray(item.list_show_fields) ? item.list_show_fields.join(",") : "";
  form.created_user_id = item.created_user_id || null;
  message.value = "";
  error.value = "";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function submitPolicy() {
  saving.value = true;
  error.value = "";
  message.value = "";
  try {
    const payload = {
      name: form.name,
      folder: form.folder || null,
      readme: form.readme,
      path: form.path,
      results: form.results || null,
      list_show_fields: form.list_show_fields,
      created_user_id: form.created_user_id || null,
    };
    if (editingId.value) {
      await api.put(`/policies/${editingId.value}`, payload);
      message.value = "策略记录已更新。";
    } else {
      await api.post("/policies", payload);
      message.value = "策略记录已新增。";
    }
    resetForm();
    await fetchPolicies();
  } catch (err) {
    error.value = err.response?.data?.detail || "策略保存失败";
  } finally {
    saving.value = false;
  }
}

async function removePolicy(item) {
  if (!window.confirm(`确认删除策略「${item.name}」吗？`)) {
    return;
  }
  error.value = "";
  message.value = "";
  try {
    await api.delete(`/policies/${item.id}`);
    if (editingId.value === item.id) {
      resetForm();
    }
    message.value = "策略记录已删除。";
    await fetchPolicies();
  } catch (err) {
    error.value = err.response?.data?.detail || "策略删除失败";
  }
}

async function fetchPolicies() {
  loading.value = true;
  if (!saving.value) {
    error.value = "";
  }
  try {
    const { data } = await api.get("/policies");
    policies.value = Array.isArray(data) ? data : [];
  } catch (err) {
    policies.value = [];
    error.value = err.response?.data?.detail || "策略列表读取失败";
  } finally {
    loading.value = false;
  }
}

async function fetchUsers() {
  try {
    const { data } = await api.get("/users");
    userOptions.value = Array.isArray(data) ? data : [];
  } catch {
    userOptions.value = [];
  }
}

onMounted(async () => {
  await Promise.all([fetchPolicies(), fetchUsers()]);
});
</script>
