<script setup>
import { ref, computed, watch, onMounted, inject } from 'vue'
import { api } from '@/api/index.js'

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

const totalPages = computed(() => Math.ceil(total.value / perPage))

const selected = ref(null)
const faqSaving = ref(false)

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

function feedbackLabel(fb) {
  if (fb === 'good') return { label: '👍', cls: 'fb-good' }
  if (fb === 'bad') return { label: '👎', cls: 'fb-bad' }
  if (fb === 'operator') return { label: '🆘', cls: 'fb-op' }
  return null
}

function qtypeLabel(qt) {
  return {
    RAG_PRODUCT: 'RAG',
    FAQ_COMPANY: 'О компании',
    FAQ_DEALER:  'Дилер',
    FAQ_EXACT:   'FAQ',
    ERROR:       'Ошибка',
  }[qt] || qt
}

function qtypeCls(qt) {
  return {
    RAG_PRODUCT: 'qt-rag',
    FAQ_COMPANY: 'qt-ref',
    FAQ_DEALER:  'qt-dealer',
    FAQ_EXACT:   'qt-faq',
    ERROR:       'qt-error',
  }[qt] || ''
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
      </div>
    </div>

    <!-- Table -->
    <div class="table-wrap">
      <div v-if="loading" class="loading-state">Загрузка...</div>
      <table v-else class="log-table">
        <colgroup>
          <col style="width: 96px" />
          <col style="width: 64px" />
          <col style="width: 96px" />
          <col style="width: 260px" />
          <col style="width: auto" />
          <col style="width: 64px" />
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
            @click="selected = selected?.id === log.id ? null : log"
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
            <td colspan="9" class="empty-state">Нет записей</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Detail panel -->
    <Teleport to="body">
      <div v-if="selected" class="detail-overlay" @click.self="selected = null">
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
          <button class="detail-close" @click="selected = null">✕</button>
          </div>

          <div class="detail-body">
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

.qtype-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: var(--rad-sm);
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  letter-spacing: 0.03em;
}

.qt-rag    { background: var(--ark-blue-100);   color: var(--ark-blue-700); }
.qt-faq    { background: var(--ark-green-100);  color: var(--ark-green-600); }
.qt-ref    { background: var(--ark-yellow-100, #fef9c3); color: #854d0e; }
.qt-dealer { background: var(--ark-purple-100); color: var(--ark-purple-700); }
.qt-error  { background: var(--ark-red-100);    color: var(--ark-red-600); }

.score-val {
  font-size: var(--fs-12);
  font-variant-numeric: tabular-nums;
  font-weight: var(--fw-semibold);
}

.score-green  { color: var(--ark-green-600); }
.score-yellow { color: #b45309; }
.score-red    { color: var(--ark-red-600); }
.score-none   { color: var(--fg-4); }

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
