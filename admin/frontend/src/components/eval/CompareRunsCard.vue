<script setup>
import { ref, inject } from 'vue'
import { api } from '@/api/index.js'
import AjaxFrog from '@/components/AjaxFrog.vue'
import CompareSummaryHeader from './CompareSummaryHeader.vue'
import CompareTable from './CompareTable.vue'

const toast = inject('toast')

const props = defineProps({
  runs: {
    type: Array,
    required: true
  }
})

const compareData = ref(null)
const compareLoading = ref(false)

async function compareLastTwo() {
  if (props.runs.length < 2) return
  // runs come sorted DESC (newest first); compare goes A→B = old→new
  const runA = props.runs[1]
  const runB = props.runs[0]
  compareLoading.value = true
  compareData.value = null
  try {
    const res = await api.compareEvalRuns(runA.id, runB.id)
    compareData.value = res.data
  } catch {
    toast('Ошибка сравнения', 'error')
  } finally {
    compareLoading.value = false
  }
}

function handleClose() {
  compareData.value = null
}
</script>

<template>
  <div class="compare-card">
    <!-- Compare button when no data yet -->
    <div v-if="!compareData" class="compare-button-section">
      <button @click="compareLastTwo" :disabled="compareLoading" class="btn btn-secondary">
        <AjaxFrog v-if="compareLoading" text="" size="14px" />
        <span v-else>Сравнить последние 2</span>
      </button>
    </div>

    <!-- Compare results when data loaded -->
    <div v-else class="compare-results">
      <CompareSummaryHeader
        :run-a="compareData.run_a"
        :run-b="compareData.run_b"
        :summary="compareData.summary"
        @close="handleClose"
      />

      <CompareTable :questions="compareData.questions" />
    </div>
  </div>
</template>

<style scoped>
.compare-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-4);
}

.compare-button-section {
  text-align: left;
}

.btn {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-panel);
  color: var(--fg-1);
  font-size: var(--fs-13);
  font-weight: var(--fw-semibold);
  cursor: pointer;
  transition: all var(--dur-fast);
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
}

.btn-secondary {
  background: var(--bg-panel-2);
  border-color: var(--border-2);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--accent);
  color: var(--accent);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.compare-results {
  margin-top: var(--sp-4);
}
</style>