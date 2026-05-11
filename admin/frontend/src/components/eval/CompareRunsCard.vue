<script setup>
import {
  fmtScore, fmtDelta, fmtQuality, fmtDeltaQuality, fmtPct,
  scoreColor, deltaColor, qualityColor, deltaQualityColor
} from '@/utils/format.js'
import { categoryBadgeClass, qtypeCls, qtypeLabel } from '@/utils/badges.js'

const props = defineProps({
  compareData: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['close'])

function handleClose() {
  emit('close')
}
</script>

<template>
  <div class="compare-results">
    <div class="compare-header">
      <div class="compare-runs-label">
        <span class="run-label-a">#{{ compareData.run_a.id }}</span>
        <span class="compare-arrow">→</span>
        <span class="run-label-b">#{{ compareData.run_b.id }}</span>
      </div>
      <button @click="handleClose" class="close-btn" title="Закрыть сравнение">✕</button>
    </div>

    <div class="compare-summary">
      <div v-if="compareData.summary.quality_a !== null && compareData.summary.quality_b !== null" class="compare-stat-row">
        <span>Quality:</span>
        <span>{{ fmtQuality(compareData.summary.quality_a) }}</span>
        <span class="compare-sep">→</span>
        <span>{{ fmtQuality(compareData.summary.quality_b) }}</span>
        <span v-if="compareData.summary.quality_delta !== null"
              :class="['compare-stat', deltaQualityColor(compareData.summary.quality_delta)]">
          ({{ fmtDeltaQuality(compareData.summary.quality_delta) }})
        </span>
      </div>
      <div class="compare-stat-row">
        <span>Avg score:</span>
        <span>{{ fmtScore(compareData.summary.avg_score_a) }}</span>
        <span class="compare-sep">→</span>
        <span>{{ fmtScore(compareData.summary.avg_score_b) }}</span>
      </div>
      <div class="compare-stat-row compare-counts">
        <span class="improved">улучшилось: {{ compareData.summary.improved }}</span>
        <span class="degraded">ухудшилось: {{ compareData.summary.degraded }}</span>
        <span>тип изменился: {{ compareData.summary.type_changes }}</span>
      </div>
    </div>

    <div class="compare-table-wrap">
      <table class="log-table">
        <colgroup>
          <col style="width: 56px" />
          <col style="width: 100px" />
          <col style="width: auto" />
          <col style="width: 80px" />
          <col style="width: 80px" />
          <col style="width: 80px" />
          <col style="width: 90px" />
          <col style="width: 90px" />
        </colgroup>
        <thead>
          <tr>
            <th>#</th>
            <th>Категория</th>
            <th>Вопрос</th>
            <th>Score A</th>
            <th>Score B</th>
            <th>Δ</th>
            <th>Тип A</th>
            <th>Тип B</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="q in compareData.questions" :key="q.id" class="log-row">
            <td class="cell-num">{{ q.id }}</td>
            <td><span :class="['cat-badge', categoryBadgeClass(q.category)]">{{ q.category }}</span></td>
            <td class="cell-q">{{ q.question }}</td>
            <td class="cell-score">
              <span v-if="q.run_a.score !== null && q.run_a.score !== undefined" :class="['score-val', scoreColor(q.run_a.score)]">
                {{ q.run_a.score.toFixed(3) }}
              </span>
              <span v-else class="score-none">—</span>
            </td>
            <td class="cell-score">
              <span v-if="q.run_b.score !== null && q.run_b.score !== undefined" :class="['score-val', scoreColor(q.run_b.score)]">
                {{ q.run_b.score.toFixed(3) }}
              </span>
              <span v-else class="score-none">—</span>
            </td>
            <td class="cell-score">
              <span :class="['score-val', deltaColor(q.score_delta)]">{{ fmtDelta(q.score_delta) }}</span>
            </td>
            <td>
              <span v-if="q.run_a.type" :class="['qtype-badge', qtypeCls(q.run_a.type)]">{{ qtypeLabel(q.run_a.type) }}</span>
              <span v-else class="score-none">—</span>
            </td>
            <td>
              <span v-if="q.run_b.type" :class="['qtype-badge', qtypeCls(q.run_b.type), { 'type-changed': q.type_changed }]">
                {{ q.type_changed ? '→ ' : '' }}{{ qtypeLabel(q.run_b.type) }}
              </span>
              <span v-else class="score-none">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.compare-results {
  margin-top: var(--sp-4);
}

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
.compare-stat.improved { color: var(--ark-green-600); font-weight: var(--fw-semibold); }
.compare-stat.degraded { color: var(--ark-red-600); font-weight: var(--fw-semibold); }

.compare-counts .improved { color: var(--ark-green-600); font-weight: var(--fw-semibold); }
.compare-counts .degraded { color: var(--ark-red-600); font-weight: var(--fw-semibold); }

.compare-table-wrap {
  border-radius: var(--rad-lg);
  overflow: hidden;
  border: 1px solid var(--border-1);
  background: var(--bg-panel);
}

/* Color classes */
.score-green { color: var(--ark-green-600); }
.score-yellow { color: var(--ark-amber-600); }
.score-red { color: var(--ark-red-600); }
.score-muted { color: var(--fg-3); }
.score-none { color: var(--fg-4); }

.cat-badge {
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  padding: 2px 6px;
  border-radius: var(--rad-sm);
  white-space: nowrap;
  background: var(--bg-panel-2);
  color: var(--fg-2);
}

.cat-selection { background: color-mix(in srgb, var(--ark-blue-600) 15%, transparent); color: var(--ark-blue-600); }
.cat-specs { background: color-mix(in srgb, var(--ark-green-600) 15%, transparent); color: var(--ark-green-600); }
.cat-install { background: color-mix(in srgb, var(--ark-purple-600) 15%, transparent); color: var(--ark-purple-600); }
.cat-company { background: color-mix(in srgb, var(--ark-amber-600) 15%, transparent); color: var(--ark-amber-600); }
.cat-dealer { background: color-mix(in srgb, var(--ark-red-600) 15%, transparent); color: var(--ark-red-600); }

.qtype-badge {
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  padding: 2px 6px;
  border-radius: var(--rad-sm);
  white-space: nowrap;
  background: var(--bg-panel-2);
  color: var(--fg-3);
}

.qt-rag { background: color-mix(in srgb, var(--ark-blue-600) 15%, transparent); color: var(--ark-blue-600); }
.qt-ref { background: color-mix(in srgb, var(--ark-green-600) 15%, transparent); color: var(--ark-green-600); }
.qt-dealer { background: color-mix(in srgb, var(--ark-purple-600) 15%, transparent); color: var(--ark-purple-600); }
.qt-faq { background: color-mix(in srgb, var(--ark-amber-600) 15%, transparent); color: var(--ark-amber-600); }
.qt-error { background: color-mix(in srgb, var(--ark-red-600) 15%, transparent); color: var(--ark-red-600); }

.type-changed {
  background: color-mix(in srgb, var(--ark-amber-600) 20%, transparent);
  color: var(--ark-amber-700);
  font-weight: var(--fw-bold);
}
</style>