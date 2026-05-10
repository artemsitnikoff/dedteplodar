<script setup>
import { ref, reactive, computed, onMounted, inject } from 'vue'
import { api } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import DataTable from '@/components/DataTable.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'

const toast = inject('toast')

const documents = ref([])
const loading = ref(false)
const pagination = ref({ page: 1, per_page: 50, total: 0 })

const filters = reactive({
  search: '',
  doc_type: ''
})

const confirmDelete = ref({
  show: false,
  document: null
})

const uploadDialog = ref({
  show: false,
  file: null,
  productId: ''
})

const columns = [
  { key: 'id', title: 'ID', width: '80px', align: 'center' },
  { key: 'doc_type', title: 'Тип', width: '100px' },
  { key: 'title', title: 'Название' },
  { key: 'product_name', title: 'Товар', width: '200px' },
  { key: 'char_count', title: 'Размер', width: '120px', align: 'right' },
  { key: 'fetched_at', title: 'Загружено', width: '140px' },
  { key: 'actions', title: '', width: '80px', align: 'center' },
]

async function loadDocuments() {
  try {
    loading.value = true
    const params = {
      page: pagination.value.page,
      per_page: pagination.value.per_page,
      ...filters
    }

    if (!params.search) delete params.search
    if (!params.doc_type) delete params.doc_type

    const response = await api.getDocuments(params)
    documents.value = response.data.items
    pagination.value = {
      page: response.data.page || 1,
      per_page: response.data.per_page || 50,
      total: response.data.total || 0
    }
  } catch (error) {
    console.error('Failed to load documents:', error)
    toast('Ошибка загрузки документов', 'error')
  } finally {
    loading.value = false
  }
}

function handlePageChange(page) {
  pagination.value.page = page
  loadDocuments()
}

function handleSearch() {
  pagination.value.page = 1
  loadDocuments()
}

function handleDeleteClick(document, event) {
  event.stopPropagation()
  confirmDelete.value = { show: true, document }
}

async function confirmDeleteDocument() {
  try {
    await api.deleteDocument(confirmDelete.value.document.id)
    toast('Документ удален', 'success')
    confirmDelete.value = { show: false, document: null }
    loadDocuments()
  } catch (error) {
    console.error('Failed to delete document:', error)
    toast('Ошибка удаления документа', 'error')
  }
}

function cancelDelete() {
  confirmDelete.value = { show: false, document: null }
}

function showUploadDialog() {
  uploadDialog.value = { show: true, file: null, productId: '' }
}

function hideUploadDialog() {
  uploadDialog.value = { show: false, file: null, productId: '' }
}

function handleFileSelect(event) {
  const file = event.target.files[0]
  if (file) {
    uploadDialog.value.file = file
  }
}

async function uploadDocument() {
  if (!uploadDialog.value.file) {
    toast('Выберите файл для загрузки', 'error')
    return
  }

  try {
    const productId = uploadDialog.value.productId || null
    await api.uploadDocument(uploadDialog.value.file, productId)
    toast('Документ загружен', 'success')
    hideUploadDialog()
    loadDocuments()
  } catch (error) {
    console.error('Failed to upload document:', error)
    toast('Ошибка загрузки документа', 'error')
  }
}

const formatFileSize = (charCount) => {
  if (!charCount) return '—'
  const kb = Math.round(charCount / 1000)
  return `${kb.toLocaleString('ru-RU')} тыс. симв.`
}

const formatDate = (dateStr) => {
  return dateStr ? new Date(dateStr).toLocaleDateString('ru-RU') : '—'
}

const getDocTypeBadge = (docType) => {
  switch (docType) {
    case 'pdf': return { type: 'danger', text: 'PDF' }
    case 'html': return { type: 'info', text: 'HTML' }
    default: return { type: 'default', text: docType || '—' }
  }
}

onMounted(() => {
  loadDocuments()
})
</script>

<template>
  <div>
    <PageHeader title="Документы">
      <template #actions>
        <div class="filters">
          <input
            v-model="filters.search"
            placeholder="Поиск по названию..."
            class="search-input"
            @input="handleSearch"
          />
          <select
            v-model="filters.doc_type"
            class="type-select"
            @change="handleSearch"
          >
            <option value="">Все типы</option>
            <option value="pdf">PDF</option>
            <option value="html">HTML</option>
          </select>
          <button class="btn btn-primary" @click="showUploadDialog">
            Загрузить PDF
          </button>
        </div>
      </template>
    </PageHeader>

    <div class="content">
      <DataTable
        :columns="columns"
        :data="documents"
        :loading="loading"
        :pagination="pagination"
        @page-change="handlePageChange"
      >
        <template #cell-doc_type="{ value }">
          <StatusBadge
            :status="getDocTypeBadge(value).text"
            :type="getDocTypeBadge(value).type"
          />
        </template>

        <template #cell-title="{ item }">
          <div class="title-cell">
            <span class="title">{{ item.title || 'Без названия' }}</span>
            <a
              v-if="item.source_url"
              :href="item.source_url"
              target="_blank"
              class="source-link"
              @click.stop
            >
              🔗
            </a>
          </div>
        </template>

        <template #cell-char_count="{ value }">
          {{ formatFileSize(value) }}
        </template>

        <template #cell-fetched_at="{ value }">
          {{ formatDate(value) }}
        </template>

        <template #cell-actions="{ item }">
          <button
            class="delete-btn"
            @click="handleDeleteClick(item, $event)"
          >
            🗑
          </button>
        </template>
      </DataTable>
    </div>

    <!-- Upload dialog -->
    <div v-if="uploadDialog.show" class="dialog-backdrop" @click="hideUploadDialog">
      <div class="dialog" @click.stop>
        <div class="dialog-header">
          <h3 class="dialog-title">Загрузить документ</h3>
        </div>
        <div class="dialog-body">
          <div class="form-field">
            <label class="form-label">Файл (PDF)</label>
            <input
              type="file"
              accept=".pdf"
              class="file-input"
              @change="handleFileSelect"
            />
          </div>
          <div class="form-field">
            <label class="form-label">ID товара (необязательно)</label>
            <input
              v-model="uploadDialog.productId"
              type="number"
              class="form-input"
              placeholder="Оставьте пустым для общего документа"
            />
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn btn-outline" @click="hideUploadDialog">
            Отмена
          </button>
          <button
            class="btn btn-primary"
            :disabled="!uploadDialog.file"
            @click="uploadDocument"
          >
            Загрузить
          </button>
        </div>
      </div>
    </div>

    <ConfirmDialog
      :show="confirmDelete.show"
      title="Удалить документ"
      :message="`Вы уверены, что хотите удалить документ «${confirmDelete.document?.title}»?`"
      confirm-text="Удалить"
      danger
      @confirm="confirmDeleteDocument"
      @cancel="cancelDelete"
    />
  </div>
</template>

<style scoped>
.content {
  padding: var(--sp-6);
}

.filters {
  display: flex;
  gap: var(--sp-3);
  align-items: center;
}

.search-input {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  font: inherit;
  font-size: var(--fs-14);
  color: var(--fg-1);
  width: 240px;
  transition: border-color var(--dur-fast) var(--ease-out);
}

.search-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--shadow-focus);
}

.search-input::placeholder {
  color: var(--fg-3);
}

.type-select {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  font: inherit;
  font-size: var(--fs-14);
  color: var(--fg-1);
  width: 140px;
  cursor: pointer;
}

.type-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--shadow-focus);
}

.title-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}

.title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-link {
  font-size: 14px;
  text-decoration: none;
  opacity: 0.7;
  transition: opacity var(--dur-fast) var(--ease-out);
}

.source-link:hover {
  opacity: 1;
}

.delete-btn {
  padding: var(--sp-1);
  border: none;
  background: none;
  cursor: pointer;
  font-size: 14px;
  opacity: 0.6;
  transition: opacity var(--dur-fast) var(--ease-out);
}

.delete-btn:hover {
  opacity: 1;
}

.btn {
  padding: var(--sp-2) var(--sp-4);
  border-radius: var(--rad-md);
  border: 1px solid;
  font: inherit;
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-outline {
  background: var(--bg-elevated);
  border-color: var(--border-1);
  color: var(--fg-1);
}

.btn-outline:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--fg-on-accent);
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}

/* Upload dialog styles */
.dialog-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-xl);
  box-shadow: var(--shadow-3);
  width: 100%;
  max-width: 500px;
  margin: var(--sp-4);
}

.dialog-header {
  padding: var(--sp-5) var(--sp-5) var(--sp-2);
}

.dialog-title {
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0;
}

.dialog-body {
  padding: 0 var(--sp-5) var(--sp-4);
}

.dialog-footer {
  padding: var(--sp-4) var(--sp-5) var(--sp-5);
  display: flex;
  gap: var(--sp-3);
  justify-content: flex-end;
}

.form-field {
  margin-bottom: var(--sp-4);
}

.form-label {
  display: block;
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  color: var(--fg-1);
  margin-bottom: var(--sp-2);
}

.form-input {
  width: 100%;
  padding: var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  font: inherit;
  font-size: var(--fs-14);
  color: var(--fg-1);
  transition: border-color var(--dur-fast) var(--ease-out);
}

.form-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--shadow-focus);
}

.file-input {
  width: 100%;
  padding: var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  font: inherit;
  font-size: var(--fs-14);
  color: var(--fg-1);
  cursor: pointer;
}

.file-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--shadow-focus);
}
</style>