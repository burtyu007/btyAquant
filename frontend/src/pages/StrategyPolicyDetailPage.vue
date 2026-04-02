<template>
  <AppShell :title="detail?.name || '策略详情'" subtitle="这里会展示策略的 README.md 使用说明，以及按统一结构读取的 results.json 结果。">
    <template #header-extra>
      <button class="ghost-btn" @click="goBack">返回列表</button>
    </template>

    <section class="panel">
      <div class="panel-head">
        <div>
          <div class="panel-kicker">策略详情</div>
          <h3>{{ detail?.name || `策略 #${route.params.id}` }}</h3>
          <p class="note">脚本目录、说明文档和结果文件都来自 `policy_files` 与本地 `policy/&lt;folder&gt;` 目录联动。</p>
        </div>
      </div>

      <p v-if="loading" class="empty-state">正在读取策略详情...</p>
      <p v-else-if="error" class="error-text">{{ error }}</p>

      <template v-else-if="detail">
        <div class="strategy-detail-grid">
          <article class="sub-card">
            <h4>目录信息</h4>
            <ul class="plain-list">
              <li>策略目录：{{ detail.folder || "-" }}</li>
              <li>脚本文件：{{ detail.path }}</li>
              <li>README：{{ detail.readme }} / {{ detail.readme_exists ? "已找到" : "未找到" }}</li>
              <li>结果文件：{{ detail.results || "-" }} / {{ detail.results_exists ? "已找到" : "未找到" }}</li>
              <li>创建人：{{ detail.created_user_name || `用户#${detail.created_user_id}` }}</li>
              <li>更新时间：{{ formatDateTime(detail.updated_at) }}</li>
            </ul>
          </article>
          <article class="sub-card">
            <h4>结果摘要</h4>
            <ul class="plain-list">
              <li>结果记录数：{{ detail.result_count }}</li>
              <li>列表展示字段：{{ detail.list_show_fields.join(", ") || "-" }}</li>
              <li>脚本语言：{{ detail.script_language.toUpperCase() }}</li>
              <li>结果类型：{{ detail.results_format }}</li>
            </ul>
          </article>
        </div>

        <section class="panel nested-panel">
          <div class="panel-head">
            <div>
              <div class="panel-kicker">README.md</div>
              <h3>脚本使用说明</h3>
            </div>
            <button
              v-if="detail.readme_content"
              class="ghost-btn small"
              type="button"
              @click="readmeExpanded = !readmeExpanded"
            >
              {{ readmeExpanded ? "收起说明" : "展开说明" }}
            </button>
          </div>
          <div v-if="!detail.readme_content" class="empty-state">当前策略没有可读的 README.md。</div>
          <div v-else-if="!readmeExpanded" class="collapsed-tip">README 已默认收起，点击右上角“展开说明”查看脚本使用文档。</div>
          <article v-else class="markdown-body" v-html="renderedMarkdown"></article>
        </section>

        <section class="panel nested-panel">
          <div class="panel-head">
            <div>
              <div class="panel-kicker">Results</div>
              <h3>结果数据</h3>
              <p class="note">`fields` 负责字段中文名映射，`list_show_fields` 只控制结果列表列，其余字段只在结果详情里展示。</p>
            </div>
          </div>

          <div v-if="detail.results_format === 'html' && detail.results_html_content" class="html-result-view">
            <iframe
              class="html-result-frame"
              :srcdoc="detail.results_html_content"
              title="HTML Results"
            />
          </div>
          <div v-else-if="!detail.results_data?.lists?.length" class="empty-state">当前策略还没有结果数据。</div>
          <template v-else>
            <div class="strategy-result-columns">
              <span v-for="column in detail.list_display_columns" :key="column.key" class="strategy-column-chip">
                {{ column.label }}
              </span>
            </div>
            <div class="strategy-results-wrap">
              <table class="data-table strategy-results-table">
                <thead>
                  <tr>
                    <th v-for="column in detail.list_display_columns" :key="column.key">{{ column.label }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, rowIndex) in detail.results_data.lists"
                    :key="row.code || row.rank || rowIndex"
                    :class="{ active: rowIndex === selectedResultIndex }"
                    @click="selectedResultIndex = rowIndex"
                  >
                    <td v-for="column in detail.list_display_columns" :key="column.key">
                      <div class="strategy-cell-content">{{ formatCell(row[column.key]) }}</div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="selectedResult" class="strategy-result-detail">
              <div class="panel-head">
                <div>
                  <div class="panel-kicker">Result Detail</div>
                  <h3>结果详情</h3>
                  <p class="note">当前选中第 {{ selectedResultIndex + 1 }} 条，展示该条结果的完整字段内容。</p>
                </div>
              </div>

              <div class="result-detail-grid">
                <div
                  v-for="column in detail.detail_display_columns"
                  :key="column.key"
                  class="result-detail-item"
                >
                  <span class="result-detail-label">{{ column.label }}</span>
                  <div class="result-detail-value">
                    <template v-if="Array.isArray(selectedResult[column.key])">
                      <div v-if="!selectedResult[column.key].length" class="muted">-</div>
                      <div v-else class="result-detail-array">
                        <article
                          v-for="(item, itemIndex) in selectedResult[column.key]"
                          :key="`${column.key}-${itemIndex}`"
                          class="result-detail-array-item"
                        >
                          <pre>{{ formatStructuredValue(item) }}</pre>
                        </article>
                      </div>
                    </template>
                    <template v-else-if="isObjectValue(selectedResult[column.key])">
                      <pre>{{ formatStructuredValue(selectedResult[column.key]) }}</pre>
                    </template>
                    <template v-else>
                      {{ formatCell(selectedResult[column.key]) }}
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </section>
      </template>
    </section>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { marked } from "marked";
import { useRoute, useRouter } from "vue-router";
import AppShell from "../components/AppShell.vue";
import api from "../services/api";

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const error = ref("");
const detail = ref(null);
const readmeExpanded = ref(false);
const selectedResultIndex = ref(0);

marked.setOptions({
  gfm: true,
  breaks: true,
});

const renderedMarkdown = computed(() => String(marked.parse(detail.value?.readme_content || "")));
const selectedResult = computed(() => detail.value?.results_data?.lists?.[selectedResultIndex.value] || null);

function formatDateTime(value) {
  return value ? value.slice(0, 19).replace("T", " ") : "-";
}

function formatCell(value) {
  if (value == null || value === "") return "-";
  if (Array.isArray(value) || typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function isObjectValue(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function formatStructuredValue(value) {
  return JSON.stringify(value, null, 2);
}

function goBack() {
  router.push({ name: "strategy-picker" });
}

async function fetchDetail() {
  loading.value = true;
  error.value = "";
  detail.value = null;
  readmeExpanded.value = false;
  selectedResultIndex.value = 0;
  try {
    const { data } = await api.get(`/policies/${route.params.id}`);
    detail.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "策略详情读取失败";
  } finally {
    loading.value = false;
  }
}

watch(() => route.params.id, fetchDetail);
onMounted(fetchDetail);
</script>
