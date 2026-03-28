<template>
  <aside class="panel news-panel">
    <div class="panel-head">
      <div>
        <div class="panel-kicker">消息库新闻流</div>
        <h3>财经热点</h3>
      </div>
      <div class="news-actions">
        <button class="ghost-btn small" @click="toggleLock">{{ locked ? "解锁" : "锁定" }}</button>
        <button class="ghost-btn small" @click="$emit('refresh')">刷新</button>
      </div>
    </div>

    <div v-if="loading" class="empty-state">正在拉取入库后的财经热点...</div>
    <div v-else-if="error" class="empty-state error-text">{{ error }}</div>
    <div v-else-if="!items.length" class="empty-state">暂时没有拿到新闻数据。</div>
    <template v-else-if="locked">
      <div class="news-lock-list">
        <button
          v-for="(item, index) in items"
          :key="item.title + item.date"
          class="news-title-button"
          @click="openFromLocked(index)"
        >
          <span class="news-index">{{ String(index + 1).padStart(2, "0") }}</span>
          <span class="news-title-mini">{{ item.title }}</span>
        </button>
      </div>
      <div class="pagination-bar news-pagination">
        <span>默认展示 20 条标题，解锁后可瀑布流继续加载。</span>
      </div>
    </template>
    <template v-else>
      <div class="news-waterfall">
        <article
          v-for="(item, index) in items"
          :key="item.title + item.date"
          class="news-item waterfall-card"
          :class="{ open: openIndexes.has(index) }"
          @click="toggleItem(index)"
        >
          <div class="news-meta">{{ item.date || "最新" }}<span v-if="item.source"> · {{ item.source }}</span></div>
          <h4>{{ item.title }}</h4>
          <p v-if="openIndexes.has(index)">{{ item.content }}</p>
        </article>
      </div>
      <div v-if="hasMore || loadingMore" class="pagination-bar news-pagination">
        <span>{{ loadingMore ? "正在加载更多..." : "继续下拉新闻流" }}</span>
        <button class="ghost-btn small" :disabled="loadingMore" @click="$emit('load-more')">
          {{ loadingMore ? "加载中..." : "加载更多" }}
        </button>
      </div>
    </template>
  </aside>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  items: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  loadingMore: { type: Boolean, default: false },
  hasMore: { type: Boolean, default: false },
  error: { type: String, default: "" }
});

defineEmits(["refresh", "load-more"]);

const locked = ref(true);
const openIndexes = ref(new Set());

function toggleLock() {
  locked.value = !locked.value;
  if (locked.value) {
    openIndexes.value = new Set();
  }
}

function openFromLocked(index) {
  locked.value = false;
  openIndexes.value = new Set([index]);
}

function toggleItem(index) {
  const next = new Set(openIndexes.value);
  if (next.has(index)) {
    next.delete(index);
  } else {
    next.add(index);
  }
  openIndexes.value = next;
}
</script>
