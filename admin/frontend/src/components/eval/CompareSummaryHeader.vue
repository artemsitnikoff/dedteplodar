<script setup>
import {
  fmtScore, fmtQuality, fmtDeltaQuality,
  deltaQualityColor
} from '@/utils/format.js'

const props = defineProps({
  runA: {
    type: Object,
    required: true
  },
  runB: {
    type: Object,
    required: true
  },
  summary: {
    type: Object,
    required: true
  }
})

defineEmits(['close'])
</script>

<template>
  <div class="compare-header">
    <div class="compare-runs-label">
      <span class="run-label-a">#{{ runA.id }}</span>
      <span class="compare-arrow">→</span>
      <span class="run-label-b">#{{ runB.id }}</span>
    </div>
    <button @click="$emit('close')" class="close-btn" title="Закрыть сравнение">✕</button>
  </div>

  <div class="compare-summary">
    <div v-if="summary.quality_a !== null && summary.quality_b !== null" class="compare-stat-row">
      <span>Quality:</span>
      <span>{{ fmtQuality(summary.quality_a) }}</span>
      <span class="compare-sep">→</span>
      <span>{{ fmtQuality(summary.quality_b) }}</span>
      <span v-if="summary.quality_delta !== null"
            :class="['compare-stat', deltaQualityColor(summary.quality_delta)]">
        ({{ fmtDeltaQuality(summary.quality_delta) }})
      </span>
    </div>
    <div class="compare-stat-row">
      <span>Avg score:</span>
      <span>{{ fmtScore(summary.avg_score_a) }}</span>
      <span class="compare-sep">→</span>
      <span>{{ fmtScore(summary.avg_score_b) }}</span>
    </div>
    <div class="compare-stat-row compare-counts">
      <span class="improved">улучшилось: {{ summary.improved }}</span>
      <span class="degraded">ухудшилось: {{ summary.degraded }}</span>
      <span>тип изменился: {{ summary.type_changes }}</span>
    </div>
  </div>
</template>

<style scoped>
.compare-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--sp-3);
}

.compare-runs-label {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--fg-3);
}

.run-label-a { color: var(--fg-2); }
.run-label-b { color: var(--fg-1); font-weight: var(--fw-medium); }
.compare-arrow { color: var(--fg-4); }

.close-btn {
  border: 1px solid var(--border-1);
  background: transparent;
  color: var(--fg-3);
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  padding: 2px 6px;
  border-radius: var(--rad-sm);
  cursor: pointer;
  white-space: nowrap;
}

.close-btn:hover {
  border-color: var(--ark-red-600);
  color: var(--ark-red-600);
  background: var(--ark-red-100);
}

.compare-summary {
  background: var(--bg-panel-2);
  border-radius: var(--rad-md);
  padding: var(--sp-3);
  margin-bottom: var(--sp-4);
}

.compare-stat-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-13);
}

.compare-sep { color: var(--fg-4); }
.compare-stat { font-size: var(--fs-13); color: var(--fg-2); }

.compare-counts .improved { color: var(--ark-green-600); font-weight: var(--fw-semibold); }
.compare-counts .degraded { color: var(--ark-red-600); font-weight: var(--fw-semibold); }
</style>