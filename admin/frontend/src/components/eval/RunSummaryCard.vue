<script setup>
import {
  fmtScore, fmtDelta, fmtQuality, fmtDeltaQuality, fmtPct,
  qualityColor, deltaColor, deltaQualityColor
} from '@/utils/format.js'

const props = defineProps({
  summary: Object,
  title: { type: String, default: 'Итоги прогона' }
})
</script>

<template>
  <div v-if="summary" class="run-summary">
    <div class="run-summary-header">{{ title }}</div>
    <div class="run-summary-stats">
      <div class="summary-group">
        <div class="summary-row">
          <span class="summary-label">Качество (0-100):</span>
          <div class="summary-values">
            <span :class="['summary-val', qualityColor(summary.quality)]">{{ fmtQuality(summary.quality) }}</span>
            <span v-if="summary.deltaQuality !== null && summary.deltaQuality !== undefined"
                  :class="['summary-delta', deltaQualityColor(summary.deltaQuality)]">
              {{ fmtDeltaQuality(summary.deltaQuality) }}
            </span>
          </div>
        </div>
        <div class="summary-row">
          <span class="summary-label">Средний score:</span>
          <div class="summary-values">
            <span :class="['summary-val', scoreColor(summary.avg)]">{{ fmtScore(summary.avg) }}</span>
            <span v-if="summary.deltaAvg !== null && summary.deltaAvg !== undefined"
                  :class="['summary-delta', deltaColor(summary.deltaAvg)]">
              {{ fmtDelta(summary.deltaAvg) }}
            </span>
          </div>
        </div>
        <div class="summary-row">
          <span class="summary-label">Точность типа:</span>
          <div class="summary-values">
            <span :class="['summary-val', scoreColor(summary.typeAcc)]">{{ fmtPct(summary.typeAcc) }}</span>
            <span v-if="summary.deltaTypeAcc !== null && summary.deltaTypeAcc !== undefined"
                  :class="['summary-delta', deltaColor(summary.deltaTypeAcc)]">
              {{ fmtDelta(summary.deltaTypeAcc) }}
            </span>
          </div>
        </div>
      </div>

      <div class="summary-group">
        <div class="summary-row">
          <span class="summary-label">Min-Max:</span>
          <span class="summary-val">{{ fmtScore(summary.min) }}—{{ fmtScore(summary.max) }}</span>
        </div>
        <div class="summary-row">
          <span class="summary-label">Обработано:</span>
          <span class="summary-val">{{ summary.count }} / {{ summary.total }}</span>
        </div>
        <div class="summary-row">
          <span class="summary-label">Ошибки:</span>
          <span :class="['summary-val', summary.errorCount > 0 ? 'score-red' : '']">{{ summary.errorCount }}</span>
        </div>
        <div v-if="summary.avgLatency" class="summary-row">
          <span class="summary-label">Задержка:</span>
          <span class="summary-val">{{ Math.round(summary.avgLatency) }}ms</span>
        </div>
      </div>

      <div v-if="summary.byCategory && Object.keys(summary.byCategory).length > 0" class="summary-group">
        <div class="summary-row" v-for="(stats, cat) in summary.byCategory" :key="cat">
          <span class="summary-label">{{ cat }}:</span>
          <span class="summary-val">
            {{ stats.scored ? (stats.sum / stats.scored).toFixed(3) : '—' }}
            <span class="summary-count">({{ stats.scored }}/{{ stats.total }})</span>
          </span>
        </div>
      </div>
    </div>

    <div v-if="summary.previousRunId" class="summary-vs">
      vs run #{{ summary.previousRunId }}
    </div>
  </div>
</template>

<style scoped>
.run-summary {
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-4);
  margin-bottom: var(--sp-4);
}

.run-summary-header {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin-bottom: var(--sp-3);
}

.run-summary-stats {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-4);
}

.summary-group {
  min-width: 200px;
}

.summary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-2);
  font-size: var(--fs-13);
}

.summary-row:last-child {
  margin-bottom: 0;
}

.summary-label {
  color: var(--fg-3);
  font-weight: var(--fw-medium);
}

.summary-values {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
}

.summary-val {
  font-variant-numeric: tabular-nums;
  color: var(--fg-1);
  font-weight: var(--fw-medium);
}

.summary-delta {
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  font-variant-numeric: tabular-nums;
}

.summary-count {
  font-size: var(--fs-11);
  color: var(--fg-3);
  margin-left: 4px;
}

.summary-vs {
  margin-top: var(--sp-3);
  padding-top: var(--sp-3);
  border-top: 1px solid var(--border-1);
  font-size: var(--fs-12);
  color: var(--fg-3);
  text-align: center;
}

.score-green { color: var(--ark-green-600); }
.score-yellow { color: var(--ark-amber-600); }
.score-red { color: var(--ark-red-600); }
.score-muted { color: var(--fg-3); }
</style>