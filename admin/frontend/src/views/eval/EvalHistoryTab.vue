<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { api } from '@/api/index.js'
import {
  fmtScore, fmtQuality, fmtDeltaQuality, fmtPct,
  scoreColor, qualityColor, deltaQualityColor
} from '@/utils/format.js'
import AjaxFrog from '@/components/AjaxFrog.vue'
import RunSummaryCard from '@/components/eval/RunSummaryCard.vue'
import EvalResultRow from '@/components/eval/EvalResultRow.vue'
import CompareRunsCard from '@/components/eval/CompareRunsCard.vue'
import { computeRunStats } from '@/utils/evalStats.js'

const toast = inject('toast')

// ── history tab ────────────────────────────────────────────────────────────────
const runs = ref([])
const runsLoading = ref(false)
const expandedRunId = ref(null)
const expandedRunData = ref(null)
const expandedLoading = ref(false)
const expandedAnswerIds = ref(new Set())

// ── compare (moved to CompareRunsCard) ───────────────────────────────────────

async function loadRuns() {
  runsLoading.value = true
  try {
    const res = await api.getEvalRuns()
    runs.value = res.data.items
  } catch {
    toast('Ошибка загрузки истории', 'error')
  } finally {
    runsLoading.value = false
  }
}

async function toggleRun(runId) {
  if (expandedRunId.value === runId) {
    expandedRunId.value = null
    expandedRunData.value = null
    expandedAnswerIds.value = new Set()
    return
  }
  expandedRunId.value = runId
  expandedRunData.value = null
  expandedAnswerIds.value = new Set()
  expandedLoading.value = true
  try {
    const res = await api.getEvalRun(runId)
    expandedRunData.value = res.data
  } catch {
    toast('Ошибка загрузки прогона', 'error')
    expandedRunId.value = null
  } finally {
    expandedLoading.value = false
  }
}

async function deleteRun(runId) {
  if (!confirm('Удалить прогон #' + runId + '?')) return
  try {
    await api.deleteEvalRun(runId)
    if (expandedRunId.value === runId) {
      expandedRunId.value = null
      expandedRunData.value = null
    }
    await loadRuns()
    toast('Прогон удалён', 'success')
  } catch {
    toast('Ошибка удаления', 'error')
  }
}


function toggleAnswer(qid) {
  const s = new Set(expandedAnswerIds.value)
  if (s.has(qid)) s.delete(qid)
  else s.add(qid)
  expandedAnswerIds.value = s
}

async function loadAnswer(runId, questionId) {
  try {
    const { data } = await api.getEvalAnswer(runId, questionId)
    const result = expandedRunData.value?.results?.find(r => r.question_id === questionId)
    if (result) {
      result.answer = data.answer
    }
  } catch {
    toast('Ошибка загрузки ответа', 'error')
  }
}

const expandedSummary = computed(() =>
  computeRunStats(expandedRunData.value, expandedRunData.value?.results ?? [])
)

// Helper functions
function statusCls(status) {
  return {
    running: 'status-running',
    done: 'status-done',
    error: 'status-error',
  }[status] || ''
}

function statusLabel(status) {
  return {
    running: 'В процессе',
    done: 'Завершён',
    error: 'Ошибка',
  }[status] || status
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('ru', { day: '2-digit', month: '2-digit', year: '2-digit' }) +
    ' ' + d.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })
}

onMounted(loadRuns)

defineExpose({ loadRuns, runs })
</script>

<template>
  <div class="eval-history-tab">
    <!-- Compare section -->
    <CompareRunsCard
      v-if="runs.length >= 2"
      :runs="runs"
    />

    <!-- Runs list -->
    <div class="runs-section">
      <div v-if="runsLoading" class="loading-state">
        <AjaxFrog />
      </div>
      <div v-else-if="runs.length === 0" class="empty-state-box">
        Прогонов ещё нет
      </div>
      <div v-else class="runs-list">
        <div v-for="run in runs" :key="run.id" class="run-card">
          <div class="run-card-header" @click="toggleRun(run.id)">
            <div class="run-card-meta">
              <span class="run-id">#{{ run.id }}</span>
              <span :class="['run-status', statusCls(run.status)]">{{ statusLabel(run.status) }}</span>
              <span v-if="run.dataset_name" class="run-dataset" :title="'Eval dataset'">
                {{ run.dataset_name }}
              </span>
              <span class="run-date">{{ formatDate(run.ran_at) }}</span>
              <span class="run-progress">{{ run.completed }}/{{ run.total }}</span>
              <span v-if="run.note" class="run-note">{{ run.note }}</span>
            </div>
            <div class="run-card-score">
              <span :class="['quality-pill', qualityColor(run.quality_score)]" :title="'Quality = 0.7·avg_score + 0.3·type_accuracy'">
                {{ fmtQuality(run.quality_score) }}
              </span>
              <span v-if="run.delta_quality !== null && run.delta_quality !== undefined"
                :class="['quality-delta', deltaQualityColor(run.delta_quality)]"
                :title="'vs прогон #' + run.previous_run_id">
                {{ fmtDeltaQuality(run.delta_quality) }}
              </span>
            </div>
            <div class="run-card-metrics">
              <span class="metric-chip">avg score <span :class="['metric-val', scoreColor(run.avg_score)]">{{ fmtScore(run.avg_score) }}</span></span>
              <span class="metric-chip">type acc <span class="metric-val">{{ fmtPct(run.type_accuracy) }}</span></span>
              <span v-if="run.error_count > 0" class="metric-chip error-chip">
                ошибок: {{ run.error_count }}
              </span>
              <span v-if="run.avg_latency_ms" class="metric-chip">⏱ {{ (run.avg_latency_ms / 1000).toFixed(1) }}с</span>
            </div>
            <div class="run-card-actions">
              <button class="row-faq-btn" @click.stop="deleteRun(run.id)" title="Удалить">✕</button>
              <span class="expand-chevron" :class="{ open: expandedRunId === run.id }">▼</span>
            </div>
          </div>

          <!-- Expanded results -->
          <div v-if="expandedRunId === run.id" class="run-card-body">
            <div v-if="expandedLoading" class="loading-state">
              <AjaxFrog />
            </div>
            <div v-else-if="expandedRunData">
              <!-- Per-run summary with delta vs previous -->
              <RunSummaryCard
                v-if="expandedSummary"
                :summary="expandedSummary"
                title="Итоги прогона"
              />

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
                    v-for="result in expandedRunData.results"
                    :key="result.question_id"
                    :colspan="8"
                    :result="result"
                    :is-open="expandedAnswerIds.has(result.question_id)"
                    @toggle="toggleAnswer"
                    @load-answer="(qid) => loadAnswer(expandedRunData.id, qid)"
                  />
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.eval-history-tab {
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
}

.loading-state {
  padding: var(--sp-8);
  text-align: center;
}

.empty-state-box {
  padding: var(--sp-8);
  text-align: center;
  background: var(--bg-panel-2);
  border-radius: var(--rad-lg);
  color: var(--fg-3);
  font-size: var(--fs-14);
}

.runs-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.run-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  overflow: hidden;
}

.run-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-3) var(--sp-4);
  cursor: pointer;
  transition: background var(--dur-fast);
}

.run-card-header:hover {
  background: var(--bg-hover);
}

.run-card-meta {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
}

.run-id {
  font-size: var(--fs-13);
  font-weight: var(--fw-bold);
  color: var(--fg-1);
}

.run-status {
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  padding: 2px 6px;
  border-radius: var(--rad-sm);
  text-transform: uppercase;
}

.status-running { background: var(--ark-blue-100); color: var(--ark-blue-600); }
.status-done { background: var(--ark-green-100); color: var(--ark-green-600); }
.status-error { background: var(--ark-red-100); color: var(--ark-red-600); }

.run-date {
  font-size: var(--fs-12);
  color: var(--fg-3);
}

.run-progress {
  font-size: var(--fs-12);
  color: var(--fg-3);
}

.run-dataset {
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 1px 7px;
  border-radius: var(--rad-sm);
  background: color-mix(in srgb, var(--ark-blue-600) 15%, transparent);
  color: var(--ark-blue-600);
}

.run-note {
  font-size: var(--fs-12);
  color: var(--fg-2);
  font-style: italic;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-card-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.run-card-score {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  min-width: 110px;
}

.quality-pill {
  font-size: var(--fs-18);
  font-weight: var(--fw-bold);
  padding: 2px 10px;
  border-radius: var(--rad-md);
  background: var(--bg-panel-2);
  border: 1px solid var(--border-1);
  font-variant-numeric: tabular-nums;
}

.quality-delta {
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  font-variant-numeric: tabular-nums;
}

.run-card-metrics {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

.metric-chip {
  font-size: var(--fs-11);
  color: var(--fg-3);
  padding: 2px 6px;
  background: var(--bg-panel-2);
  border-radius: var(--rad-sm);
  white-space: nowrap;
}

.metric-chip .metric-val {
  color: var(--fg-1);
  font-weight: var(--fw-semibold);
  margin-left: 4px;
  font-variant-numeric: tabular-nums;
}

.error-chip {
  color: var(--ark-red-600);
  background: color-mix(in srgb, var(--ark-red-600) 12%, transparent);
}

.expand-chevron {
  font-size: 10px;
  color: var(--fg-3);
  transition: transform var(--dur-fast);
}

.expand-chevron.open {
  transform: rotate(180deg);
  color: var(--accent);
}

.row-faq-btn {
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

.row-faq-btn:hover {
  border-color: var(--ark-red-600);
  color: var(--ark-red-600);
  background: var(--ark-red-100);
}

.run-card-body {
  border-top: 1px solid var(--border-1);
  padding: var(--sp-4);
}

/* Score styles moved to global @/assets/scores.css */

</style>