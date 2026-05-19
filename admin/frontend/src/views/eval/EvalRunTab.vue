<script setup>
import { ref, computed, onUnmounted, inject } from 'vue'
import { api } from '@/api/index.js'
import AjaxFrog from '@/components/AjaxFrog.vue'
import RunSummaryCard from '@/components/eval/RunSummaryCard.vue'
import EvalResultRow from '@/components/eval/EvalResultRow.vue'
import { computeRunStats } from '@/utils/evalStats.js'

const toast = inject('toast')

// ── run tab ───────────────────────────────────────────────────────────────────
const runNote = ref('')
const runDataset = ref('synthetic')  // "synthetic" | "mango"
const isRunning = ref(false)
const currentRun = ref(null)
const pollTimer = ref(null)
const expandedAnswerIds = ref(new Set())

const DATASETS = [
  { value: 'synthetic', label: 'Synthetic (50)', hint: '50 синтетических вопросов, ручная составка' },
  { value: 'mango',     label: 'Mango (50)',     hint: '50 реальных вопросов из транскрибаций звонков ТП' },
]

const emit = defineEmits(['run-completed'])

async function startRun() {
  if (isRunning.value) return
  isRunning.value = true
  currentRun.value = null
  expandedAnswerIds.value = new Set()

  try {
    const res = await api.runEvalDataset(runNote.value || null, runDataset.value)
    const runId = res.data.run_id
    await pollRun(runId)
    schedulePolling(runId)
  } catch {
    toast('Ошибка запуска eval', 'error')
    isRunning.value = false
  }
}

async function pollRun(runId) {
  try {
    // Lightweight progress endpoint — returns status, completed, total, aggregates
    // but NOT the heavy `results[]` with full LLM answers.
    const { data } = await api.getEvalRunProgress(runId)
    currentRun.value = currentRun.value
      ? { ...currentRun.value, ...data }
      : data

    if (data.status !== 'running') {
      stopPolling()
      isRunning.value = false

      // Run is finished — pull full results once. Wrapped so a network blip
      // on this single request doesn't leave the user with "Eval завершён"
      // and an empty table.
      try {
        const detail = await api.getEvalRun(runId)
        currentRun.value = detail.data
      } catch {
        toast('Не удалось загрузить детали прогона — обнови страницу', 'error')
      }

      emit('run-completed')
      toast(data.status === 'done' ? 'Eval завершён' : 'Eval завершился с ошибкой',
            data.status === 'done' ? 'success' : 'error')
    }
  } catch (err) {
    // ignore transient errors during polling
    console.warn('Polling error:', err)
  }
}

function schedulePolling(runId) {
  stopPolling()
  pollTimer.value = setInterval(() => {
    // Skip the tick if the user is on a different tab — saves server CPU
    if (document.visibilityState !== 'visible') return
    pollRun(runId)
  }, 3000)
}

function stopPolling() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

onUnmounted(stopPolling)

// current run progress
const runProgress = computed(() => {
  if (!currentRun.value) return 0
  const { total, completed } = currentRun.value
  if (!total) return 0
  return Math.round((completed / total) * 100)
})

const currentResults = computed(() => currentRun.value?.results ?? [])

const runSummary = computed(() => computeRunStats(currentRun.value, currentResults.value))

function toggleAnswer(qid) {
  const s = new Set(expandedAnswerIds.value)
  if (s.has(qid)) s.delete(qid)
  else s.add(qid)
  expandedAnswerIds.value = s
}

async function loadAnswer(runId, questionId) {
  try {
    const { data } = await api.getEvalAnswer(runId, questionId)
    const result = currentRun.value?.results?.find(r => r.question_id === questionId)
    if (result) {
      result.answer = data.answer
    }
  } catch {
    toast('Ошибка загрузки ответа', 'error')
  }
}
</script>

<template>
  <div class="run-tab">
    <!-- Start controls -->
    <div class="run-controls panel">
      <div class="run-controls-inner">
        <select
          v-model="runDataset"
          class="dataset-select"
          :disabled="isRunning"
          :title="DATASETS.find(d => d.value === runDataset)?.hint"
        >
          <option v-for="d in DATASETS" :key="d.value" :value="d.value">
            {{ d.label }}
          </option>
        </select>
        <input
          v-model="runNote"
          placeholder="Заметка к прогону (опционально)"
          class="run-note-input"
          :disabled="isRunning"
        />
        <button
          @click="startRun"
          :disabled="isRunning"
          class="btn btn-primary"
          :class="{ 'btn-loading': isRunning }"
        >
          <AjaxFrog v-if="isRunning" text="" size="16px" />
          <span v-else>Запустить eval</span>
        </button>
      </div>
      <div class="dataset-hint">
        {{ DATASETS.find(d => d.value === runDataset)?.hint }}
      </div>
    </div>

    <!-- Current run progress -->
    <div v-if="isRunning || currentRun" class="current-run-block">
      <div v-if="isRunning" class="progress-header">
        <h3>Прогон в процессе...</h3>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: runProgress + '%' }"></div>
        </div>
        <div class="progress-text">{{ runProgress }}% ({{ currentRun?.completed || 0 }} / {{ currentRun?.total || 0 }})</div>
      </div>

      <!-- Run summary -->
      <RunSummaryCard
        v-if="runSummary"
        :summary="runSummary"
        :title="isRunning ? 'Текущие результаты' : 'Итоги прогона'"
      />

      <!-- Results table -->
      <div v-if="currentResults.length > 0" class="results-section">
        <h4 class="results-title">Результаты</h4>
        <div class="table-wrap">
          <table class="log-table">
            <colgroup>
              <col style="width: 56px" />
              <col style="width: 100px" />
              <col style="width: auto" />
              <col style="width: 110px" />
              <col style="width: 110px" />
              <col style="width: 64px" />
              <col style="width: 56px" />
              <col style="width: 70px" />
            </colgroup>
            <thead>
              <tr>
                <th>#</th>
                <th>Категория</th>
                <th>Вопрос</th>
                <th>Ожид. тип</th>
                <th>Факт. тип</th>
                <th>Score</th>
                <th title="LLM-judge usefulness 0-100">Useful</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody>
              <EvalResultRow
                v-for="result in currentResults"
                :key="result.question_id"
                :colspan="8"
                :result="result"
                :is-open="expandedAnswerIds.has(result.question_id)"
                @toggle="toggleAnswer"
                @load-answer="(qid) => loadAnswer(currentRun.id, qid)"
              />
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.run-tab {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.run-controls {
  margin-bottom: var(--sp-4);
}

.run-controls-inner {
  display: flex;
  gap: var(--sp-3);
  align-items: center;
}

.dataset-select {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-input);
  color: var(--fg-1);
  font-size: var(--fs-14);
  cursor: pointer;
  min-width: 160px;
}

.dataset-hint {
  font-size: var(--fs-11);
  color: var(--fg-3);
  padding: var(--sp-2) 0 0;
}

.run-note-input {
  flex: 1;
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-input);
  color: var(--fg-1);
  font-size: var(--fs-14);
  transition: border-color var(--dur-fast);
}

.run-note-input:focus {
  outline: none;
  border-color: var(--accent);
}

.btn {
  padding: var(--sp-2) var(--sp-4);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-panel);
  color: var(--fg-1);
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  cursor: pointer;
  transition: all var(--dur-fast);
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  min-height: 40px;
}

.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-loading {
  background: var(--accent);
  border-color: var(--accent);
}

.current-run-block {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.progress-header h3 {
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0 0 var(--sp-3) 0;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--bg-panel-2);
  border-radius: var(--rad-md);
  overflow: hidden;
  margin-bottom: var(--sp-2);
}

.progress-fill {
  height: 100%;
  background: var(--accent);
  transition: width var(--dur-normal);
}

.progress-text {
  font-size: var(--fs-13);
  color: var(--fg-3);
  text-align: center;
}

.results-section {
  margin-top: var(--sp-4);
}

.results-title {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0 0 var(--sp-3) 0;
}

.panel {
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-4);
}
</style>