<script setup>
import { ref, onMounted } from 'vue'
import EvalDatasetTab from '@/views/eval/EvalDatasetTab.vue'
import EvalRunTab from '@/views/eval/EvalRunTab.vue'
import EvalHistoryTab from '@/views/eval/EvalHistoryTab.vue'


// ── tabs ──────────────────────────────────────────────────────────────────────
const activeTab = ref('dataset')

// References to child components
const datasetTabRef = ref()
const historyTabRef = ref()

// Handle run completion - refresh history
function handleRunCompleted() {
  if (historyTabRef.value?.loadRuns) {
    historyTabRef.value.loadRuns()
  }
}
</script>

<template>
  <div class="eval-view">
    <!-- Header -->
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">Eval</h1>
        <span class="page-count">{{ datasetTabRef?.dataset?.length || 0 }} вопросов</span>
      </div>

      <!-- Tabs -->
      <div class="tabs">
        <button :class="['tab-btn', { active: activeTab === 'dataset' }]" @click="activeTab = 'dataset'">
          Датасет
        </button>
        <button :class="['tab-btn', { active: activeTab === 'run' }]" @click="activeTab = 'run'">
          Запустить
        </button>
        <button :class="['tab-btn', { active: activeTab === 'history' }]" @click="activeTab = 'history'">
          История
          <span v-if="historyTabRef?.runs?.length" class="tab-count">{{ historyTabRef.runs.length }}</span>
        </button>
      </div>
    </div>

    <!-- Tab content -->
    <div class="tab-content">
      <EvalDatasetTab
        v-show="activeTab === 'dataset'"
        ref="datasetTabRef"
      />
      <EvalRunTab
        v-show="activeTab === 'run'"
        @run-completed="handleRunCompleted"
      />
      <EvalHistoryTab
        v-show="activeTab === 'history'"
        ref="historyTabRef"
      />
    </div>
  </div>
</template>

<style scoped>
.eval-view {
  padding: var(--sp-6) var(--sp-8);
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-6);
  flex-wrap: wrap;
  gap: var(--sp-4);
}

.page-title-block {
  display: flex;
  align-items: baseline;
  gap: var(--sp-4);
}

.page-title {
  font-size: var(--fs-24);
  font-weight: var(--fw-bold);
  color: var(--fg-1);
  margin: 0;
}

.page-count {
  font-size: var(--fs-13);
  color: var(--fg-3);
  background: var(--bg-panel-2);
  padding: 2px 8px;
  border-radius: var(--rad-md);
  white-space: nowrap;
}

.tabs {
  display: flex;
  gap: var(--sp-1);
  background: var(--bg-panel-2);
  padding: 4px;
  border-radius: var(--rad-lg);
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-4);
  border: none;
  background: transparent;
  color: var(--fg-3);
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  border-radius: var(--rad-md);
  cursor: pointer;
  transition: all var(--dur-fast);
  white-space: nowrap;
}

.tab-btn:hover {
  color: var(--fg-2);
  background: var(--bg-hover);
}

.tab-btn.active {
  color: var(--fg-1);
  background: var(--bg-panel);
  box-shadow: 0 1px 3px var(--shadow-1);
  font-weight: var(--fw-semibold);
}

.tab-count {
  font-size: var(--fs-11);
  background: var(--accent);
  color: white;
  padding: 2px 6px;
  border-radius: var(--rad-full);
  min-width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: var(--fw-bold);
}

.tab-content {
  /* Tab content is handled by child components */
}

/* Global styles that need to be available for child components */
:deep(.table-wrap) {
  border-radius: var(--rad-lg);
  overflow: hidden;
  border: 1px solid var(--border-1);
  background: var(--bg-panel);
}

:deep(.log-table) {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-13);
}

:deep(.log-table th) {
  background: var(--bg-panel-2);
  color: var(--fg-2);
  font-weight: var(--fw-semibold);
  padding: var(--sp-3);
  text-align: left;
  border-bottom: 1px solid var(--border-1);
  font-size: var(--fs-12);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

:deep(.log-table td) {
  padding: var(--sp-3);
  border-bottom: 1px solid var(--border-1);
  vertical-align: top;
}

:deep(.log-row) {
  transition: background var(--dur-fast);
}

:deep(.log-row:hover) {
  background: var(--bg-hover);
}

:deep(.clickable-row) {
  cursor: pointer;
}

:deep(.clickable-row.row-open) {
  background: var(--bg-panel-2);
}

:deep(.cell-num) {
  font-variant-numeric: tabular-nums;
  color: var(--fg-3);
  font-size: var(--fs-12);
}

:deep(.cell-q) {
  color: var(--fg-1);
  line-height: 1.4;
}

:deep(.cell-score) {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

:deep(.latency) {
  font-size: var(--fs-12);
}

:deep(.answer-row) {
  background: var(--bg-panel-2);
}

:deep(.answer-row td) {
  padding: var(--sp-4);
}

:deep(.panel) {
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-4);
}
</style>