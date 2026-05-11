<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { api } from '@/api/index.js'
import {
  fmtScore, fmtDelta, fmtQuality, fmtDeltaQuality, fmtPct,
  scoreColor, deltaColor, qualityColor, deltaQualityColor
} from '@/utils/format.js'
import AjaxFrog from '@/components/AjaxFrog.vue'
import RunSummaryCard from '@/components/eval/RunSummaryCard.vue'
import EvalResultRow from '@/components/eval/EvalResultRow.vue'

const toast = inject('toast')

// ── history tab ────────────────────────────────────────────────────────────────
const runs = ref([])
const runsLoading = ref(false)
const expandedRunId = ref(null)
const expandedRunData = ref(null)
const expandedLoading = ref(false)
const expandedAnswerIds = ref(new Set())

// ── compare ───────────────────────────────────────────────────────────────────
const compareData = ref(null)
const compareLoading = ref(false)

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

async function compareLastTwo() {
  if (runs.value.length < 2) return
  const [runA, runB] = [runs.value[1], runs.value[0]]
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
      const result = expandedRunData.value?.results?.find(r => r.question_id === questionId)
      if (result?.answer) {
        return // Answer already loaded
      }
      throw new Error('Answer not available')
    }

    // Update the result in expandedRunData.value.results
    if (expandedRunData.value?.results) {
      const result = expandedRunData.value.results.find(r => r.question_id === questionId)
      if (result) {
        result.answer = answer
      }
    }
  } catch {
    toast('Ошибка загрузки ответа', 'error')
  }
}

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

function categoryBadgeClass(cat) {
  return {
    'подбор': 'cat-selection',
    'характеристики': 'cat-specs',
    'установка': 'cat-install',
    'компания': 'cat-company',
    'дилер': 'cat-dealer',
  }[cat] || ''
}

function qtypeCls(qt) {
  return {
    RAG_PRODUCT: 'qt-rag',
    FAQ_COMPANY: 'qt-ref',
    FAQ_DEALER: 'qt-dealer',
    FAQ_EXACT: 'qt-faq',
    ERROR: 'qt-error',
  }[qt] || ''
}

function qtypeLabel(qt) {
  return {
    RAG_PRODUCT: 'RAG',
    FAQ_COMPANY: 'О компании',
    FAQ_DEALER: 'Дилер',
    FAQ_EXACT: 'FAQ',
    ERROR: 'Ошибка',
  }[qt] || qt || '—'
}

onMounted(loadRuns)

defineExpose({ loadRuns })
</script>

<template>
  <div class="eval-history-tab">
    <!-- Compare section -->
    <div v-if="runs.length >= 2" class="compare-section">
      <div class="compare-header">
        <button @click="compareLastTwo" :disabled="compareLoading" class="btn btn-secondary">
          <AjaxFrog v-if="compareLoading" text="" size="14px" />
          <span v-else>Сравнить последние 2</span>
        </button>
      </div>

      <div v-if="compareData" class="compare-results">
        <div class="compare-runs-label">
          <span class="run-label-a">#{{ compareData.run_a_id }}</span>
          <span class="compare-arrow">→</span>
          <span class="run-label-b">#{{ compareData.run_b_id }}</span>
        </div>

        <div class="compare-summary">
          <div class="compare-stat-row">
            <span>Quality:</span>
            <span :class="compareData.summary.quality_delta > 0 ? 'improved' : compareData.summary.quality_delta < 0 ? 'degraded' : ''">
              {{ compareData.summary.quality_a.toFixed(1) }}
            </span>
            <span class="compare-sep">→</span>
            <span :class="compareData.summary.quality_delta > 0 ? 'improved' : compareData.summary.quality_delta < 0 ? 'degraded' : ''">
              {{ compareData.summary.quality_b.toFixed(1) }}
            </span>
            <span :class="['compare-stat', compareData.summary.quality_delta > 0.5 ? 'improved' : compareData.summary.quality_delta < -0.5 ? 'degraded' : '']">
              ({{ compareData.summary.quality_delta >= 0 ? '+' : '' }}{{ compareData.summary.quality_delta.toFixed(1) }})
            </span>
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
              <tr v-for="q in compareData.questions" :key="q.question_id" class="log-row">
                <td class="cell-num">{{ q.question_id }}</td>
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
    </div>

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
                    v-for="result in expandedRunData.results"
                    :key="result.question_id"
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

.compare-section {
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-4);
}

.compare-header {
  margin-bottom: var(--sp-4);
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

.compare-runs-label {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--fg-3);
  margin-bottom: var(--sp-3);
}

.run-label-a { color: var(--fg-2); }
.run-label-b { color: var(--fg-1); font-weight: var(--fw-medium); }
.compare-arrow { color: var(--fg-4); }

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