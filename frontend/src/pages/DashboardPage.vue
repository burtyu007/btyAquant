<template>
  <AppShell title="量化分析" subtitle="左侧展示入库后的财经热点，右侧做股票策略分析、回测与我的本地自选。">
    <div class="dashboard-layout">
      <NewsSidebar
        :items="news"
        :loading="loadingNews"
        :loading-more="loadingMoreNews"
        :has-more="hasMoreNews"
        :error="newsError"
        @refresh="fetchNews(true)"
        @load-more="loadMoreNews"
      />

      <div class="dashboard-main">
        <section class="panel hero-panel">
          <div class="panel-head">
            <div>
              <div class="panel-kicker">策略输入</div>
              <h3>股票量化分析-布林带均值回归</h3>
            </div>
            <div class="badge">预留多策略扩展</div>
          </div>

          <div class="strategy-presets">
            <div class="strategy-subhead">
              <div>
                <h4>组合建议</h4>
                <p class="note">一键套用常见区间与窗口组合，适合先快速看一眼策略表现。</p>
              </div>
              <span class="strategy-mini-badge">建议先用 2年 + 20日</span>
            </div>

            <div class="preset-grid">
              <button
                v-for="preset in STRATEGY_PRESETS"
                :key="preset.id"
                type="button"
                class="preset-card"
                :class="{ active: selectedPresetId === preset.id }"
                @click="applyPreset(preset)"
              >
                <span class="preset-tag">{{ preset.tag }}</span>
                <strong>{{ preset.label }}</strong>
                <span>{{ preset.lookbackLabel }} · {{ preset.windowLabel }}</span>
                <p>{{ preset.description }}</p>
              </button>
            </div>
          </div>

          <form class="analysis-form strategy-form" @submit.prevent="runAnalysis">
            <label>
              <span>市场</span>
              <select v-model="form.market">
                <option value="a">A股</option>
                <option value="hk">港股</option>
              </select>
            </label>
            <label>
              <span>股票代码</span>
              <input v-model="form.symbol" type="text" placeholder="例如 600036 或 00700" />
            </label>
            <label>
              <span>历史回看区间</span>
              <select v-model="form.lookback_period" @change="syncPresetFromCustom">
                <option v-for="item in LOOKBACK_OPTIONS" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label>
              <span>布林带窗口</span>
              <select v-model="form.bollinger_window" @change="syncPresetFromCustom">
                <option v-for="item in WINDOW_OPTIONS" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <div class="table-actions analysis-actions">
              <button class="primary-btn" :disabled="loadingAnalysis">{{ loadingAnalysis ? "分析中..." : "确认分析" }}</button>
              <button type="button" class="ghost-btn" :disabled="loadingAnalysis && !analysisResults.length" @click="clearAnalysis">清除</button>
            </div>
          </form>

          <div class="strategy-summary-strip">
            <div class="summary-chip">
              <span>当前选择</span>
              <strong>{{ currentPresetLabel }}</strong>
            </div>
            <div class="summary-chip">
              <span>历史回看</span>
              <strong>{{ formatLookback(form.lookback_period) }}</strong>
            </div>
            <div class="summary-chip">
              <span>窗口长度</span>
              <strong>{{ formatWindow(form.bollinger_window) }}</strong>
            </div>
          </div>

          <p v-if="analysisHint" class="hero-note">{{ analysisHint }}</p>
          <p v-if="analysisError" class="error-text">{{ analysisError }}</p>
        </section>

        <StrategyCard v-for="item in analysisResults" :key="item.key" :result="item" />

        <section class="panel history-panel">
          <div class="panel-head">
            <div>
              <div class="panel-kicker">股票列表</div>
              <h3>我的本地自选</h3>
              <p class="note">默认每页 10 条，默认收起。</p>
            </div>
            <div class="table-actions wrap-actions">
              <button class="primary-btn small-btn" @click="openWatchlistModal">加入自选</button>
              <button class="ghost-btn small" :disabled="refreshingAllWatchlist" @click="refreshAll">
                {{ refreshingAllWatchlist ? "刷新中..." : "刷新全部价格" }}
              </button>
              <button class="ghost-btn small" @click="localCollapsed = !localCollapsed">{{ localCollapsed ? "展开" : "收起" }}</button>
            </div>
          </div>
          <p v-if="watchlistError" class="error-text">{{ watchlistError }}</p>

          <div v-if="localCollapsed" class="collapsed-tip">本地自选已收起，点击右上角“展开”查看。</div>
          <template v-else>
            <div v-if="!watchlistItems.length" class="empty-state">还没有本地自选股票。</div>
            <template v-else>
              <table class="data-table">
                <thead>
                  <tr>
                    <th>代码</th>
                    <th>市场</th>
                    <th>名称</th>
                    <th>当前价</th>
                    <th>开盘价</th>
                    <th>收盘价</th>
                    <th>当日最高</th>
                    <th>当日最低</th>
                    <th>更新时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in pagedLocalItems" :key="item.id">
                    <td>{{ item.symbol }}</td>
                    <td>{{ item.market }}</td>
                    <td>{{ item.display_name || "-" }}</td>
                    <td>{{ formatPrice(item.last_price) }}</td>
                    <td>{{ formatPrice(item.open_price) }}</td>
                    <td>{{ formatPrice(item.close_price) }}</td>
                    <td>{{ formatPrice(item.day_high) }}</td>
                    <td>{{ formatPrice(item.day_low) }}</td>
                    <td>{{ item.last_price_at ? item.last_price_at.slice(0, 19).replace('T', ' ') : "-" }}</td>
                    <td class="table-actions">
                      <button class="ghost-btn small" :disabled="refreshingItemId === item.id" @click="refreshOne(item.id)">
                        {{ refreshingItemId === item.id ? "刷新中..." : "刷新" }}
                      </button>
                      <button class="ghost-btn small danger" @click="removeItem(item.id)">删除</button>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div class="pagination-bar">
                <span>第 {{ localPage }} / {{ localTotalPages }} 页，共 {{ watchlistItems.length }} 条</span>
                <div class="table-actions">
                  <button class="ghost-btn small" :disabled="localPage === 1" @click="localPage--">上一页</button>
                  <button class="ghost-btn small" :disabled="localPage === localTotalPages" @click="localPage++">下一页</button>
                </div>
              </div>
            </template>
          </template>
        </section>

        <section class="panel history-panel">
          <div class="panel-head">
            <div>
              <div class="panel-kicker">最近记录</div>
              <h3>我的分析历史</h3>
            </div>
            <button class="ghost-btn small" @click="fetchHistory">刷新</button>
          </div>

          <div v-if="!history.length" class="empty-state">还没有分析历史，先跑一次策略看看。</div>
          <table v-else class="data-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>代码</th>
                <th>市场</th>
                <th>回看区间</th>
                <th>窗口</th>
                <th>策略</th>
                <th>总收益率</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in history" :key="item.id">
                <td>{{ item.created_at.slice(0, 19).replace('T', ' ') }}</td>
                <td>{{ item.symbol }}</td>
                <td>{{ item.market }}</td>
                <td>{{ formatLookback(item.lookback_period) }}</td>
                <td>{{ formatWindow(item.bollinger_window) }}</td>
                <td>{{ item.strategy_key }}</td>
                <td>{{ item.result_payload.backtest?.total_return_pct ?? "-" }}%</td>
                <td>
                  <button class="ghost-btn small" @click="reviewHistory(item)">回看</button>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </div>

    <div v-if="watchlistModalOpen" class="modal-overlay" @click.self="closeWatchlistModal">
      <div class="modal-card">
        <div class="panel-kicker">本地自选</div>
        <h3>加入自选股票</h3>
        <p class="note">使用 AKShare 获取最近可用交易日的行情快照，收盘前优先取 T-1，收盘后自动取当天数据。</p>

        <form class="analysis-form modal-form" @submit.prevent="addItem">
          <label>
            <span>市场</span>
            <select v-model="watchlistForm.market">
              <option value="a">A股</option>
              <option value="hk">港股</option>
            </select>
          </label>
          <label>
            <span>股票代码</span>
            <input v-model="watchlistForm.symbol" type="text" placeholder="例如 600036 或 00700" />
          </label>
          <div class="modal-actions">
            <button type="button" class="ghost-btn" @click="closeWatchlistModal">取消</button>
            <button class="primary-btn" :disabled="submittingWatchlist">{{ submittingWatchlist ? "提交中..." : "确认加入" }}</button>
          </div>
        </form>
        <p v-if="watchlistError" class="error-text">{{ watchlistError }}</p>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import AppShell from "../components/AppShell.vue";
import NewsSidebar from "../components/NewsSidebar.vue";
import StrategyCard from "../components/StrategyCard.vue";
import api from "../services/api";

const PAGE_SIZE = 10;
const ANALYSIS_VIEW_KEY = "quant_analysis_view";
const LOOKBACK_OPTIONS = [
  { value: "6m", label: "6个月" },
  { value: "1y", label: "1年" },
  { value: "2y", label: "2年" },
  { value: "3y", label: "3年" },
  { value: "5y", label: "5年" },
  { value: "10y", label: "10年" }
];
const WINDOW_OPTIONS = [
  { value: "10d", label: "10日" },
  { value: "20d", label: "20日" },
  { value: "30d", label: "30日" },
  { value: "60d", label: "60日" }
];
const STRATEGY_PRESETS = [
  { id: "starter", tag: "入门默认", label: "标准均值回归", lookback: "2y", lookbackLabel: "2年", window: "20d", windowLabel: "20日", description: "样本够用，也不会被过旧数据拖慢。" },
  { id: "short", tag: "短线敏感", label: "快节奏捕捉", lookback: "1y", lookbackLabel: "1年", window: "10d", windowLabel: "10日", description: "信号更灵敏，适合先观察短线节奏。" },
  { id: "steady", tag: "中期稳健", label: "平衡回归", lookback: "3y", lookbackLabel: "3年", window: "30d", windowLabel: "30日", description: "过滤部分噪音，适合中期观察。" },
  { id: "slow", tag: "慢节奏", label: "长样本回归", lookback: "5y", lookbackLabel: "5年", window: "60d", windowLabel: "60日", description: "更偏向慢节奏、低频次的均值回归。" }
];
const STRATEGY_TITLES = {
  bollinger_mean_reversion: "布林带均值回归"
};
const news = ref([]);
const history = ref([]);
const analysisResults = ref([]);
const watchlistItems = ref([]);
const loadingNews = ref(false);
const loadingMoreNews = ref(false);
const loadingAnalysis = ref(false);
const submittingWatchlist = ref(false);
const refreshingAllWatchlist = ref(false);
const refreshingItemId = ref(null);
const analysisError = ref("");
const analysisHint = ref("");
const newsError = ref("");
const watchlistError = ref("");
const newsPage = ref(1);
const newsPageSize = 20;
const hasMoreNews = ref(true);
const selectedPresetId = ref("starter");
const form = reactive({ symbol: "600036", market: "a", lookback_period: "2y", bollinger_window: "20d" });
const watchlistForm = reactive({ symbol: "", market: "a" });
const watchlistModalOpen = ref(false);
const localCollapsed = ref(true);
const localPage = ref(1);
const localTotalPages = computed(() => Math.max(1, Math.ceil(watchlistItems.value.length / PAGE_SIZE)));
const pagedLocalItems = computed(() => watchlistItems.value.slice((localPage.value - 1) * PAGE_SIZE, localPage.value * PAGE_SIZE));
const currentPresetLabel = computed(() => {
  const preset = STRATEGY_PRESETS.find((item) => item.id === selectedPresetId.value);
  return preset ? `${preset.label} · ${preset.lookbackLabel} + ${preset.windowLabel}` : "自定义组合";
});

function saveAnalysisView() {
  localStorage.setItem(
    ANALYSIS_VIEW_KEY,
    JSON.stringify({
      form: { symbol: form.symbol, market: form.market },
      results: analysisResults.value,
      lookback_period: form.lookback_period,
      bollinger_window: form.bollinger_window,
      selected_preset_id: selectedPresetId.value
    })
  );
}

function restoreAnalysisView() {
  const raw = localStorage.getItem(ANALYSIS_VIEW_KEY);
  if (!raw) {
    return;
  }
  try {
    const parsed = JSON.parse(raw);
    if (parsed?.form?.symbol) {
      form.symbol = parsed.form.symbol;
    }
    if (parsed?.form?.market) {
      form.market = parsed.form.market;
    }
    if (parsed?.lookback_period) {
      form.lookback_period = parsed.lookback_period;
    }
    if (parsed?.bollinger_window) {
      form.bollinger_window = parsed.bollinger_window;
    }
    if (parsed?.selected_preset_id) {
      selectedPresetId.value = parsed.selected_preset_id;
    } else {
      syncPresetFromCustom();
    }
    analysisResults.value = Array.isArray(parsed?.results) ? parsed.results : [];
  } catch {
    localStorage.removeItem(ANALYSIS_VIEW_KEY);
  }
}

function formatPrice(value) {
  return value == null ? "-" : Number(value).toFixed(2);
}

function formatPercent(value) {
  return value == null ? "-" : `${Number(value).toFixed(2)}%`;
}

function formatLookback(value) {
  return LOOKBACK_OPTIONS.find((item) => item.value === value)?.label || value;
}

function formatWindow(value) {
  return WINDOW_OPTIONS.find((item) => item.value === value)?.label || value;
}

function applyPreset(preset) {
  selectedPresetId.value = preset.id;
  form.lookback_period = preset.lookback;
  form.bollinger_window = preset.window;
  saveAnalysisView();
}

function syncPresetFromCustom() {
  const matched = STRATEGY_PRESETS.find((item) => item.lookback === form.lookback_period && item.window === form.bollinger_window);
  selectedPresetId.value = matched?.id || "";
  saveAnalysisView();
}

function priceClass(value) {
  if (value == null) return "";
  if (Number(value) > 0) return "positive";
  if (Number(value) < 0) return "negative";
  return "";
}

async function fetchNews(reset = false) {
  newsError.value = "";
  if (reset) {
    newsPage.value = 1;
    hasMoreNews.value = true;
  }
  loadingNews.value = true;
  try {
    const { data } = await api.get("/market/news", { params: { limit: newsPageSize, page_no: newsPage.value } });
    news.value = data;
    hasMoreNews.value = data.length === newsPageSize;
  } catch (err) {
    news.value = [];
    hasMoreNews.value = false;
    newsError.value = err.response?.data?.detail || "新闻拉取失败";
  } finally {
    loadingNews.value = false;
  }
}

async function loadMoreNews() {
  if (loadingMoreNews.value || !hasMoreNews.value) {
    return;
  }
  loadingMoreNews.value = true;
  newsError.value = "";
  try {
    const nextPage = newsPage.value + 1;
    const { data } = await api.get("/market/news", { params: { limit: newsPageSize, page_no: nextPage } });
    news.value = [...news.value, ...data];
    newsPage.value = nextPage;
    hasMoreNews.value = data.length === newsPageSize;
  } catch (err) {
    newsError.value = err.response?.data?.detail || "新闻拉取失败";
  } finally {
    loadingMoreNews.value = false;
  }
}

async function fetchHistory() {
  const { data } = await api.get("/analysis/history");
  history.value = data;
}

function resetLocalPage() {
  localPage.value = Math.min(localPage.value, localTotalPages.value);
}

function openWatchlistModal() {
  watchlistError.value = "";
  watchlistModalOpen.value = true;
}

function closeWatchlistModal() {
  if (submittingWatchlist.value) {
    return;
  }
  watchlistError.value = "";
  watchlistModalOpen.value = false;
}

async function fetchItems() {
  const { data } = await api.get("/watchlist");
  watchlistItems.value = data;
  resetLocalPage();
}

async function addItem() {
  submittingWatchlist.value = true;
  watchlistError.value = "";
  try {
    await api.post("/watchlist", watchlistForm);
    watchlistForm.symbol = "";
    localCollapsed.value = false;
    closeWatchlistModal();
    await fetchItems();
  } catch (err) {
    watchlistError.value = err.response?.data?.detail || "添加失败";
  } finally {
    submittingWatchlist.value = false;
  }
}

async function refreshOne(id) {
  refreshingItemId.value = id;
  watchlistError.value = "";
  try {
    await api.post(`/watchlist/${id}/refresh`);
    await fetchItems();
  } catch (err) {
    watchlistError.value = err.response?.data?.detail || "刷新失败";
  } finally {
    refreshingItemId.value = null;
  }
}

async function refreshAll() {
  refreshingAllWatchlist.value = true;
  watchlistError.value = "";
  try {
    await api.post("/watchlist/refresh-all");
    localCollapsed.value = false;
    await fetchItems();
  } catch (err) {
    watchlistError.value = err.response?.data?.detail || "批量刷新失败，请尝试单独刷新";
  } finally {
    refreshingAllWatchlist.value = false;
  }
}

async function removeItem(id) {
  await api.delete(`/watchlist/${id}`);
  await fetchItems();
}

async function runAnalysis() {
  loadingAnalysis.value = true;
  analysisError.value = "";
  analysisHint.value = "";
  try {
    const { data } = await api.post("/analysis/run", {
      symbol: form.symbol,
      market: form.market,
      lookback_period: form.lookback_period,
      bollinger_window: form.bollinger_window,
      strategies: ["bollinger_mean_reversion"]
    });
    analysisResults.value = data.results;
    analysisHint.value = data.cached ? `今日 ${formatLookback(form.lookback_period)} + ${formatWindow(form.bollinger_window)} 已有历史结果，本次直接使用数据库历史数据。` : `当前页面已记录你的参数偏好：${formatLookback(form.lookback_period)} + ${formatWindow(form.bollinger_window)}。`;
    saveAnalysisView();
    await fetchHistory();
  } catch (err) {
    analysisError.value = err.response?.data?.detail || err.response?.data?.message || "分析失败";
  } finally {
    loadingAnalysis.value = false;
  }
}

function clearAnalysis() {
  analysisResults.value = [];
  analysisError.value = "";
  analysisHint.value = "";
  saveAnalysisView();
}

function reviewHistory(item) {
  form.symbol = item.symbol;
  form.market = item.market;
  form.lookback_period = item.lookback_period || item.request_payload?.lookback_period || "2y";
  form.bollinger_window = item.bollinger_window || item.request_payload?.bollinger_window || "20d";
  analysisError.value = "";
  syncPresetFromCustom();
  analysisHint.value = `当前展示的是 ${formatLookback(form.lookback_period)} + ${formatWindow(form.bollinger_window)} 的历史分析结果。`;
  analysisResults.value = [
    {
      key: item.strategy_key,
      title: STRATEGY_TITLES[item.strategy_key] || item.strategy_key,
      payload: item.result_payload
    }
  ];
  saveAnalysisView();
}

onMounted(async () => {
  restoreAnalysisView();
  await Promise.all([fetchNews(true), fetchHistory(), fetchItems()]);
});
</script>
