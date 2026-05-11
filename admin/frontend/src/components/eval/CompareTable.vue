<script setup>
import {
  fmtDelta,
  scoreColor, deltaColor
} from '@/utils/format.js'
import { categoryBadgeClass, qtypeCls, qtypeLabel } from '@/utils/badges.js'

const props = defineProps({
  questions: {
    type: Array,
    required: true
  }
})
</script>

<template>
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
        <tr v-for="q in questions" :key="q.id" class="log-row">
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
</template>

<style scoped>
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