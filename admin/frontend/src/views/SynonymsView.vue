<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { api } from '@/api/index.js'
import AjaxFrog from '@/components/AjaxFrog.vue'

const toast = inject('toast')

const synonyms = ref([])
const total = ref(0)
const loading = ref(false)

const filterCategory = ref('')
const filterActive = ref('')
const searchInput = ref('')
const search = ref('')

const editing = ref(null)  // null = closed; {} = new; {id, ...} = edit existing
const saving = ref(false)

const CATEGORIES = [
  { value: 'model',         label: 'Модель',           color: 'cat-model' },
  { value: 'component',     label: 'Компонент',        color: 'cat-component' },
  { value: 'discontinued',  label: 'Снято',            color: 'cat-discontinued' },
  { value: 'general',       label: 'Общее',            color: 'cat-general' },
]

const categoryLabel = (c) => CATEGORIES.find(x => x.value === c)?.label || c
const categoryClass = (c) => CATEGORIES.find(x => x.value === c)?.color || ''

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filterCategory.value) params.category = filterCategory.value
    if (filterActive.value === 'true') params.active = true
    if (filterActive.value === 'false') params.active = false
    if (search.value) params.search = search.value
    const res = await api.getSynonyms(params)
    synonyms.value = res.data.items
    total.value = res.data.total
  } catch {
    toast('Ошибка загрузки словаря', 'error')
  } finally {
    loading.value = false
  }
}

function applySearch() {
  search.value = searchInput.value.trim()
  load()
}

function openNew() {
  editing.value = {
    id: null,
    term: '',
    canonical: '',
    category: 'model',
    note: '',
    active: true,
  }
}

function openEdit(s) {
  editing.value = { ...s }
}

function closeEditor() {
  editing.value = null
}

async function save() {
  if (saving.value) return
  const e = editing.value
  if (!e.term?.trim() || !e.canonical?.trim()) {
    toast('Заполни «Что говорят» и «Канонически»', 'error')
    return
  }
  saving.value = true
  try {
    const payload = {
      term: e.term.trim(),
      canonical: e.canonical.trim(),
      category: e.category,
      note: e.note?.trim() || null,
      active: e.active,
    }
    if (e.id) {
      await api.updateSynonym(e.id, payload)
      toast('Сохранено', 'success')
    } else {
      await api.createSynonym(payload)
      toast('Создано', 'success')
    }
    closeEditor()
    await load()
  } catch {
    toast('Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
}

async function remove(s) {
  if (!confirm(`Удалить «${s.term}» → «${s.canonical}»?`)) return
  try {
    await api.deleteSynonym(s.id)
    toast('Удалено', 'success')
    await load()
  } catch {
    toast('Ошибка удаления', 'error')
  }
}

async function reload() {
  try {
    await api.reloadSynonyms()
    toast('Бот перечитал словарь', 'success')
  } catch {
    toast('Ошибка перезагрузки', 'error')
  }
}

onMounted(load)
</script>

<template>
  <div class="synonyms-view">
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">Словарь синонимов</h1>
        <span class="page-count">{{ total }} записей</span>
      </div>
      <div class="actions">
        <button class="btn btn-secondary" @click="reload" title="Заставить бот перечитать словарь сейчас">
          ↻ Reload бота
        </button>
        <button class="btn btn-primary" @click="openNew">+ Новый синоним</button>
      </div>
    </div>

    <div class="filters">
      <div class="search-wrap">
        <input
          v-model="searchInput"
          class="search-input"
          placeholder="Поиск по term / canonical…"
          @keydown.enter="applySearch"
        />
        <button class="search-btn" @click="applySearch">Найти</button>
      </div>
      <select v-model="filterCategory" class="filter-select" @change="load">
        <option value="">Все категории</option>
        <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
      </select>
      <select v-model="filterActive" class="filter-select" @change="load">
        <option value="">Все</option>
        <option value="true">Активные</option>
        <option value="false">Отключённые</option>
      </select>
    </div>

    <div class="hint">
      Синонимы применяются к запросам пользователей <b>до</b> RAG-поиска.
      <br>
      Пример: пользователь пишет «<i>трус двенадцать</i>» → бот ищет «<i>Русь-12</i>».
    </div>

    <div class="table-wrap">
      <div v-if="loading" class="loading-state"><AjaxFrog /></div>
      <table v-else class="log-table">
        <colgroup>
          <col style="width: 110px" />
          <col style="width: auto" />
          <col style="width: auto" />
          <col style="width: 80px" />
          <col style="width: auto" />
          <col style="width: 90px" />
        </colgroup>
        <thead>
          <tr>
            <th>Категория</th>
            <th>Что говорят</th>
            <th>Канонически (→)</th>
            <th>Статус</th>
            <th>Заметка</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in synonyms" :key="s.id" class="log-row" @click="openEdit(s)">
            <td>
              <span :class="['cat-pill', categoryClass(s.category)]">
                {{ categoryLabel(s.category) }}
              </span>
            </td>
            <td class="term-cell">{{ s.term }}</td>
            <td class="canonical-cell"><span class="arrow">→</span> {{ s.canonical }}</td>
            <td>
              <span :class="['status-pill', s.active ? 'st-on' : 'st-off']">
                {{ s.active ? 'on' : 'off' }}
              </span>
            </td>
            <td class="note-cell">{{ s.note || '—' }}</td>
            <td class="cell-actions">
              <button class="row-btn danger" @click.stop="remove(s)" title="Удалить">✕</button>
            </td>
          </tr>
          <tr v-if="!loading && synonyms.length === 0">
            <td colspan="6" class="empty-state">Записей нет</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Editor modal -->
    <Teleport to="body">
      <div v-if="editing" class="overlay" @click.self="closeEditor">
        <div class="modal">
          <div class="modal-header">
            <h3>{{ editing.id ? 'Редактировать синоним' : 'Новый синоним' }}</h3>
            <button class="close-btn" @click="closeEditor">✕</button>
          </div>
          <div class="modal-body">
            <div class="field">
              <label>Что говорят / пишут (term)</label>
              <input v-model="editing.term" placeholder="напр. трус двенадцать" />
            </div>
            <div class="field">
              <label>Канонически (canonical) — что хочет увидеть бот</label>
              <input v-model="editing.canonical" placeholder="напр. Русь-12" />
            </div>
            <div class="field">
              <label>Категория</label>
              <select v-model="editing.category">
                <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
              </select>
            </div>
            <div class="field">
              <label>Заметка (опционально)</label>
              <input v-model="editing.note" placeholder="напр. сленг / опечатка / искажение голосового набора" />
            </div>
            <div class="field-inline">
              <label>
                <input type="checkbox" v-model="editing.active" />
                Активный (применяется к запросам)
              </label>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closeEditor">Отмена</button>
            <button class="btn btn-primary" :disabled="saving" @click="save">
              {{ saving ? 'Сохраняю…' : 'Сохранить' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.synonyms-view {
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--sp-3);
}

.page-title-block {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
}

.page-title {
  margin: 0;
  font-size: var(--fs-24);
  font-weight: var(--fw-bold);
}

.page-count {
  font-size: var(--fs-13);
  color: var(--fg-3);
  background: var(--bg-panel-2);
  padding: 2px 8px;
  border-radius: var(--rad-md);
}

.actions {
  display: flex;
  gap: var(--sp-2);
}

.filters {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
  align-items: center;
}

.search-wrap {
  display: flex;
  gap: 4px;
}

.search-input {
  width: 280px;
  padding: 6px 10px;
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-input);
  color: var(--fg-1);
  font-size: var(--fs-13);
}

.search-btn,
.filter-select {
  padding: 6px 10px;
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-panel);
  color: var(--fg-1);
  font-size: var(--fs-13);
  cursor: pointer;
}

.hint {
  background: color-mix(in srgb, var(--ark-blue-600) 6%, transparent);
  border-left: 3px solid var(--ark-blue-600);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--rad-sm);
  font-size: var(--fs-12);
  color: var(--fg-2);
}

.table-wrap {
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  overflow: hidden;
}

.cat-pill {
  display: inline-block;
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  padding: 2px 8px;
  border-radius: var(--rad-sm);
  white-space: nowrap;
}

.cat-model        { background: color-mix(in srgb, var(--ark-blue-600)   15%, transparent); color: var(--ark-blue-600); }
.cat-component    { background: color-mix(in srgb, var(--ark-green-600)  15%, transparent); color: var(--ark-green-600); }
.cat-discontinued { background: color-mix(in srgb, var(--ark-red-600)    15%, transparent); color: var(--ark-red-600); }
.cat-general      { background: var(--bg-panel-2); color: var(--fg-3); }

.term-cell        { font-weight: var(--fw-medium); color: var(--fg-1); }
.canonical-cell   { color: var(--fg-2); }
.arrow            { color: var(--fg-4); margin-right: 6px; }
.note-cell        { color: var(--fg-3); font-size: var(--fs-12); }

.status-pill {
  display: inline-block;
  font-size: var(--fs-11);
  padding: 1px 7px;
  border-radius: 99px;
  font-weight: var(--fw-semibold);
}
.st-on  { background: color-mix(in srgb, var(--ark-green-600) 18%, transparent); color: var(--ark-green-600); }
.st-off { background: var(--bg-panel-2); color: var(--fg-3); }

.cell-actions   { text-align: right; }
.row-btn        { background: transparent; border: 1px solid var(--border-1); border-radius: var(--rad-sm); padding: 2px 7px; font-size: 12px; cursor: pointer; color: var(--fg-3); }
.row-btn.danger:hover { color: var(--ark-red-600); border-color: var(--ark-red-600); }

.empty-state {
  text-align: center;
  padding: var(--sp-6);
  color: var(--fg-3);
}

.loading-state {
  padding: var(--sp-6);
  text-align: center;
}

/* Modal */
.overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}

.modal {
  width: 520px;
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  display: flex; flex-direction: column;
  max-height: 90vh;
}

.modal-header {
  padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid var(--border-1);
  display: flex; align-items: center; justify-content: space-between;
}
.modal-header h3 { margin: 0; font-size: var(--fs-16); }
.close-btn {
  background: transparent; border: 0; cursor: pointer;
  font-size: 18px; color: var(--fg-3); padding: 0 6px;
}

.modal-body {
  padding: var(--sp-4);
  display: flex; flex-direction: column; gap: var(--sp-3);
  overflow-y: auto;
}

.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: var(--fs-12); color: var(--fg-3); font-weight: var(--fw-semibold); }
.field input, .field select {
  padding: 8px 10px;
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-input);
  color: var(--fg-1);
  font: inherit;
  font-size: var(--fs-14);
}
.field-inline label { display: flex; gap: var(--sp-2); align-items: center; font-size: var(--fs-14); }

.modal-footer {
  padding: var(--sp-3) var(--sp-4);
  border-top: 1px solid var(--border-1);
  display: flex; justify-content: flex-end; gap: var(--sp-2);
}

.btn {
  padding: 8px 14px;
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-panel);
  color: var(--fg-1);
  font: inherit;
  font-size: var(--fs-13);
  cursor: pointer;
}
.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-secondary { background: var(--bg-panel-2); }
</style>
