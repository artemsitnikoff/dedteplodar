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

/* Badge and score styles moved to global @/assets/badges.css and @/assets/scores.css */
</style>