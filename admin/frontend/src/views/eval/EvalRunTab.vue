<script setup>
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'
import { api } from '@/api/index.js'
import AjaxFrog from '@/components/AjaxFrog.vue'
import RunSummaryCard from '@/components/eval/RunSummaryCard.vue'
import EvalResultRow from '@/components/eval/EvalResultRow.vue'

const toast = inject('toast')

// ── run tab ───────────────────────────────────────────────────────────────────
const runNote = ref('')
const isRunning = ref(false)
const currentRun = ref(null)
const pollTimer = ref(null)
const expandedAnswerIds = ref(new Set())

const emit = defineEmits(['run-completed'])

async function startRun() {
  if (isRunning.value) return
  isRunning.value = true
  currentRun.value = null
  expandedAnswerIds.value = new Set()

  try {
    const res = await api.runEvalDataset(runNote.value || null)
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
    let data
    // FIXME: Use lightweight progress endpoint when backend is ready
    try {
      const res = await api.getEvalRunProgress(runId)
      data = res.data
    } catch {
      // Fallback to full endpoint for now
      const res = await api.getEvalRun(runId)
      data = res.data
      // Update current results immediately when using full endpoint
      currentRun.value = data
    }

    // Update basic progress info
    if (currentRun.value) {
      currentRun.value = { ...currentRun.value, ...data }
    } else {
      currentRun.value = data
    }

    if (data.status !== 'running') {
      stopPolling()
      isRunning.value = false

      // Load full results once when completed (if not already loaded)
      if (!currentRun.value.results || currentRun.value.results.length === 0) {
        const detail = await api.getEvalRun(runId)
        currentRun.value = detail.data
      }

      emit('run-completed')

      if (data.status === 'done') {
        toast('Eval завершён', 'success')
      } else {
        toast('Eval завершился с ошибкой', 'error')
      }
    }
  } catch {
    // ignore transient errors during polling
  }
}

function schedulePolling(runId) {
  stopPolling()
  pollTimer.value = setInterval(() => {
    // Stop polling if page is not visible to save server resources
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

// Stop polling when user switches to another tab
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible' && pollTimer.value) {
    // Keep the timer but it won't make requests
  }
})

onUnmounted(stopPolling)

// current run progress
const runProgress = computed(() => {
  if (!currentRun.value) return 0
  const { total, completed } = currentRun.value
  if (!total) return 0
  return Math.round((completed / total) * 100)
})

const currentResults = computed(() => currentRun.value?.results ?? [])

function computeRunStats(run, results) {
  if (!run || !results) return null
  const scoredResults = results.filter(r => r.top_score !== null && r.top_score !== undefined)
  const scores = scoredResults.map(r => r.top_score)
  const min = scores.length ? Math.min(...scores) : null
  const max = scores.length ? Math.max(...scores) : null
  const byCategory = {}
  for (const r of results) {
    if (!byCategory[r.category]) byCategory[r.category] = { total: 0, scored: 0, sum: 0 }
    byCategory[r.category].total++
    if (r.top_score !== null && r.top_score !== undefined) {
      byCategory[r.category].scored++
      byCategory[r.category].sum += r.top_score
    }
  }
  return {
    quality: run.quality_score,
    avg: run.avg_score,
    typeAcc: run.type_accuracy,
    errorCount: run.error_count ?? 0,
    avgLatency: run.avg_latency_ms,
    deltaQuality: run.delta_quality,
    deltaAvg: run.delta_avg_score,
    deltaTypeAcc: run.delta_type_accuracy,
    previousRunId: run.previous_run_id,
    min, max,
    count: scoredResults.length,
    total: results.length,
    byCategory,
  }
}

const runSummary = computed(() => computeRunStats(currentRun.value, currentResults.value))

function toggleAnswer(qid) {
  const s = new Set(expandedAnswerIds.value)
  if (s.has(qid)) s.delete(qid)
  else s.add(qid)
  expandedAnswerIds.value = s
}

async function loadAnswer(runId, questionId) {
  try {
    // FIXME: Use dedicated answer endpoint when backend is ready
    let answer
    try {
      const res = await api.getEvalAnswer(runId, questionId)
      answer = res.data.answer
    } catch {
      // Fallback: answer should already be in the result from getEvalRun
      const result = currentRun.value?.results?.find(r => r.question_id === questionId)
      if (result?.answer) {
        return // Answer already loaded
      }
      throw new Error('Answer not available')
    }

    // Update the result in currentRun.value.results
    if (currentRun.value?.results) {
      const result = currentRun.value.results.find(r => r.question_id === questionId)
      if (result) {
        result.answer = answer
      }
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
                <th>Latency</th>
              </tr>
            </thead>
            <tbody>
              <EvalResultRow
                v-for="result in currentResults"
                :key="result.question_id"
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