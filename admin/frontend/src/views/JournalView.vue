<script setup>
import { ref, computed, watch, onMounted, inject } from 'vue'
import { api } from '@/api/index.js'
import AjaxFrog from '@/components/AjaxFrog.vue'
import { qtypeCls, qtypeLabel } from '@/utils/badges.js'

const toast = inject('toast')
const logs = ref([])
const total = ref(0)
const page = ref(1)
const perPage = 50
const loading = ref(false)

const filterType = ref('')
const filterFeedback = ref('')
const search = ref('')
const searchInput = ref('')

const dateFrom = ref('')
const dateTo = ref('')
const exporting = ref(false)

const totalPages = computed(() => Math.ceil(total.value / perPage))

const selected = ref(null)
const faqSaving = ref(false)
const contextTurns = ref([])
const contextLoading = ref(false)

async function openLog(log) {
  if (selected.value?.id === log.id) {
    selected.value = null
    contextTurns.value = []
    return
  }
  selected.value = log
  contextTurns.value = []
  if (!log.user_id) return
  contextLoading.value = true
  try {
    const res = await api.getJournalContext(log.id)
    contextTurns.value = res.data || []
  } catch {
    contextTurns.value = []
  } finally {
    contextLoading.value = false
  }
}

function closeDetail() {
  selected.value = null
  contextTurns.value = []
}

async function addToFaq(log) {
  if (faqSaving.value) return
  faqSaving.value = true
  try {
    await api.createFaqEntry({
      question: log.question,
      answer: log.answer,
      source_log_id: log.id,
    })
    toast('Добавлено в FAQ', 'success')
  } catch {
    toast('Ошибка добавления в FAQ', 'error')
  } finally {
    faqSaving.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: perPage }
    if (filterType.value) params.query_type = filterType.value
    if (filterFeedback.value) params.feedback = filterFeedback.value
    if (search.value) params.search = search.value
    const res = await api.getJournal(params)
    logs.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function applySearch() {
  search.value = searchInput.value.trim()
  page.value = 1
  load()
}

async function exportReport() {
  if (exporting.value) return
  exporting.value = true
  try {
    // Send the viewer's tz offset (minutes to add to UTC) so date filtering
    // and the timestamps in the report match what's shown in the table.
    const params = { tz_offset_min: -new Date().getTimezoneOffset() }
    if (filterType.value) params.query_type = filterType.value
    if (filterFeedback.value) params.feedback = filterFeedback.value
    if (search.value) params.search = search.value
    if (dateFrom.value) params.date_from = dateFrom.value
    if (dateTo.value) params.date_to = dateTo.value

    const res = await api.exportJournal(params)
    const blob = new Blob([res.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const cd = res.headers['content-disposition'] || ''
    const m = cd.match(/filename="?([^"]+)"?/)
    a.download = m ? m[1] : `teplodar-journal_${dateFrom.value || 'all'}_${dateTo.value || 'all'}.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    toast('Отчёт выгружен', 'success')
  } catch {
    toast('Ошибка выгрузки отчёта', 'error')
  } finally {
    exporting.value = false
  }
}

function onKeydown(e) {
  if (e.key === 'Enter') applySearch()
}

watch([filterType, filterFeedback], () => {
  page.value = 1
  load()
})

onMounted(load)

function scoreColor(score) {
  if (score === null || score === undefined) return ''
  if (score >= 0.85) return 'score-green'
  if (score >= 0.80) return 'score-yellow'
  return 'score-red'
}

function usefulnessColor(s) {
  if (s == null) return ''
  if (s >= 75) return 'score-green'
  if (s >= 50) return 'score-yellow'
  return 'score-red'
}

function feedbackLabel(fb) {
  if (fb === 'good') return { label: '👍', cls: 'fb-good' }
  if (fb === 'bad') return { label: '👎', cls: 'fb-bad' }
  if (fb === 'operator') return { label: '🆘', cls: 'fb-op' }
  return null
}

function formatTs(ts) {
  const d = new Date(ts)
  const date = d.toLocaleDateString('ru', { day: '2-digit', month: '2-digit' })
  const time = d.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })
  return `${date} ${time}`
}
</script>

<template>
  <div class="journal-view">
    <!-- Header -->
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">Журнал</h1>
        <span class="page-count">{{ total.toLocaleString('ru') }} запросов</span>
      </div>

      <div class="filters">
        <div class="search-wrap">
          <input
            v-model="searchInput"
            class="search-input"
            placeholder="Поиск по тексту вопроса..."
            @keydown="onKeydown"
          />
          <button class="search-btn" @click="applySearch">Найти</button>
        </div>

        <select v-model="filterType" class="filter-select">
          <option value="">Все типы</option>
          <option value="RAG_PRODUCT">RAG</option>
          <option value="FAQ_EXACT">FAQ</option>
          <option value="FAQ_COMPANY">О компании</option>
          <option value="FAQ_DEALER">Дилер</option>
          <option value="ERROR">Ошибка</option>
        </select>

        <select v-model="filterFeedback" class="filter-select">
          <option value="">Любая оценка</option>
          <option value="good">👍 Хорошо</option>
          <option value="bad">👎 Плохо</option>
          <option value="operator">🆘 Оператор</option>
          <option value="none">Без оценки</option>
        </select>

        <div class="export-group">
          <input v-model="dateFrom" type="date" class="filter-select date-input" title="Дата: с" />
          <span class="date-sep">–</span>
          <input v-model="dateTo" type="date" class="filter-select date-input" title="Дата: по" />
          <button class="export-btn" :disabled="exporting" @click="exportReport" title="Скачать журнал в Excel (учитывает выбранные фильтры и даты)">
            {{ exporting ? 'Готовлю…' : '⬇ Выгрузить отчёт' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Table -->
    <div class="table-wrap">
      <div v-if="loading" class="loading-state"><AjaxFrog /></div>
      <table v-else class="log-table">
        <colgroup>
          <col style="width: 96px" />
          <col style="width: 64px" />
          <col style="width: 96px" />
          <col style="width: 260px" />
          <col style="width: auto" />
          <col style="width: 64px" />
          <col style="width: 56px" />
          <col style="width: 44px" />
          <col style="width: 36px" />
          <col style="width: 52px" />
        </colgroup>
        <thead>
          <tr>
            <th>Время</th>
            <th>Тип</th>
            <th>Пользователь</th>
            <th>Вопрос</th>
            <th>Ответ</th>
            <th>Score</th>
            <th title="LLM-judge usefulness 0–100">Useful</th>
            <th>Чанки</th>
            <th>Оц.</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="log in logs"
            :key="log.id"
            class="log-row"
            :class="{ 'row-selected': selected?.id === log.id }"
            @click="openLog(log)"
          >
            <td class="cell-ts">{{ formatTs(log.ts) }}</td>
            <td><span :class="['qtype-badge', qtypeCls(log.query_type)]">{{ qtypeLabel(log.query_type) }}</span></td>
            <td class="cell-user">{{ log.username ? '@' + log.username : log.user_id || '—' }}</td>
            <td class="cell-q">{{ log.question }}</td>
            <td class="cell-a">{{ log.answer }}</td>
            <td class="cell-score">
              <span v-if="log.top_score !== null && log.top_score !== undefined" :class="['score-val', scoreColor(log.top_score)]">
                {{ log.top_score.toFixed(3) }}
              </span>
              <span v-else class="score-none">—</span>
            </td>
            <td class="cell-score">
              <span v-if="log.usefulness_score !== null && log.usefulness_score !== undefined"
                    :class="['usefulness-pill', usefulnessColor(log.usefulness_score)]"
                    :title="log.usefulness_verdict || ''">
                {{ log.usefulness_score }}
              </span>
              <span v-else class="score-none" title="LLM-judge ещё не отработал">…</span>
            </td>
            <td class="cell-num">{{ log.chunks_used ?? '—' }}</td>
            <td class="cell-fb">
              <span v-if="feedbackLabel(log.feedback)" :class="['fb-icon', feedbackLabel(log.feedback).cls]">
                {{ feedbackLabel(log.feedback).label }}
              </span>
            </td>
            <td class="cell-faq">
              <button class="row-faq-btn" title="В FAQ" @click.stop="addToFaq(log)">→</button>
            </td>
          </tr>
          <tr v-if="logs.length === 0">
            <td colspan="10" class="empty-state">Нет записей</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Detail panel -->
    <Teleport to="body">
      <div v-if="selected" class="detail-overlay" @click.self="closeDetail()">
        <div class="detail-panel">
          <div class="detail-header">
            <div class="detail-meta">
              <span :class="['qtype-badge', qtypeCls(selected.query_type)]">{{ qtypeLabel(selected.query_type) }}</span>
              <span class="detail-ts">{{ formatTs(selected.ts) }}</span>
              <span v-if="selected.username" class="detail-user">@{{ selected.username }}</span>
              <span v-else-if="selected.user_id" class="detail-user">id:{{ selected.user_id }}</span>
              <span v-if="selected.top_score !== null && selected.top_score !== undefined" :class="['score-val', scoreColor(selected.top_score)]">
                score {{ selected.top_score.toFixed(3) }}
              </span>
              <span v-if="selected.chunks_used" class="detail-chunks">{{ selected.chunks_used }} чанков</span>
              <span v-if="selected.city" class="detail-city">{{ selected.city }}</span>
              <span v-if="feedbackLabel(selected.feedback)" :class="['fb-badge', feedbackLabel(selected.feedback).cls]">
                {{ feedbackLabel(selected.feedback).label }} {{ { good: 'Полезно', bad: 'Не помогло', operator: 'Оператор' }[selected.feedback] }}
              </span>
              <span v-else class="fb-badge fb-none">— без оценки</span>
            </div>
            <button class="faq-add-btn" :disabled="faqSaving" @click="addToFaq(selected)" title="Добавить в FAQ">
            {{ faqSaving ? '...' : '→ FAQ' }}
          </button>
          <button class="detail-close" @click="closeDetail()">✕</button>
          </div>

          <div class="detail-body">
            <!-- Dialog context: previous turns from the same user -->
            <div v-if="contextLoading || contextTurns.length" class="detail-section">
              <div class="detail-label">Контекст диалога (предыдущие сообщения)</div>
              <div v-if="contextLoading" class="context-loading">
                <AjaxFrog text="Загружаю контекст…" size="18px" />
              </div>
              <div v-else class="context-thread">
                <div v-for="turn in contextTurns" :key="turn.id" class="context-turn">
                  <div class="context-q">
                    <span class="context-role">Q</span>
                    <span class="context-content">{{ turn.question }}</span>
                  </div>
                  <div class="context-a">
                    <span class="context-role">A</span>
                    <span class="context-content">{{ turn.answer }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="detail-section">
              <div class="detail-label">Вопрос</div>
              <div class="detail-text detail-q">{{ selected.question }}</div>
            </div>
            <div v-if="selected.reformulated_query" class="detail-section">
              <div class="detail-label">Переформулировка</div>
              <div class="detail-text detail-ref">{{ selected.reformulated_query }}</div>
            </div>
            <div class="detail-section">
              <div class="detail-label">Ответ</div>
              <div class="detail-text detail-a">{{ selected.answer }}</div>
            </div>
            <div v-if="selected.usefulness_verdict" class="detail-section">
              <div class="detail-label">⚖️ Оценка LLM-судьи: {{ selected.usefulness_score }}/100</div>
              <div class="detail-text detail-verdict">{{ selected.usefulness_verdict }}</div>
            </div>
            <div v-if="selected.feedback_note" class="detail-section">
              <div class="detail-label">👎 Что не так (от пользователя)</div>
              <div class="detail-text detail-note">{{ selected.feedback_note }}</div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="pagination">
      <button class="page-btn" :disabled="page === 1" @click="page--; load()">←</button>
      <span class="page-info">{{ page }} / {{ totalPages }}</span>
      <button class="page-btn" :disabled="page >= totalPages" @click="page++; load()">→</button>
    </div>
  </div>
</template>

<style scoped>
.journal-view {
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  min-height: 100%;
}

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

.filters {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

.search-wrap {
  display: flex;
  gap: 0;
}

.search-input {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-right: 0;
  border-radius: var(--rad-md) 0 0 var(--rad-md);
  background: var(--bg-elevated);
  color: var(--fg-1);
  font: inherit;
  font-size: var(--fs-13);
  width: 220px;
}

.search-input:focus {
  outline: none;
  border-color: var(--accent);
}

.search-btn {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: 0 var(--rad-md) var(--rad-md) 0;
  background: var(--bg-elevated);
  color: var(--fg-1);
  font: inherit;
  font-size: var(--fs-13);
  cursor: pointer;
}

.search-btn:hover {
  background: var(--bg-hover);
}

.filter-select {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  color: var(--fg-1);
  font: inherit;
  font-size: var(--fs-13);
  cursor: pointer;
}

.export-group {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-left: var(--sp-2);
  padding-left: var(--sp-3);
  border-left: 1px solid var(--border-1);
}

.date-input {
  color: var(--fg-2);
  padding-right: var(--sp-2);
}

.date-sep {
  color: var(--fg-3);
  font-size: var(--fs-13);
}

.export-btn {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--accent);
  border-radius: var(--rad-md);
  background: var(--accent);
  color: #fff;
  font: inherit;
  font-size: var(--fs-13);
  font-weight: var(--fw-semibold);
  cursor: pointer;
  white-space: nowrap;
}

.export-btn:hover:not(:disabled) { filter: brightness(1.06); }
.export-btn:disabled { opacity: .55; cursor: default; }

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
  cursor: pointer;
  transition: background var(--dur-fast);
}

.log-row:hover {
  background: var(--bg-hover);
}

.row-selected {
  background: var(--accent-soft) !important;
}

.cell-ts {
  color: var(--fg-3);
  font-size: var(--fs-12);
  white-space: nowrap;
}

.cell-user {
  color: var(--fg-2);
  font-size: var(--fs-12);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-q {
  color: var(--fg-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

.cell-a {
  color: var(--fg-3);
  font-size: var(--fs-12);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-faq {
  text-align: center;
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
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-soft);
}

.log-table td.cell-score {
  text-align: right;
  overflow: visible;
  text-overflow: clip;
  white-space: nowrap;
}
.cell-num { text-align: center; color: var(--fg-2); white-space: nowrap; }
.log-table td.cell-fb { text-align: center; white-space: nowrap; overflow: visible; text-overflow: clip; }



.fb-icon { font-size: 15px; }

.fb-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--rad-md);
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
}

.fb-badge.fb-good { background: var(--ark-green-100); color: var(--ark-green-600); }
.fb-badge.fb-bad  { background: var(--ark-red-100);   color: var(--ark-red-600); }
.fb-badge.fb-op   { background: var(--ark-yellow-100, #fef9c3); color: #854d0e; }
.fb-badge.fb-none { color: var(--fg-4); font-size: var(--fs-12); background: none; padding: 0; }

.empty-state {
  text-align: center;
  padding: var(--sp-8);
  color: var(--fg-3);
}

/* Detail panel */
.detail-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.4);
  z-index: 200;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
}

.detail-panel {
  width: 560px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-panel);
  border-left: 1px solid var(--border-1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-4);
  border-bottom: 1px solid var(--border-1);
  flex-shrink: 0;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2);
}

.detail-ts, .detail-user, .detail-chunks, .detail-city {
  font-size: var(--fs-12);
  color: var(--fg-3);
}

.faq-add-btn {
  flex: none;
  border: 1px solid var(--accent);
  background: transparent;
  color: var(--accent);
  font: inherit;
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  cursor: pointer;
  padding: 3px 10px;
  border-radius: var(--rad-md);
  transition: background var(--dur-fast);
}

.faq-add-btn:hover { background: var(--accent-soft); }
.faq-add-btn:disabled { opacity: .5; cursor: default; }

.detail-close {
  flex: none;
  border: 0;
  background: transparent;
  color: var(--fg-3);
  font-size: 16px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--rad-sm);
}

.detail-close:hover { background: var(--bg-hover); color: var(--fg-1); }

.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.detail-label {
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--fg-3);
}

.detail-text {
  font-size: var(--fs-13);
  line-height: var(--lh-relaxed);
  color: var(--fg-1);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-q {
  font-weight: var(--fw-medium);
}

.detail-ref {
  color: var(--fg-2);
  font-style: italic;
}

.detail-note {
  background: color-mix(in srgb, var(--ark-red-600) 8%, transparent);
  border-left: 3px solid var(--ark-red-600);
  padding: var(--sp-3);
  border-radius: var(--rad-sm);
  color: var(--fg-1);
}

.detail-verdict {
  background: color-mix(in srgb, var(--ark-amber-600) 8%, transparent);
  border-left: 3px solid var(--ark-amber-600);
  padding: var(--sp-3);
  border-radius: var(--rad-sm);
  color: var(--fg-1);
  font-style: italic;
}

.usefulness-pill {
  display: inline-block;
  font-size: var(--fs-12);
  font-weight: var(--fw-bold);
  padding: 2px 8px;
  border-radius: var(--rad-sm);
  font-variant-numeric: tabular-nums;
  cursor: help;
}
.usefulness-pill.score-green { background: color-mix(in srgb, var(--ark-green-600) 15%, transparent); }
.usefulness-pill.score-yellow { background: color-mix(in srgb, var(--ark-amber-600) 15%, transparent); }
.usefulness-pill.score-red { background: color-mix(in srgb, var(--ark-red-600) 15%, transparent); }

.context-loading {
  padding: var(--sp-2) 0;
  color: var(--fg-3);
}

.context-thread {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  background: color-mix(in srgb, var(--ark-blue-600) 5%, transparent);
  border-left: 3px solid var(--ark-blue-600);
  padding: var(--sp-3);
  border-radius: var(--rad-sm);
}

.context-turn {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
  font-size: var(--fs-13);
}

.context-turn + .context-turn {
  margin-top: var(--sp-2);
  padding-top: var(--sp-2);
  border-top: 1px dashed var(--border-1);
}

.context-q, .context-a {
  display: flex;
  gap: var(--sp-2);
  align-items: flex-start;
  line-height: 1.4;
}

.context-role {
  display: inline-block;
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 10px;
  font-weight: var(--fw-bold);
  line-height: 18px;
  text-align: center;
  color: white;
  margin-top: 2px;
}

.context-q .context-role {
  background: var(--fg-3);
}

.context-a .context-role {
  background: var(--ark-blue-600);
}

.context-content {
  color: var(--fg-2);
  flex: 1;
  word-break: break-word;
}

.context-a .context-content {
  color: var(--fg-1);
}

/* Pagination */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-3);
}

.page-btn {
  padding: var(--sp-2) var(--sp-4);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  color: var(--fg-1);
  font: inherit;
  font-size: var(--fs-13);
  cursor: pointer;
}

.page-btn:disabled {
  opacity: .4;
  cursor: default;
}

.page-btn:not(:disabled):hover {
  background: var(--bg-hover);
}

.page-info {
  font-size: var(--fs-13);
  color: var(--fg-2);
}
</style>
