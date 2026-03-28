<template>
  <section class="panel strategy-card">
    <div class="panel-head">
      <div>
        <div class="panel-kicker">{{ result.title }}</div>
        <h3>{{ payload.strategy_name }}</h3>
      </div>
      <div class="badge">{{ payload.market_label }} {{ payload.symbol }} · {{ payload.lookback_period_label || "2年" }} · {{ payload.bollinger_window_label || "20日" }}</div>
    </div>

    <div class="stats-grid">
      <div class="stat-box">
        <span>{{ payload.summary.close_label || "最新收盘" }}</span>
        <strong>{{ payload.summary.close }}</strong>
      </div>
      <div class="stat-box">
        <span>下轨低吸</span>
        <strong>{{ payload.summary.buy_reference }}</strong>
      </div>
      <div class="stat-box">
        <span>中轨止盈</span>
        <strong>{{ payload.summary.first_take_profit }}</strong>
      </div>
      <div class="stat-box">
        <span>上轨强止盈</span>
        <strong>{{ payload.summary.strong_take_profit }}</strong>
      </div>
    </div>

    <div class="insight-grid">
      <article class="sub-card">
        <h4>策略判断</h4>
        <p>{{ payload.summary.state }}</p>
        <div class="muted">
          购买建议：{{ payload.summary.recommendation.action }}
        </div>
        <div v-if="payload.summary.recommendation.risk_level" class="muted">
          风险星级：{{ payload.summary.recommendation.risk_level }}
        </div>
        <div class="muted">Z-Score：{{ payload.summary.zscore }}</div>
      </article>
      <article class="sub-card">
        <h4>回测摘要</h4>
        <ul class="plain-list">
          <li>交易次数：{{ payload.backtest.trade_count }}</li>
          <li>总收益率：{{ payload.backtest.total_return_pct }}%</li>
          <li>胜率：{{ payload.backtest.win_rate }}%</li>
          <li>盈亏比：{{ payload.backtest.profit_factor }}</li>
          <li>最大回撤：{{ payload.backtest.max_drawdown_pct }}%</li>
        </ul>
      </article>
    </div>

    <div class="table-grid">
      <article class="sub-card">
        <h4>最近下轨买点</h4>
        <div v-if="!payload.buy_signals.length" class="empty-state compact">暂无明显买点</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>日期</th>
              <th>收盘</th>
              <th>下轨</th>
              <th>中轨</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in payload.buy_signals" :key="item.trade_date">
              <td>{{ item.trade_date }}</td>
              <td>{{ item.close }}</td>
              <td>{{ item.lower_band }}</td>
              <td>{{ item.middle_band }}</td>
            </tr>
          </tbody>
        </table>
      </article>

      <article class="sub-card">
        <h4>最近回测交易</h4>
        <div v-if="!payload.recent_trades.length" class="empty-state compact">暂无回测交易</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>买入时间</th>
              <th>卖出时间</th>
              <th>净收益</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in payload.recent_trades" :key="item.entry_time + item.exit_time">
              <td>{{ item.entry_time.slice(0, 10) }}</td>
              <td>{{ item.exit_time.slice(0, 10) }}</td>
              <td :class="item.net_pnl >= 0 ? 'positive' : 'negative'">{{ item.net_pnl }}</td>
            </tr>
          </tbody>
        </table>
      </article>
    </div>

    <div class="note">{{ payload.data_notes }}</div>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  result: { type: Object, required: true }
});

const payload = computed(() => props.result.payload);
</script>
