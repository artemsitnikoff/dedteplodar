<script setup>
import { scoreColor } from '@/utils/format.js'
import { categoryBadgeClass, qtypeCls, qtypeLabel } from '@/utils/badges.js'

const props = defineProps({
  result: {
    type: Object,
    required: true
  },
  isOpen: {
    type: Boolean,
    default: false
  },
  colspan: {
    type: Number,
    default: 7
  }
})

const emit = defineEmits(['toggle', 'load-answer'])

function handleRowClick() {
  emit('toggle', props.result.question_id)
}

function handleLoadAnswer() {
  emit('load-answer', props.result.question_id)
}
</script>

<template>
  <tr
    class="log-row clickable-row"
    :class="{ 'row-open': isOpen }"
    @click="handleRowClick"
  >
    <td class="cell-num">{{ result.question_id }}</td>
    <td>
      <span :class="['cat-badge', categoryBadgeClass(result.category)]">
        {{ result.category }}
      </span>
    </td>
    <td class="cell-q">{{ result.question }}</td>
    <td>
      <span :class="['qtype-badge', qtypeCls(result.expected_type)]">
        {{ qtypeLabel(result.expected_type) }}
      </span>
    </td>
    <td>
      <span v-if="result.error" class="error-note" :title="result.error">ERR</span>
      <span v-else-if="result.actual_type" :class="['qtype-badge', qtypeCls(result.actual_type)]">
        {{ qtypeLabel(result.actual_type) }}
      </span>
      <span v-else class="score-none">—</span>
    </td>
    <td class="cell-score">
      <span v-if="result.top_score !== null && result.top_score !== undefined"
            :class="['score-val', scoreColor(result.top_score)]">
        {{ result.top_score.toFixed(3) }}
      </span>
      <span v-else class="score-none">—</span>
    </td>
    <td class="cell-num latency">
      {{ result.latency_ms !== null ? result.latency_ms + 'ms' : '—' }}
    </td>
  </tr>
  <tr v-if="isOpen" class="answer-row">
    <td :colspan="colspan">
      <div v-if="result.error" class="answer-error">⚠ {{ result.error }}</div>
      <div v-else-if="result.answer" class="answer-body">
        <pre class="answer-text">{{ result.answer }}</pre>
      </div>
      <div v-else class="answer-empty">
        <span>Ответ не загружен</span>
        <button @click.stop="handleLoadAnswer" class="load-answer-btn">Загрузить</button>
      </div>
    </td>
  </tr>
</template>

<style scoped>
/* Row styles will be inherited from parent table styles */
.answer-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: var(--fs-13);
  line-height: 1.5;
  color: var(--fg-2);
  background: var(--bg-panel-2);
  padding: var(--sp-3);
  border-radius: var(--rad-md);
  margin: 0;
}

.answer-error {
  color: var(--ark-red-600);
  background: color-mix(in srgb, var(--ark-red-600) 12%, transparent);
  padding: var(--sp-3);
  border-radius: var(--rad-md);
  font-size: var(--fs-13);
}

.answer-empty {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3);
  color: var(--fg-3);
  font-size: var(--fs-13);
}

.load-answer-btn {
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  padding: 4px 8px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-sm);
  color: var(--fg-2);
  cursor: pointer;
  transition: all var(--dur-fast);
}

.load-answer-btn:hover {
  background: var(--bg-hover);
  border-color: var(--accent);
  color: var(--accent);
}

/* Helper classes that need to be global or inherited from parent */
.score-val.score-green { color: var(--ark-green-600); }
.score-val.score-yellow { color: var(--ark-amber-600); }
.score-val.score-red { color: var(--ark-red-600); }
.score-none { color: var(--fg-4); }

.error-note {
  color: var(--ark-red-600);
  font-weight: var(--fw-bold);
  font-size: var(--fs-11);
}

/* Badge styles moved to global @/assets/badges.css */
</style>