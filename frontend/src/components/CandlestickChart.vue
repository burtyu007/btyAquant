<template>
  <div class="kline-chart">
    <svg v-if="normalized.length" viewBox="0 0 640 240" preserveAspectRatio="none">
      <g v-for="(item, index) in normalized" :key="item.date">
        <line
          :x1="item.x"
          :x2="item.x"
          :y1="item.highY"
          :y2="item.lowY"
          :stroke="item.rising ? '#0b7a75' : '#b54738'"
          stroke-width="2"
          stroke-linecap="round"
        />
        <rect
          :x="item.x - candleWidth / 2"
          :y="Math.min(item.openY, item.closeY)"
          :width="candleWidth"
          :height="Math.max(4, Math.abs(item.closeY - item.openY))"
          :fill="item.rising ? 'rgba(11,122,117,0.75)' : 'rgba(181,71,56,0.75)'"
          rx="3"
        />
      </g>
    </svg>
    <div v-else class="empty-state compact">暂无 K 线数据</div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  items: { type: Array, default: () => [] }
});

const width = 640;
const height = 240;
const padding = 22;

const priceRange = computed(() => {
  if (!props.items.length) return { min: 0, max: 1 };
  const lows = props.items.map((item) => Number(item.low));
  const highs = props.items.map((item) => Number(item.high));
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const gap = Math.max((max - min) * 0.08, 0.5);
  return { min: min - gap, max: max + gap };
});

const candleWidth = computed(() => {
  if (!props.items.length) return 8;
  return Math.max(6, Math.min(14, (width - padding * 2) / props.items.length - 4));
});

const normalized = computed(() => {
  if (!props.items.length) return [];
  const step = (width - padding * 2) / Math.max(props.items.length - 1, 1);
  const range = priceRange.value.max - priceRange.value.min || 1;
  const toY = (value) => height - padding - ((Number(value) - priceRange.value.min) / range) * (height - padding * 2);
  return props.items.map((item, index) => ({
    ...item,
    x: padding + step * index,
    highY: toY(item.high),
    lowY: toY(item.low),
    openY: toY(item.open),
    closeY: toY(item.close),
    rising: Number(item.close) >= Number(item.open)
  }));
});
</script>
