<template>
  <AppShell title="东财智选" subtitle="集中查看 MX 东财智选结果与 MX 自选股，同步维护妙想侧自选。">
    <section class="panel history-panel">
      <div class="panel-head">
        <div>
          <div class="panel-kicker">智能推荐</div>
          <h3>MX 东财智选</h3>
          <p class="note">默认每页 5 条，支持按最新价和涨跌幅高低排序。</p>
        </div>
        <div class="news-actions">
          <button class="ghost-btn small" @click="fetchRecommendations(recommendationPage, true)">刷新</button>
          <button class="ghost-btn small" @click="recommendationCollapsed = !recommendationCollapsed">{{ recommendationCollapsed ? "展开" : "收起" }}</button>
        </div>
      </div>

      <div v-if="recommendationCollapsed" class="collapsed-tip">MX 东财智选已收起，点击右上角“展开”查看。</div>
      <template v-else>
        <form class="analysis-form recommendation-inline-form" @submit.prevent="fetchRecommendations(1)">
          <label class="analysis-span-2">
            <span>推荐条件</span>
            <input v-model="recommendationKeyword" type="text" placeholder="例如 东财智选 推荐" />
          </label>
          <button class="primary-btn" :disabled="loadingRecommendations">{{ loadingRecommendations ? "拉取中..." : "获取推荐" }}</button>
        </form>

        <p v-if="recommendationLogic" class="hero-note">推荐逻辑：{{ recommendationLogic }}</p>
        <p v-if="recommendationError" class="error-text">{{ recommendationError }}</p>
        <div v-if="!recommendations.length" class="empty-state">还没有智能推荐结果。</div>
        <template v-else>
          <table class="data-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>市场</th>
                <th>名称</th>
                <th class="sortable-head" @click="toggleRecommendationSort('last_price')">
                  最新价{{ sortIndicator('last_price') }}
                </th>
                <th class="sortable-head" @click="toggleRecommendationSort('change_pct')">
                  涨跌幅{{ sortIndicator('change_pct') }}
                </th>
                <th>行业</th>
                <th>概念</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in sortedRecommendations" :key="`${item.market}-${item.symbol}`">
                <td>{{ item.symbol }}</td>
                <td>{{ item.market }}</td>
                <td>{{ item.display_name }}</td>
                <td>{{ formatPrice(item.last_price) }}</td>
                <td :class="priceClass(item.change_pct)">{{ formatPercent(item.change_pct) }}</td>
                <td>{{ item.industry || "-" }}</td>
                <td>{{ item.concepts || "-" }}</td>
              </tr>
            </tbody>
          </table>
          <div class="pagination-bar">
            <span>第 {{ recommendationPage }} / {{ recommendationTotalPages }} 页，共 {{ recommendationTotalCount }} 条</span>
            <div class="table-actions">
              <button class="ghost-btn small" :disabled="recommendationPage === 1 || loadingRecommendations" @click="changeRecommendationPage(recommendationPage - 1)">上一页</button>
              <button class="ghost-btn small" :disabled="recommendationPage >= recommendationTotalPages || loadingRecommendations" @click="changeRecommendationPage(recommendationPage + 1)">下一页</button>
            </div>
          </div>
        </template>
      </template>
    </section>

    <section class="panel history-panel">
      <div class="panel-head">
        <div>
          <div class="panel-kicker">MX 自选</div>
          <h3>MX 自选股</h3>
          <p class="note">默认每页 10 条，默认收起，列表缓存 4 小时，点击刷新会强制拉取最新结果。</p>
        </div>
        <div class="news-actions mx-panel-actions">
          <button class="ghost-btn small" @click="fetchMxWatchlist(true)">刷新 MX 自选</button>
          <button class="ghost-btn small" @click="importMxWatchlist">同步到本地自选</button>
        </div>
      </div>

      <form class="analysis-form mx-inline-form" @submit.prevent="addMxItem">
        <label>
          <span>市场</span>
          <select v-model="mxForm.market">
            <option value="a">A股</option>
            <option value="hk">港股</option>
          </select>
        </label>
        <label>
          <span>股票代码</span>
          <input v-model="mxForm.symbol" type="text" placeholder="例如 600036 或 00700" />
        </label>
        <button class="primary-btn" :disabled="mxSubmitting">{{ mxSubmitting ? "同步中..." : "加入自选" }}</button>
      </form>

      <p v-if="mxMessage" class="note">{{ mxMessage }}</p>
      <p v-if="mxError" class="error-text">{{ mxError }}</p>
      <button type="button" class="collapsed-tip collapsed-tip-toggle" @click="mxCollapsed = !mxCollapsed">
        {{ mxCollapsed ? "MX 自选已收起，点击当前图层展开查看。" : "MX 自选已展开，点击当前图层收起。" }}
      </button>
      <template v-if="!mxCollapsed">
        <div v-if="!mxItems.length" class="empty-state">还没有 MX 自选结果。</div>
        <template v-else>
          <table class="data-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>市场</th>
                <th>名称</th>
                <th>最新价</th>
                <th>涨跌幅</th>
                <th>最高</th>
                <th>最低</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in pagedMxItems" :key="`${item.market}-${item.symbol}`">
                <td>{{ item.symbol }}</td>
                <td>{{ item.market }}</td>
                <td>{{ item.display_name }}</td>
                <td>{{ formatPrice(item.last_price) }}</td>
                <td :class="priceClass(item.change_pct)">{{ formatPercent(item.change_pct) }}</td>
                <td>{{ formatPrice(item.day_high) }}</td>
                <td>{{ formatPrice(item.day_low) }}</td>
                <td class="table-actions">
                  <button class="ghost-btn small danger" @click="removeMxItem(item)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="pagination-bar">
            <span>第 {{ mxPage }} / {{ mxTotalPages }} 页，共 {{ mxItems.length }} 条</span>
            <div class="table-actions">
              <button class="ghost-btn small" :disabled="mxPage === 1" @click="mxPage--">上一页</button>
              <button class="ghost-btn small" :disabled="mxPage === mxTotalPages" @click="mxPage++">下一页</button>
            </div>
          </div>
        </template>
      </template>
    </section>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import AppShell from "../components/AppShell.vue";
import api from "../services/api";
import { useSessionUser } from "../services/session";

const PAGE_SIZE = 10;
const currentUser = useSessionUser();
const mxItems = ref([]);
const mxSubmitting = ref(false);
const mxError = ref("");
const mxMessage = ref("");
const mxCollapsed = ref(true);
const mxPage = ref(1);
const mxForm = reactive({ symbol: "", market: "a" });
const recommendations = ref([]);
const loadingRecommendations = ref(false);
const recommendationError = ref("");
const recommendationLogic = ref("");
const recommendationKeyword = ref("东财智选 推荐");
const recommendationCollapsed = ref(false);
const recommendationPage = ref(1);
const recommendationPageSize = 5;
const recommendationTotalCount = ref(0);
const recommendationSortField = ref("change_pct");
const recommendationSortOrder = ref("desc");

const mxTotalPages = computed(() => Math.max(1, Math.ceil(mxItems.value.length / PAGE_SIZE)));
const pagedMxItems = computed(() => mxItems.value.slice((mxPage.value - 1) * PAGE_SIZE, mxPage.value * PAGE_SIZE));
const recommendationTotalPages = computed(() =>
  Math.max(1, Math.ceil(recommendationTotalCount.value / recommendationPageSize))
);
const sortedRecommendations = computed(() => {
  const direction = recommendationSortOrder.value === "asc" ? 1 : -1;
  return [...recommendations.value].sort((left, right) => {
    const leftValue = Number(left?.[recommendationSortField.value] ?? 0);
    const rightValue = Number(right?.[recommendationSortField.value] ?? 0);
    return (leftValue - rightValue) * direction;
  });
});

function formatPrice(value) {
  return value == null ? "-" : Number(value).toFixed(2);
}

function formatPercent(value) {
  return value == null ? "-" : `${Number(value).toFixed(2)}%`;
}

function priceClass(value) {
  if (value == null) return "";
  if (Number(value) > 0) return "positive";
  if (Number(value) < 0) return "negative";
  return "";
}

function resetMxPage() {
  mxPage.value = Math.min(mxPage.value, mxTotalPages.value);
}

async function fetchMxWatchlist(forceRefresh = false) {
  mxError.value = "";
  mxMessage.value = "";
  if (!currentUser.value?.has_mx_api_key) {
    mxItems.value = [];
    mxError.value = "请先在用户管理里配置当前用户的 MX Key。";
    resetMxPage();
    return;
  }
  try {
    const { data } = await api.get("/watchlist/mx-self-select", { params: { force_refresh: forceRefresh } });
    mxItems.value = data.items;
    resetMxPage();
  } catch (err) {
    mxItems.value = [];
    resetMxPage();
    mxError.value = err.response?.data?.detail || "MX 自选拉取失败";
  }
}

async function fetchRecommendations(page = recommendationPage.value, forceRefresh = false) {
  recommendationError.value = "";
  recommendationLogic.value = "";
  if (!currentUser.value?.has_mx_api_key) {
    recommendations.value = [];
    recommendationTotalCount.value = 0;
    recommendationError.value = "请先在用户管理里配置当前用户的 MX Key，再获取智能推荐。";
    return;
  }
  loadingRecommendations.value = true;
  try {
    recommendationPage.value = page;
    const { data } = await api.get("/market/recommendations", {
      params: {
        keyword: recommendationKeyword.value,
        page_no: recommendationPage.value,
        page_size: recommendationPageSize,
        force_refresh: forceRefresh
      }
    });
    recommendations.value = data.items;
    recommendationLogic.value = data.select_logic || "";
    recommendationTotalCount.value = data.total_count || data.items.length;
  } catch (err) {
    recommendations.value = [];
    recommendationTotalCount.value = 0;
    recommendationError.value = err.response?.data?.detail || "智能推荐拉取失败";
  } finally {
    loadingRecommendations.value = false;
  }
}

function changeRecommendationPage(page) {
  if (page < 1 || page > recommendationTotalPages.value || page === recommendationPage.value) {
    return;
  }
  fetchRecommendations(page);
}

function toggleRecommendationSort(field) {
  if (recommendationSortField.value === field) {
    recommendationSortOrder.value = recommendationSortOrder.value === "desc" ? "asc" : "desc";
    return;
  }
  recommendationSortField.value = field;
  recommendationSortOrder.value = "desc";
}

function sortIndicator(field) {
  if (recommendationSortField.value !== field) {
    return "";
  }
  return recommendationSortOrder.value === "desc" ? " ↓" : " ↑";
}

async function addMxItem() {
  mxSubmitting.value = true;
  mxError.value = "";
  mxMessage.value = "";
  try {
    const { data } = await api.post("/watchlist/mx-self-select", mxForm);
    mxMessage.value = data.message;
    mxForm.symbol = "";
    await fetchMxWatchlist(true);
  } catch (err) {
    mxError.value = err.response?.data?.detail || "同步 MX 自选失败";
  } finally {
    mxSubmitting.value = false;
  }
}

async function importMxWatchlist() {
  mxError.value = "";
  mxMessage.value = "";
  try {
    const { data } = await api.post("/watchlist/mx-self-select/import");
    mxMessage.value = data.message;
    await fetchMxWatchlist(true);
  } catch (err) {
    mxError.value = err.response?.data?.detail || "同步 MX 自选失败";
  }
}

async function removeMxItem(item) {
  mxError.value = "";
  mxMessage.value = "";
  try {
    const { data } = await api.delete(`/watchlist/mx-self-select/${item.market}/${item.symbol}`);
    mxMessage.value = data.message;
    await fetchMxWatchlist(true);
  } catch (err) {
    mxError.value = err.response?.data?.detail || "删除 MX 自选失败";
  }
}

onMounted(async () => {
  await Promise.all([fetchRecommendations(), fetchMxWatchlist()]);
});
</script>
