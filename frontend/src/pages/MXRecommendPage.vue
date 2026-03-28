<template>
  <AppShell title="只MX推荐" subtitle="这里集中处理 MX 东财智选与实时追踪，方便和量化回归分析分开使用。">
    <section class="panel history-panel">
      <div class="panel-head">
        <div>
          <div class="panel-kicker">智能推荐</div>
          <h3>MX 东财智选</h3>
        </div>
        <button class="ghost-btn small" @click="fetchRecommendations(recommendationPage, true)">刷新</button>
      </div>

      <form class="analysis-form" @submit.prevent="fetchRecommendations(1)">
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
              <th>最新价</th>
              <th>涨跌幅</th>
              <th>行业</th>
              <th>概念</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in recommendations" :key="`${item.market}-${item.symbol}`">
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
    </section>

    <section class="panel hero-panel">
      <div class="panel-head">
        <div>
          <div class="panel-kicker">实时追踪</div>
          <h3>MX 实时追踪</h3>
        </div>
        <button class="ghost-btn small" @click="fetchTracker">刷新追踪</button>
      </div>

      <form class="analysis-form" @submit.prevent="fetchTracker">
        <label>
          <span>市场</span>
          <select v-model="trackerForm.market">
            <option value="a">A股</option>
            <option value="hk">港股</option>
          </select>
        </label>
        <label>
          <span>股票代码</span>
          <input v-model="trackerForm.symbol" type="text" placeholder="例如 600036 或 00700" />
        </label>
        <button class="primary-btn" :disabled="loadingTracker">{{ loadingTracker ? "追踪中..." : "开始追踪" }}</button>
      </form>

      <p v-if="trackerError" class="error-text">{{ trackerError }}</p>
      <div v-if="tracker" class="tracker-layout">
        <div class="panel-head tracker-head">
          <div>
            <div class="panel-kicker">{{ tracker.market === "a" ? "A股" : "港股" }}</div>
            <h3>{{ tracker.display_name }} {{ tracker.symbol }}</h3>
          </div>
          <div class="badge">{{ tracker.quote.timestamp || "实时" }}</div>
        </div>

        <div class="stats-grid">
          <div class="stat-box">
            <span>最新价</span>
            <strong>{{ formatPrice(tracker.quote.price) }}</strong>
          </div>
          <div class="stat-box">
            <span>开盘价</span>
            <strong>{{ formatPrice(tracker.quote.open) }}</strong>
          </div>
          <div class="stat-box">
            <span>当日最高</span>
            <strong>{{ formatPrice(tracker.quote.high) }}</strong>
          </div>
          <div class="stat-box">
            <span>当日最低</span>
            <strong>{{ formatPrice(tracker.quote.low) }}</strong>
          </div>
        </div>

        <div class="tracker-chart-grid">
          <article class="sub-card">
            <h4>日 K</h4>
            <CandlestickChart :items="tracker.daily_kline" />
          </article>
          <article class="sub-card">
            <h4>周 K</h4>
            <CandlestickChart :items="tracker.weekly_kline" />
          </article>
          <article class="sub-card">
            <h4>月 K</h4>
            <CandlestickChart :items="tracker.monthly_kline" />
          </article>
        </div>

        <div class="tracker-info-grid">
          <article class="sub-card">
            <h4>基础数据</h4>
            <ul class="plain-list">
              <li>昨收参考：{{ formatPrice(tracker.quote.close) }}</li>
              <li>成交量：{{ formatLarge(tracker.quote.volume) }}</li>
              <li>市盈率 TTM：{{ tracker.fundamentals.valuation?.pe_ttm ?? "-" }}</li>
              <li>市净率 PB：{{ tracker.fundamentals.valuation?.pb_mrq ?? "-" }}</li>
              <li>近 3 年 PE 分位：{{ tracker.fundamentals.valuation?.pe_percentile_3y ?? "-" }}</li>
            </ul>
          </article>
          <article class="sub-card">
            <h4>基本面分析</h4>
            <ul class="plain-list">
              <li>最新报表：{{ tracker.fundamentals.profitability?.report_date || "-" }}</li>
              <li>营业总收入：{{ formatLarge(tracker.fundamentals.profitability?.revenue) }}</li>
              <li>归母净利润：{{ formatLarge(tracker.fundamentals.profitability?.net_profit) }}</li>
              <li>ROE：{{ tracker.fundamentals.profitability?.roe ?? "-" }}</li>
              <li>利润同比：{{ tracker.fundamentals.profitability?.profit_yoy ?? "-" }}</li>
            </ul>
          </article>
        </div>

        <article class="sub-card">
          <h4>追踪结论</h4>
          <ul class="plain-list">
            <li v-for="item in tracker.analysis_points" :key="item">{{ item }}</li>
          </ul>
        </article>
      </div>
    </section>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import AppShell from "../components/AppShell.vue";
import CandlestickChart from "../components/CandlestickChart.vue";
import api from "../services/api";
import { useSessionUser } from "../services/session";

const currentUser = useSessionUser();
const recommendations = ref([]);
const recommendationError = ref("");
const recommendationLogic = ref("");
const recommendationKeyword = ref("东财智选 推荐");
const recommendationPage = ref(1);
const recommendationPageSize = 20;
const recommendationTotalCount = ref(0);
const loadingRecommendations = ref(false);

const tracker = ref(null);
const trackerError = ref("");
const loadingTracker = ref(false);
const trackerForm = reactive({ symbol: "600036", market: "a" });

const recommendationTotalPages = computed(() =>
  Math.max(1, Math.ceil(recommendationTotalCount.value / recommendationPageSize))
);

function formatPrice(value) {
  return value == null ? "-" : Number(value).toFixed(2);
}

function formatPercent(value) {
  return value == null ? "-" : `${Number(value).toFixed(2)}%`;
}

function formatLarge(value) {
  if (value == null || value === "") return "-";
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  if (Math.abs(amount) >= 1e8) return `${(amount / 1e8).toFixed(2)} 亿`;
  if (Math.abs(amount) >= 1e4) return `${(amount / 1e4).toFixed(2)} 万`;
  return amount.toFixed(2);
}

function priceClass(value) {
  if (value == null) return "";
  if (Number(value) > 0) return "positive";
  if (Number(value) < 0) return "negative";
  return "";
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
  if (page < 1 || page > recommendationTotalPages.value || page === recommendationPage.value) return;
  fetchRecommendations(page);
}

async function fetchTracker() {
  trackerError.value = "";
  if (!currentUser.value?.has_mx_api_key) {
    tracker.value = null;
    trackerError.value = "请先在用户管理里配置当前用户的 MX Key，再使用实时追踪。";
    return;
  }
  loadingTracker.value = true;
  try {
    const { data } = await api.get("/market/tracker", { params: trackerForm });
    tracker.value = data;
  } catch (err) {
    tracker.value = null;
    trackerError.value = err.response?.data?.detail || "实时追踪拉取失败";
  } finally {
    loadingTracker.value = false;
  }
}

onMounted(async () => {
  await Promise.all([fetchRecommendations(), fetchTracker()]);
});
</script>
