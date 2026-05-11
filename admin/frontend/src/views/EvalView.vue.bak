<script setup>
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'
import { api } from '@/api/index.js'
import AjaxFrog from '@/components/AjaxFrog.vue'

const toast = inject('toast')

// ── tabs ──────────────────────────────────────────────────────────────────────
const activeTab = ref('dataset')

// ── dataset tab ───────────────────────────────────────────────────────────────
const dataset = ref([])
const datasetLoading = ref(false)

async function loadDataset() {
  datasetLoading.value = true
  try {
    const res = await api.getEvalDataset()
    dataset.value = res.data.items
  } catch {
    toast('Ошибка загрузки датасета', 'error')
  } finally {
    datasetLoading.value = false
  }
}

// ── run tab ───────────────────────────────────────────────────────────────────
const runNote = ref('')
const isRunning = ref(false)
const currentRun = ref(null)
const pollTimer = ref(null)

async function startRun() {
  if (isRunning.value) return
  isRunning.value = true
  currentRun.value = null
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
    const res = await api.getEvalRun(runId)
    currentRun.value = res.data
    if (res.data.status !== 'running') {
      stopPolling()
      isRunning.value = false
      await loadRuns()
      if (res.data.status === 'done') {
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
  pollTimer.value = setInterval(() => pollRun(runId), 3000)
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
const expandedSummary = computed(() => computeRunStats(expandedRunData.value, expandedRunData.value?.results ?? []))

// ── history tab ────────────────────────────────────────────────────────────────
const runs = ref([])
const runsLoading = ref(false)
const expandedRunId = ref(null)
const expandedRunData = ref(null)
const expandedLoading = ref(false)
const expandedAnswerIds = ref(new Set())

function toggleAnswer(qid) {
  const s = new Set(expandedAnswerIds.value)
  if (s.has(qid)) s.delete(qid)
  else s.add(qid)
  expandedAnswerIds.value = s
}

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

// ── compare ───────────────────────────────────────────────────────────────────
const compareData = ref(null)
const compareLoading = ref(false)

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

// ── lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([loadDataset(), loadRuns()])
})

// ── helpers ───────────────────────────────────────────────────────────────────
function scoreColor(score) {
  if (score === null || score === undefined) return ''
  if (score >= 0.85) return 'score-green'
  if (score >= 0.80) return 'score-yellow'
  return 'score-red'
}

function deltaColor(delta) {
  if (delta === null || delta === undefined) return ''
  if (delta > 0.001) return 'score-green'
  if (delta < -0.001) return 'score-red'
  return 'score-muted'
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

function fmtScore(s) {
  if (s === null || s === undefined) return '—'
  return s.toFixed(3)
}

function fmtDelta(d) {
  if (d === null || d === undefined) return '—'
  return (d >= 0 ? '+' : '') + d.toFixed(3)
}

function fmtQuality(q) {
  if (q === null || q === undefined) return '—'
  return q.toFixed(1)
}

function fmtDeltaQuality(d) {
  if (d === null || d === undefined) return ''
  return (d >= 0 ? '+' : '') + d.toFixed(1)
}

function qualityColor(q) {
  if (q === null || q === undefined) return 'score-muted'
  if (q >= 70) return 'score-green'
  if (q >= 55) return 'score-yellow'
  return 'score-red'
}

function deltaQualityColor(d) {
  if (d === null || d === undefined) return ''
  if (d > 0.5) return 'score-green'
  if (d < -0.5) return 'score-red'
  return 'score-muted'
}

function fmtPct(p) {
  if (p === null || p === undefined) return '—'
  return (p * 100).toFixed(0) + '%'
}
</script>

<template>
  <div class="eval-view">
    <!-- Header -->
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">Eval</h1>
        <span class="page-count">{{ dataset.length }} вопросов</span>
      </div>

      <!-- Tabs -->
      <div class="tabs">
        <button :class="['tab-btn', { active: activeTab === 'dataset' }]" @click="activeTab = 'dataset'">Датасет</button>
        <button :class="['tab-btn', { active: activeTab === 'run' }]" @click="activeTab = 'run'">Запустить</button>
        <button :class="['tab-btn', { active: activeTab === 'history' }]" @click="activeTab = 'history'">
          История
          <span v-if="runs.length" class="tab-count">{{ runs.length }}</span>
        </button>
      </div>
    </div>

    <!-- ── Tab: Датасет ────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'dataset'">
      <div class="table-wrap">
        <div v-if="datasetLoading" class="loading-state"><AjaxFrog /></div>
        <table v-else class="log-table">
          <colgroup>
            <col style="width: 56px" />
            <col style="width: 110px" />
            <col style="width: auto" />
            <col style="width: 120px" />
          </colgroup>
          <thead>
            <tr>
              <th>#</th>
              <th>Категория</th>
              <th>Вопрос</th>
              <th>Ожид. тип</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in dataset" :key="item.id" class="log-row">
              <td class="cell-num">{{ item.id }}</td>
              <td><span :class="['cat-badge', categoryBadgeClass(item.category)]">{{ item.category }}</span></td>
              <td class="cell-q">{{ item.question }}</td>
              <td><span :class="['qtype-badge', qtypeCls(item.expected_type)]">{{ qtypeLabel(item.expected_type) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── Tab: Запустить ─────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'run'" class="run-tab">
      <!-- Start controls -->
      <div class="run-controls panel">
        <div class="run-controls-inner">
          <input
            v-model="runNote"
            class="note-input"
            placeholder="Метка прогона (необязательно)"
            :disabled="isRunning"
          />
          <button
            class="run-btn"
            :disabled="isRunning"
            @click="startRun"
          >
            {{ isRunning ? 'Выполняется...' : 'Запустить тестовый датасет' }}
          </button>
        </div>

        <!-- Progress bar -->
        <div v-if="currentRun" class="progress-wrap">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: runProgress + '%' }"></div>
          </div>
          <div class="progress-label">
            {{ currentRun.completed }} / {{ currentRun.total }}
            <span :class="['run-status', statusCls(currentRun.status)]">{{ statusLabel(currentRun.status) }}</span>
          </div>
        </div>
      </div>

      <!-- Live results table -->
      <div v-if="currentRun && currentResults.length" class="table-wrap">
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
            <tr v-for="r in currentResults" :key="r.question_id" class="log-row">
              <td class="cell-num">{{ r.question_id }}</td>
              <td><span :class="['cat-badge', categoryBadgeClass(r.category)]">{{ r.category }}</span></td>
              <td class="cell-q">{{ r.question }}</td>
              <td><span :class="['qtype-badge', qtypeCls(r.expected_type)]">{{ qtypeLabel(r.expected_type) }}</span></td>
              <td>
                <span v-if="r.error" class="error-note" :title="r.error">ERR</span>
                <span v-else-if="r.actual_type" :class="['qtype-badge', qtypeCls(r.actual_type)]">{{ qtypeLabel(r.actual_type) }}</span>
                <span v-else class="score-none">—</span>
              </td>
              <td class="cell-score">
                <span v-if="r.top_score !== null && r.top_score !== undefined" :class="['score-val', scoreColor(r.top_score)]">
                  {{ r.top_score.toFixed(3) }}
                </span>
                <span v-else class="score-none">—</span>
              </td>
              <td class="cell-num latency">{{ r.latency_ms !== null ? r.latency_ms + 'ms' : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Summary stats (shown after completion) -->
      <div v-if="currentRun && currentRun.status === 'done' && runSummary" class="summary-block panel">
        <h3 class="summary-title">
          Итоги прогона
          <span v-if="runSummary.previousRunId" class="vs-prev">vs прогон #{{ runSummary.previousRunId }}</span>
        </h3>

        <!-- Headline quality score -->
        <div v-if="runSummary.quality !== null && runSummary.quality !== undefined" class="quality-headline">
          <div class="quality-block">
            <div class="stat-label">Quality score</div>
            <div class="quality-row">
              <span :class="['quality-big', qualityColor(runSummary.quality)]">{{ runSummary.quality.toFixed(1) }}</span>
              <span class="quality-max">/ 100</span>
              <span v-if="runSummary.deltaQuality !== null && runSummary.deltaQuality !== undefined"
                :class="['quality-delta-big', deltaQualityColor(runSummary.deltaQuality)]">
                {{ fmtDeltaQuality(runSummary.deltaQuality) }}
              </span>
            </div>
            <div class="quality-formula">0.7 · avg_score + 0.3 · type_accuracy</div>
          </div>
        </div>

        <div class="summary-stats">
          <div class="stat-card">
            <div class="stat-label">Avg score</div>
            <div class="stat-row">
              <span :class="['stat-value', scoreColor(runSummary.avg)]">{{ fmtScore(runSummary.avg) }}</span>
              <span v-if="runSummary.deltaAvg !== null && runSummary.deltaAvg !== undefined"
                :class="['stat-delta', deltaColor(runSummary.deltaAvg)]">{{ fmtDelta(runSummary.deltaAvg) }}</span>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Type accuracy</div>
            <div class="stat-row">
              <span class="stat-value">{{ fmtPct(runSummary.typeAcc) }}</span>
              <span v-if="runSummary.deltaTypeAcc !== null && runSummary.deltaTypeAcc !== undefined"
                :class="['stat-delta', deltaColor(runSummary.deltaTypeAcc)]">
                {{ runSummary.deltaTypeAcc >= 0 ? '+' : '' }}{{ (runSummary.deltaTypeAcc * 100).toFixed(0) }}%
              </span>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Min / Max</div>
            <div class="stat-value-small">
              <span :class="scoreColor(runSummary.min)">{{ fmtScore(runSummary.min) }}</span>
              <span class="stat-sep">/</span>
              <span :class="scoreColor(runSummary.max)">{{ fmtScore(runSummary.max) }}</span>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Оценено</div>
            <div class="stat-value">{{ runSummary.count }} / {{ runSummary.total }}</div>
          </div>
          <div v-if="runSummary.errorCount" class="stat-card">
            <div class="stat-label">Ошибки</div>
            <div class="stat-value score-red">{{ runSummary.errorCount }}</div>
          </div>
          <div v-if="runSummary.avgLatency" class="stat-card">
            <div class="stat-label">Latency avg</div>
            <div class="stat-value">{{ (runSummary.avgLatency / 1000).toFixed(1) }}с</div>
          </div>
        </div>
        <div class="category-stats">
          <div v-for="(info, cat) in runSummary.byCategory" :key="cat" class="category-row">
            <span :class="['cat-badge', categoryBadgeClass(cat)]">{{ cat }}</span>
            <span class="cat-stat">{{ info.total }} вопросов</span>
            <span v-if="info.scored" :class="['score-val', scoreColor(info.sum / info.scored)]">
              avg {{ (info.sum / info.scored).toFixed(3) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Tab: История ───────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'history'" class="history-tab">
      <!-- Compare button -->
      <div class="history-actions">
        <button
          v-if="runs.length >= 2"
          class="compare-btn"
          :disabled="compareLoading"
          @click="compareLastTwo"
        >
          {{ compareLoading ? 'Сравниваем...' : 'Сравнить последние 2 прогона' }}
        </button>
      </div>

      <!-- Comparison view -->
      <div v-if="compareData" class="compare-block panel">
        <div class="compare-banner">
          <span>
            avg score:
            <span :class="['score-val', scoreColor(compareData.summary.avg_score_a)]">{{ fmtScore(compareData.summary.avg_score_a) }}</span>
            →
            <span :class="['score-val', scoreColor(compareData.summary.avg_score_b)]">{{ fmtScore(compareData.summary.avg_score_b) }}</span>
            <span v-if="compareData.summary.avg_score_a !== null && compareData.summary.avg_score_b !== null"
              :class="['delta-inline', deltaColor(compareData.summary.avg_score_b - compareData.summary.avg_score_a)]">
              ({{ fmtDelta(compareData.summary.avg_score_b - compareData.summary.avg_score_a) }})
            </span>
          </span>
          <span class="compare-sep">|</span>
          <span class="compare-stat improved">улучшилось: {{ compareData.summary.improved }}</span>
          <span class="compare-sep">|</span>
          <span class="compare-stat degraded">ухудшилось: {{ compareData.summary.degraded }}</span>
          <span class="compare-sep">|</span>
          <span class="compare-stat">тип изменился: {{ compareData.summary.type_changes }}</span>
        </div>

        <div class="compare-runs-label">
          <span class="run-label-a">Прогон #{{ compareData.run_a.id }} {{ formatDate(compareData.run_a.ran_at) }}</span>
          <span class="compare-arrow">→</span>
          <span class="run-label-b">Прогон #{{ compareData.run_b.id }} {{ formatDate(compareData.run_b.ran_at) }}</span>
        </div>

        <div class="table-wrap compare-table-wrap">
          <table class="log-table">
            <colgroup>
              <col style="width: auto" />
              <col style="width: 100px" />
              <col style="width: 80px" />
              <col style="width: 80px" />
              <col style="width: 70px" />
              <col style="width: 110px" />
              <col style="width: 110px" />
            </colgroup>
            <thead>
              <tr>
                <th>Вопрос</th>
                <th>Категория</th>
                <th>Score A</th>
                <th>Score B</th>
                <th>Дельта</th>
                <th>Тип A</th>
                <th>Тип B</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="q in compareData.questions"
                :key="q.id"
                class="log-row"
                :class="{ 'row-changed': q.type_changed || (q.score_delta !== null && Math.abs(q.score_delta) > 0.001) }"
              >
                <td class="cell-q">{{ q.question }}</td>
                <td><span :class="['cat-badge', categoryBadgeClass(q.category)]">{{ q.category }}</span></td>
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

      <!-- Runs list -->
      <div v-if="runsLoading" class="loading-state"><AjaxFrog /></div>
      <div v-else-if="runs.length === 0" class="empty-state-box">Прогонов ещё нет</div>
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
            <div v-if="expandedLoading" class="loading-state"><AjaxFrog /></div>
            <div v-else-if="expandedRunData">
              <!-- Per-run summary with delta vs previous -->
              <div v-if="expandedSummary" class="summary-block panel summary-inline">
                <h3 class="summary-title">
                  Итоги прогона
                  <span v-if="expandedSummary.previousRunId" class="vs-prev">vs прогон #{{ expandedSummary.previousRunId }}</span>
                </h3>

                <div v-if="expandedSummary.quality !== null && expandedSummary.quality !== undefined" class="quality-headline">
                  <div class="quality-block">
                    <div class="stat-label">Quality score</div>
                    <div class="quality-row">
                      <span :class="['quality-big', qualityColor(expandedSummary.quality)]">{{ expandedSummary.quality.toFixed(1) }}</span>
                      <span class="quality-max">/ 100</span>
                      <span v-if="expandedSummary.deltaQuality !== null && expandedSummary.deltaQuality !== undefined"
                        :class="['quality-delta-big', deltaQualityColor(expandedSummary.deltaQuality)]">
                        {{ fmtDeltaQuality(expandedSummary.deltaQuality) }}
                      </span>
                    </div>
                    <div class="quality-formula">0.7 · avg_score + 0.3 · type_accuracy</div>
                  </div>
                </div>

                <div class="summary-stats">
                  <div class="stat-card">
                    <div class="stat-label">Avg score</div>
                    <div class="stat-row">
                      <span :class="['stat-value', scoreColor(expandedSummary.avg)]">{{ fmtScore(expandedSummary.avg) }}</span>
                      <span v-if="expandedSummary.deltaAvg !== null && expandedSummary.deltaAvg !== undefined"
                        :class="['stat-delta', deltaColor(expandedSummary.deltaAvg)]">{{ fmtDelta(expandedSummary.deltaAvg) }}</span>
                    </div>
                  </div>
                  <div class="stat-card">
                    <div class="stat-label">Type accuracy</div>
                    <div class="stat-row">
                      <span class="stat-value">{{ fmtPct(expandedSummary.typeAcc) }}</span>
                      <span v-if="expandedSummary.deltaTypeAcc !== null && expandedSummary.deltaTypeAcc !== undefined"
                        :class="['stat-delta', deltaColor(expandedSummary.deltaTypeAcc)]">
                        {{ expandedSummary.deltaTypeAcc >= 0 ? '+' : '' }}{{ (expandedSummary.deltaTypeAcc * 100).toFixed(0) }}%
                      </span>
                    </div>
                  </div>
                  <div class="stat-card">
                    <div class="stat-label">Min / Max</div>
                    <div class="stat-value-small">
                      <span :class="scoreColor(expandedSummary.min)">{{ fmtScore(expandedSummary.min) }}</span>
                      <span class="stat-sep">/</span>
                      <span :class="scoreColor(expandedSummary.max)">{{ fmtScore(expandedSummary.max) }}</span>
                    </div>
                  </div>
                  <div class="stat-card">
                    <div class="stat-label">Оценено</div>
                    <div class="stat-value">{{ expandedSummary.count }} / {{ expandedSummary.total }}</div>
                  </div>
                  <div v-if="expandedSummary.errorCount" class="stat-card">
                    <div class="stat-label">Ошибки</div>
                    <div class="stat-value score-red">{{ expandedSummary.errorCount }}</div>
                  </div>
                  <div v-if="expandedSummary.avgLatency" class="stat-card">
                    <div class="stat-label">Latency avg</div>
                    <div class="stat-value">{{ (expandedSummary.avgLatency / 1000).toFixed(1) }}с</div>
                  </div>
                </div>
                <div class="category-stats">
                  <div v-for="(info, cat) in expandedSummary.byCategory" :key="cat" class="category-row">
                    <span :class="['cat-badge', categoryBadgeClass(cat)]">{{ cat }}</span>
                    <span class="cat-stat">{{ info.total }} вопросов</span>
                    <span v-if="info.scored" :class="['score-val', scoreColor(info.sum / info.scored)]">
                      avg {{ (info.sum / info.scored).toFixed(3) }}
                    </span>
                  </div>
                </div>
              </div>

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
                  <template v-for="r in expandedRunData.results" :key="r.question_id">
                    <tr class="log-row clickable-row" :class="{ 'row-open': expandedAnswerIds.has(r.question_id) }" @click="toggleAnswer(r.question_id)">
                      <td class="cell-num">{{ r.question_id }}</td>
                      <td><span :class="['cat-badge', categoryBadgeClass(r.category)]">{{ r.category }}</span></td>
                      <td class="cell-q">{{ r.question }}</td>
                      <td><span :class="['qtype-badge', qtypeCls(r.expected_type)]">{{ qtypeLabel(r.expected_type) }}</span></td>
                      <td>
                        <span v-if="r.error" class="error-note" :title="r.error">ERR</span>
                        <span v-else-if="r.actual_type" :class="['qtype-badge', qtypeCls(r.actual_type)]">{{ qtypeLabel(r.actual_type) }}</span>
                        <span v-else class="score-none">—</span>
                      </td>
                      <td class="cell-score">
                        <span v-if="r.top_score !== null && r.top_score !== undefined" :class="['score-val', scoreColor(r.top_score)]">
                          {{ r.top_score.toFixed(3) }}
                        </span>
                        <span v-else class="score-none">—</span>
                      </td>
                      <td class="cell-num latency">{{ r.latency_ms !== null ? r.latency_ms + 'ms' : '—' }}</td>
                    </tr>
                    <tr v-if="expandedAnswerIds.has(r.question_id)" class="answer-row">
                      <td colspan="7">
                        <div v-if="r.error" class="answer-error">⚠ {{ r.error }}</div>
                        <div v-else-if="r.answer" class="answer-body" v-html="r.answer"></div>
                        <div v-else class="answer-empty">Ответ не сохранён</div>
                      </td>
                    </tr>
                  </template>
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
.eval-view {
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  min-height: 100%;
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-4);
  flex-wrap: wrap;
}

.page-title-block {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
}

.page-title {
  margin: 0;
  font-size: var(--fs-20);
  font-weight: var(--fw-bold);
  color: var(--fg-1);
}

.page-count {
  font-size: var(--fs-13);
  color: var(--fg-3);
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
.tabs {
  display: flex;
  gap: 2px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: 3px;
}

.tab-btn {
  padding: var(--sp-2) var(--sp-4);
  border: 0;
  border-radius: var(--rad-md);
  background: transparent;
  color: var(--fg-2);
  font: inherit;
  font-size: var(--fs-13);
  font-weight: var(--fw-medium);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  transition: background var(--dur-fast), color var(--dur-fast);
}

.tab-btn:hover {
  background: var(--bg-hover);
  color: var(--fg-1);
}

.tab-btn.active {
  background: var(--bg-elevated);
  color: var(--accent);
  box-shadow: var(--shadow-1);
  font-weight: var(--fw-semibold);
}

.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-soft);
  color: var(--accent);
  border-radius: 99px;
  font-size: var(--fs-11);
  font-weight: var(--fw-bold);
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
}

/* ── Panel / Table wrap ─────────────────────────────────────────────────── */
.panel {
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-4);
}

.table-wrap {
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  overflow: hidden;
}

.loading-state {
  padding: var(--sp-8);
  text-align: center;
  color: var(--fg-3);
  font-size: var(--fs-13);
}

.empty-state-box {
  padding: var(--sp-8);
  text-align: center;
  color: var(--fg-3);
  font-size: var(--fs-13);
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
}

/* ── Table ────────────────────────────────────────────────────────────────── */
.log-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: var(--fs-13);
}

.log-table th {
  padding: var(--sp-2) var(--sp-3);
  background: var(--bg-panel-2);
  border-bottom: 1px solid var(--border-1);
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  color: var(--fg-3);
  text-align: left;
  white-space: nowrap;
}

.log-table td {
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid var(--border-2);
  vertical-align: middle;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-row {
  cursor: default;
  transition: background var(--dur-fast);
}

.log-row:hover {
  background: var(--bg-hover);
}

.row-changed {
  background: var(--accent-soft);
}

.cell-q {
  color: var(--fg-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-num {
  text-align: center;
  color: var(--fg-2);
  white-space: nowrap;
}

.clickable-row {
  cursor: pointer;
  transition: background var(--dur-fast);
}

.clickable-row:hover {
  background: var(--bg-hover);
}

.clickable-row.row-open {
  background: var(--bg-panel-2);
}

.answer-row > td {
  padding: 0 !important;
  border-bottom: 1px solid var(--border-1);
  background: var(--bg-panel-2);
  white-space: normal;
  overflow: visible;
}

.answer-body {
  padding: var(--sp-3) var(--sp-5);
  font-size: var(--fs-13);
  line-height: 1.55;
  color: var(--fg-1);
  white-space: pre-wrap;
  word-break: break-word;
}

.answer-body :deep(b) {
  font-weight: var(--fw-bold);
}

.answer-body :deep(code) {
  background: var(--bg-elevated);
  padding: 1px 5px;
  border-radius: var(--rad-sm);
  font-family: var(--font-mono, monospace);
  font-size: 0.92em;
}

.answer-error {
  padding: var(--sp-3) var(--sp-5);
  font-size: var(--fs-13);
  color: var(--ark-red-600);
  white-space: pre-wrap;
}

.answer-empty {
  padding: var(--sp-3) var(--sp-5);
  font-size: var(--fs-13);
  color: var(--fg-3);
  font-style: italic;
}

.log-table td.cell-score {
  text-align: right;
  overflow: visible;
  text-overflow: clip;
  white-space: nowrap;
}

.latency {
  color: var(--fg-3);
  font-size: var(--fs-12);
}

/* ── Category badges ──────────────────────────────────────────────────────── */
.cat-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: var(--rad-sm);
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  letter-spacing: 0.03em;
}

.cat-selection  { background: var(--ark-blue-100);                color: var(--ark-blue-700); }
.cat-specs      { background: var(--ark-purple-100);              color: var(--ark-purple-700); }
.cat-install    { background: var(--ark-yellow-100, #fef9c3);     color: #854d0e; }
.cat-company    { background: var(--ark-green-100);               color: var(--ark-green-600); }
.cat-dealer     { background: #fed7aa;                            color: #9a3412; }

/* ── Query type badges ────────────────────────────────────────────────────── */
.qtype-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: var(--rad-sm);
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  letter-spacing: 0.03em;
}

.qt-rag    { background: var(--ark-blue-100);              color: var(--ark-blue-700); }
.qt-faq    { background: var(--ark-green-100);             color: var(--ark-green-600); }
.qt-ref    { background: var(--ark-yellow-100, #fef9c3);   color: #854d0e; }
.qt-dealer { background: var(--ark-purple-100);            color: var(--ark-purple-700); }
.qt-error  { background: var(--ark-red-100);               color: var(--ark-red-600); }

.type-changed {
  outline: 1px solid currentColor;
  outline-offset: 1px;
}

/* ── Score values ─────────────────────────────────────────────────────────── */
.score-val {
  font-size: var(--fs-12);
  font-variant-numeric: tabular-nums;
  font-weight: var(--fw-semibold);
}

.score-green  { color: var(--ark-green-600); }
.score-yellow { color: #b45309; }
.score-red    { color: var(--ark-red-600); }
.score-muted  { color: var(--fg-3); }
.score-none   { color: var(--fg-4); }

.delta-inline {
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  margin-left: 4px;
}

.error-note {
  font-size: var(--fs-11);
  font-weight: var(--fw-bold);
  color: var(--ark-red-600);
  background: var(--ark-red-100);
  padding: 1px 5px;
  border-radius: var(--rad-sm);
  cursor: help;
}

/* ── Run tab ──────────────────────────────────────────────────────────────── */
.run-tab {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.run-controls {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.run-controls-inner {
  display: flex;
  gap: var(--sp-3);
  align-items: center;
}

.note-input {
  flex: 1;
  max-width: 300px;
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  color: var(--fg-1);
  font: inherit;
  font-size: var(--fs-13);
}

.note-input:focus {
  outline: none;
  border-color: var(--accent);
}

.run-btn {
  padding: var(--sp-2) var(--sp-5);
  border: 0;
  border-radius: var(--rad-md);
  background: var(--accent);
  color: #fff;
  font: inherit;
  font-size: var(--fs-13);
  font-weight: var(--fw-semibold);
  cursor: pointer;
  transition: opacity var(--dur-fast);
  white-space: nowrap;
}

.run-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.run-btn:not(:disabled):hover {
  opacity: 0.88;
}

.progress-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.progress-bar {
  height: 6px;
  background: var(--border-1);
  border-radius: 99px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 99px;
  transition: width 0.4s ease;
}

.progress-label {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--fg-2);
}

.run-status {
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  padding: 1px 6px;
  border-radius: var(--rad-sm);
}

.status-running { background: var(--ark-blue-100);             color: var(--ark-blue-700); }
.status-done    { background: var(--ark-green-100);            color: var(--ark-green-600); }
.status-error   { background: var(--ark-red-100);              color: var(--ark-red-600); }

/* ── Summary stats ────────────────────────────────────────────────────────── */
.summary-block {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.summary-title {
  margin: 0;
  font-size: var(--fs-15);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
}

.vs-prev {
  font-size: var(--fs-12);
  color: var(--fg-3);
  font-weight: var(--fw-medium);
}

.summary-inline {
  margin: var(--sp-3) var(--sp-4);
  background: var(--bg-panel-2);
}

.quality-headline {
  display: flex;
}

.quality-block {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-3) var(--sp-5);
  min-width: 240px;
}

.quality-row {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  margin-top: var(--sp-1);
}

.quality-big {
  font-size: 36px;
  font-weight: var(--fw-bold);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.quality-max {
  font-size: var(--fs-13);
  color: var(--fg-3);
}

.quality-delta-big {
  font-size: var(--fs-15);
  font-weight: var(--fw-bold);
  font-variant-numeric: tabular-nums;
  margin-left: var(--sp-2);
}

.quality-formula {
  font-size: var(--fs-11);
  color: var(--fg-3);
  font-style: italic;
  margin-top: var(--sp-1);
}

.stat-row {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
}

.stat-delta {
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  font-variant-numeric: tabular-nums;
}

.stat-value-small {
  font-size: var(--fs-15);
  font-weight: var(--fw-semibold);
  font-variant-numeric: tabular-nums;
  color: var(--fg-1);
  display: flex;
  gap: var(--sp-1);
  align-items: baseline;
}

.stat-sep {
  color: var(--fg-3);
}

.summary-stats {
  display: flex;
  gap: var(--sp-3);
  flex-wrap: wrap;
}

.stat-card {
  background: var(--bg-panel-2);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  padding: var(--sp-3) var(--sp-4);
  min-width: 100px;
}

.stat-label {
  font-size: var(--fs-11);
  color: var(--fg-3);
  font-weight: var(--fw-semibold);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--sp-1);
}

.stat-value {
  font-size: var(--fs-20);
  font-weight: var(--fw-bold);
  font-variant-numeric: tabular-nums;
  color: var(--fg-1);
}

.category-stats {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.category-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-13);
}

.cat-stat {
  color: var(--fg-3);
  font-size: var(--fs-12);
}

/* ── History tab ──────────────────────────────────────────────────────────── */
.history-tab {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.history-actions {
  display: flex;
  gap: var(--sp-3);
}

.compare-btn {
  padding: var(--sp-2) var(--sp-4);
  border: 1px solid var(--accent);
  border-radius: var(--rad-md);
  background: transparent;
  color: var(--accent);
  font: inherit;
  font-size: var(--fs-13);
  font-weight: var(--fw-semibold);
  cursor: pointer;
  transition: background var(--dur-fast);
}

.compare-btn:hover:not(:disabled) {
  background: var(--accent-soft);
}

.compare-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ── Compare block ────────────────────────────────────────────────────────── */
.compare-block {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.compare-banner {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
  padding: var(--sp-3) var(--sp-4);
  background: var(--bg-panel-2);
  border-radius: var(--rad-md);
  font-size: var(--fs-13);
  color: var(--fg-1);
}

.compare-sep {
  color: var(--fg-4);
}

.compare-stat { font-size: var(--fs-13); color: var(--fg-2); }
.compare-stat.improved { color: var(--ark-green-600); font-weight: var(--fw-semibold); }
.compare-stat.degraded { color: var(--ark-red-600);   font-weight: var(--fw-semibold); }

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

.compare-table-wrap {
  margin-top: var(--sp-1);
}

/* ── Runs list ────────────────────────────────────────────────────────────── */
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
}
</style>
