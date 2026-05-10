<script setup>
import { ref, onMounted, inject } from 'vue'
import { api } from '@/api/index.js'

const toast = inject('toast')
const entries = ref([])
const total = ref(0)
const loading = ref(false)

const modal = ref({ show: false, mode: 'create', entry: null })
const form = ref({ question: '', answer: '', active: true })
const saving = ref(false)
const deleting = ref(null)

async function load() {
  loading.value = true
  try {
    const res = await api.getFaqEntries()
    entries.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = { question: '', answer: '', active: true }
  modal.value = { show: true, mode: 'create', entry: null }
}

function openEdit(entry) {
  form.value = { question: entry.question, answer: entry.answer, active: entry.active }
  modal.value = { show: true, mode: 'edit', entry }
}

async function save() {
  if (!form.value.question.trim() || !form.value.answer.trim()) {
    toast('Заполните вопрос и ответ', 'error')
    return
  }
  saving.value = true
  try {
    if (modal.value.mode === 'create') {
      await api.createFaqEntry({ question: form.value.question.trim(), answer: form.value.answer.trim() })
      toast('FAQ добавлен', 'success')
    } else {
      await api.updateFaqEntry(modal.value.entry.id, {
        question: form.value.question.trim(),
        answer: form.value.answer.trim(),
        active: form.value.active,
      })
      toast('FAQ обновлён', 'success')
    }
    modal.value.show = false
    await load()
  } catch {
    toast('Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
}

async function toggleActive(entry) {
  try {
    await api.updateFaqEntry(entry.id, { active: !entry.active })
    entry.active = !entry.active
  } catch {
    toast('Ошибка', 'error')
  }
}

async function remove(entry) {
  if (deleting.value === entry.id) {
    try {
      await api.deleteFaqEntry(entry.id)
      toast('Удалено', 'success')
      await load()
    } catch {
      toast('Ошибка удаления', 'error')
    } finally {
      deleting.value = null
    }
  } else {
    deleting.value = entry.id
    setTimeout(() => { if (deleting.value === entry.id) deleting.value = null }, 3000)
  }
}

function formatDate(ts) {
  return new Date(ts).toLocaleDateString('ru', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

onMounted(load)
</script>

<template>
  <div class="faq-view">
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">FAQ</h1>
        <span class="page-count">{{ total }} записей</span>
      </div>
      <button class="btn-primary" @click="openCreate">+ Добавить</button>
    </div>

    <div class="table-wrap">
      <div v-if="loading" class="loading-state">Загрузка...</div>
      <table v-else class="faq-table">
        <colgroup>
          <col style="width: 44px" />
          <col style="width: 300px" />
          <col style="width: auto" />
          <col style="width: 80px" />
          <col style="width: 110px" />
        </colgroup>
        <thead>
          <tr>
            <th></th>
            <th>Вопрос</th>
            <th>Ответ</th>
            <th>Дата</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in entries" :key="entry.id" :class="{ inactive: !entry.active }">
            <td class="cell-toggle">
              <button
                :class="['toggle-btn', entry.active ? 'toggle-on' : 'toggle-off']"
                :title="entry.active ? 'Отключить' : 'Включить'"
                @click="toggleActive(entry)"
              >{{ entry.active ? '●' : '○' }}</button>
            </td>
            <td class="cell-q" @click="openEdit(entry)">{{ entry.question }}</td>
            <td class="cell-a" @click="openEdit(entry)">{{ entry.answer }}</td>
            <td class="cell-date">{{ formatDate(entry.created_at) }}</td>
            <td class="cell-actions">
              <button class="action-btn edit-btn" @click="openEdit(entry)">✎</button>
              <button
                :class="['action-btn', 'del-btn', { 'del-confirm': deleting === entry.id }]"
                :title="deleting === entry.id ? 'Нажмите ещё раз' : 'Удалить'"
                @click="remove(entry)"
              >{{ deleting === entry.id ? '✓?' : '✕' }}</button>
            </td>
          </tr>
          <tr v-if="entries.length === 0">
            <td colspan="5" class="empty-state">Нет записей. Добавьте первый FAQ или перенесите из Журнала.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal -->
    <Teleport to="body">
      <div v-if="modal.show" class="modal-overlay" @click.self="modal.show = false">
        <div class="modal">
          <div class="modal-header">
            <div class="modal-title">{{ modal.mode === 'create' ? 'Новый FAQ' : 'Редактировать FAQ' }}</div>
            <button class="modal-close" @click="modal.show = false">✕</button>
          </div>
          <div class="modal-body">
            <label class="field-label">Вопрос</label>
            <textarea v-model="form.question" class="field-input" rows="3" placeholder="Как оформить заказ?" />
            <label class="field-label">Ответ</label>
            <textarea v-model="form.answer" class="field-input" rows="6" placeholder="Ответ бота..." />
            <label v-if="modal.mode === 'edit'" class="field-row">
              <input type="checkbox" v-model="form.active" />
              <span>Активен</span>
            </label>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" @click="modal.show = false">Отмена</button>
            <button class="btn-primary" :disabled="saving" @click="save">
              {{ saving ? 'Сохраняю...' : 'Сохранить' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.faq-view {
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
}

.page-count {
  font-size: var(--fs-13);
  color: var(--fg-3);
}

.btn-primary {
  padding: var(--sp-2) var(--sp-4);
  background: var(--accent);
  color: #fff;
  border: 0;
  border-radius: var(--rad-md);
  font: inherit;
  font-size: var(--fs-13);
  font-weight: var(--fw-semibold);
  cursor: pointer;
}

.btn-primary:hover { opacity: .88; }
.btn-primary:disabled { opacity: .5; cursor: default; }

.btn-secondary {
  padding: var(--sp-2) var(--sp-4);
  background: var(--bg-elevated);
  color: var(--fg-1);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  font: inherit;
  font-size: var(--fs-13);
  cursor: pointer;
}

.btn-secondary:hover { background: var(--bg-hover); }

.table-wrap {
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  overflow: hidden;
}

.loading-state, .empty-state {
  padding: var(--sp-8);
  text-align: center;
  color: var(--fg-3);
  font-size: var(--fs-13);
}

.faq-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: var(--fs-13);
}

.faq-table th {
  padding: var(--sp-2) var(--sp-3);
  background: var(--bg-panel-2);
  border-bottom: 1px solid var(--border-1);
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  color: var(--fg-3);
  text-align: left;
}

.faq-table td {
  padding: var(--sp-3);
  border-bottom: 1px solid var(--border-2);
  vertical-align: top;
}

.faq-table tr.inactive td {
  opacity: .45;
}

.cell-q {
  font-weight: var(--fw-medium);
  cursor: pointer;
  color: var(--fg-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-a {
  color: var(--fg-2);
  cursor: pointer;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  white-space: normal;
}

.cell-q:hover, .cell-a:hover { color: var(--accent); }

.cell-date {
  font-size: var(--fs-12);
  color: var(--fg-3);
  white-space: nowrap;
}

.cell-actions {
  display: flex;
  gap: var(--sp-1);
  align-items: center;
}

.cell-toggle { text-align: center; }

.toggle-btn {
  border: 0;
  background: transparent;
  font-size: 16px;
  cursor: pointer;
  padding: 2px 4px;
}

.toggle-on  { color: var(--ark-green-600); }
.toggle-off { color: var(--fg-4); }

.action-btn {
  border: 0;
  background: transparent;
  padding: 4px 6px;
  border-radius: var(--rad-sm);
  cursor: pointer;
  font-size: 14px;
  color: var(--fg-3);
}

.action-btn:hover { background: var(--bg-hover); color: var(--fg-1); }

.del-btn:hover { color: var(--ark-red-600); }
.del-confirm  { color: var(--ark-red-600) !important; background: var(--ark-red-100) !important; }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.45);
  z-index: 300;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal {
  width: 580px;
  max-width: 95vw;
  background: var(--bg-panel);
  border-radius: var(--rad-lg);
  border: 1px solid var(--border-1);
  box-shadow: var(--shadow-2);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4);
  border-bottom: 1px solid var(--border-1);
}

.modal-title {
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
}

.modal-close {
  border: 0;
  background: transparent;
  color: var(--fg-3);
  font-size: 16px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--rad-sm);
}

.modal-close:hover { background: var(--bg-hover); color: var(--fg-1); }

.modal-body {
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.field-label {
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  color: var(--fg-3);
  text-transform: uppercase;
  letter-spacing: .05em;
  margin-bottom: -var(--sp-2);
}

.field-input {
  width: 100%;
  padding: var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  color: var(--fg-1);
  font: inherit;
  font-size: var(--fs-13);
  line-height: var(--lh-relaxed);
  resize: vertical;
}

.field-input:focus {
  outline: none;
  border-color: var(--accent);
}

.field-row {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-13);
  cursor: pointer;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: var(--sp-4);
  border-top: 1px solid var(--border-1);
}
</style>
