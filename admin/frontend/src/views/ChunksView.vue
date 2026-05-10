<script setup>
import { ref, reactive, computed, onMounted, inject } from 'vue'
import { api } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import DataTable from '@/components/DataTable.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'

const toast = inject('toast')

const chunks = ref([])
const loading = ref(false)
const pagination = ref({ page: 1, per_page: 50, total: 0 })

const filters = reactive({
  search: '',
  chunk_type: '',
  product_id: ''
})

const confirmDelete = ref({
  show: false,
  chunk: null
})

const chunkModal = ref({
  show: false,
  chunk: null
})

const columns = [
  { key: 'id', title: 'ID', width: '80px', align: 'center' },
  { key: 'chunk_type', title: 'Тип', width: '120px' },
  { key: 'chunk_text_preview', title: 'Превью текста' },
  { key: 'product_name', title: 'Товар', width: '180px' },
  { key: 'token_count', title: 'Токены', width: '100px', align: 'right' },
  { key: 'index_version', title: 'Версия', width: '80px', align: 'center' },
  { key: 'actions', title: '', width: '120px', align: 'center' },
]

async function loadChunks() {
  try {
    loading.value = true
    const params = {
      page: pagination.value.page,
      per_page: pagination.value.per_page,
      ...filters
    }

    if (!params.search) delete params.search
    if (!params.chunk_type) delete params.chunk_type
    if (!params.product_id) delete params.product_id

    const response = await api.getChunks(params)
    chunks.value = response.data.items
    pagination.value = {
      page: response.data.page || 1,
      per_page: response.data.per_page || 50,
      total: response.data.total || 0
    }
  } catch (error) {
    console.error('Failed to load chunks:', error)
    toast('Ошибка загрузки чанков', 'error')
  } finally {
    loading.value = false
  }
}

function handlePageChange(page) {
  pagination.value.page = page
  loadChunks()
}

function handleSearch() {
  pagination.value.page = 1
  loadChunks()
}

async function handleViewClick(chunk, event) {
  event.stopPropagation()
  try {
    const response = await api.getChunk(chunk.id)
    chunkModal.value = { show: true, chunk: response.data }
  } catch (error) {
    console.error('Failed to load chunk:', error)
    toast('Ошибка загрузки чанка', 'error')
  }
}

function handleDeleteClick(chunk, event) {
  event.stopPropagation()
  confirmDelete.value = { show: true, chunk }
}

async function confirmDeleteChunk() {
  try {
    await api.deleteChunk(confirmDelete.value.chunk.id)
    toast('Чанк удален', 'success')
    confirmDelete.value = { show: false, chunk: null }
    loadChunks()
  } catch (error) {
    console.error('Failed to delete chunk:', error)
    toast('Ошибка удаления чанка', 'error')
  }
}

function cancelDelete() {
  confirmDelete.value = { show: false, chunk: null }
}

function closeChunkModal() {
  chunkModal.value = { show: false, chunk: null }
}

const getChunkTypeBadge = (chunkType) => {
  switch (chunkType) {
    case 'product': return { type: 'info', text: 'Товар' }
    case 'manual': return { type: 'success', text: 'Инструкция' }
    case 'spec': return { type: 'warning', text: 'Характеристики' }
    default: return { type: 'default', text: chunkType || '—' }
  }
}

const formatTokens = (count) => {
  return count ? count.toLocaleString('ru-RU') : '—'
}

const formatPreview = (text) => {
  return text ? text.slice(0, 100) + (text.length > 100 ? '...' : '') : '—'
}

onMounted(() => {
  loadChunks()
})
</script>

<template>
  <div>
    <PageHeader title="RAG Чанки">
      <template #actions>
        <div class="filters">
          <input
            v-model="filters.search"
            placeholder="Поиск по тексту..."
            class="search-input"
            @input="handleSearch"
          />
          <select
            v-model="filters.chunk_type"
            class="type-select"
            @change="handleSearch"
          >
            <option value="">Все типы</option>
            <option value="product">Товар</option>
            <option value="manual">Инструкция</option>
            <option value="spec">Характеристики</option>
          </select>
          <input
            v-model="filters.product_id"
            type="number"
            placeholder="ID товара"
            class="product-input"
            @input="handleSearch"
          />
        </div>
      </template>
    </PageHeader>

    <div class="content">
      <DataTable
        :columns="columns"
        :data="chunks"
        :loading="loading"
        :pagination="pagination"
        @page-change="handlePageChange"
      >
        <template #cell-chunk_type="{ value }">
          <StatusBadge
            :status="getChunkTypeBadge(value).text"
            :type="getChunkTypeBadge(value).type"
          />
        </template>

        <template #cell-chunk_text_preview="{ value }">
          <span class="preview-text">{{ formatPreview(value) }}</span>
        </template>

        <template #cell-token_count="{ value }">
          <span class="token-count">{{ formatTokens(value) }}</span>
        </template>

        <template #cell-index_version="{ value }">
          <span class="version-badge">v{{ value }}</span>
        </template>

        <template #cell-actions="{ item }">
          <div class="action-buttons">
            <button
              class="action-btn view-btn"
              @click="handleViewClick(item, $event)"
            >
              👁
            </button>
            <button
              class="action-btn delete-btn"
              @click="handleDeleteClick(item, $event)"
            >
              🗑
            </button>
          </div>
        </template>
      </DataTable>
    </div>

    <!-- Chunk detail modal -->
    <div v-if="chunkModal.show" class="modal-backdrop" @click="closeChunkModal">
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">RAG Чанк #{{ chunkModal.chunk.id }}</h3>
          <button class="modal-close" @click="closeChunkModal">×</button>
        </div>
        <div class="modal-body">
          <div class="chunk-details">
            <div class="detail-row">
              <span class="detail-label">Тип:</span>
              <StatusBadge
                :status="getChunkTypeBadge(chunkModal.chunk.chunk_type).text"
                :type="getChunkTypeBadge(chunkModal.chunk.chunk_type).type"
              />
            </div>
            <div v-if="chunkModal.chunk.product_name" class="detail-row">
              <span class="detail-label">Товар:</span>
              <span class="detail-value">{{ chunkModal.chunk.product_name }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Токенов:</span>
              <span class="detail-value">{{ formatTokens(chunkModal.chunk.token_count) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Версия индекса:</span>
              <span class="detail-value">v{{ chunkModal.chunk.index_version }}</span>
            </div>
          </div>

          <div class="chunk-text-section">
            <h4 class="text-section-title">Оригинальный текст</h4>
            <pre class="chunk-text">{{ chunkModal.chunk.chunk_text }}</pre>
          </div>

          <div v-if="chunkModal.chunk.contextualized_text" class="chunk-text-section">
            <h4 class="text-section-title">Контекстуализированный текст</h4>
            <pre class="chunk-text">{{ chunkModal.chunk.contextualized_text }}</pre>
          </div>
        </div>
      </div>
    </div>

    <ConfirmDialog
      :show="confirmDelete.show"
      title="Удалить чанк"
      :message="`Вы уверены, что хотите удалить чанк #${confirmDelete.chunk?.id}?`"
      confirm-text="Удалить"
      danger
      @confirm="confirmDeleteChunk"
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
  width: 200px;
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
  width: 160px;
  cursor: pointer;
}

.type-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--shadow-focus);
}

.product-input {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  font: inherit;
  font-size: var(--fs-14);
  color: var(--fg-1);
  width: 120px;
  transition: border-color var(--dur-fast) var(--ease-out);
}

.product-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--shadow-focus);
}

.product-input::placeholder {
  color: var(--fg-3);
}

.preview-text {
  font-size: var(--fs-13);
  line-height: var(--lh-normal);
  color: var(--fg-1);
}

.token-count {
  font-family: var(--font-mono);
  font-weight: var(--fw-medium);
  color: var(--fg-1);
}

.version-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 6px;
  font-size: var(--fs-11);
  font-weight: var(--fw-medium);
  font-family: var(--font-mono);
  background: var(--bg-panel);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-sm);
  color: var(--fg-2);
}

.action-buttons {
  display: flex;
  gap: var(--sp-1);
  justify-content: center;
}

.action-btn {
  padding: var(--sp-1);
  border: none;
  background: none;
  cursor: pointer;
  font-size: 14px;
  opacity: 0.6;
  transition: opacity var(--dur-fast) var(--ease-out);
}

.action-btn:hover {
  opacity: 1;
}

/* Modal styles */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--sp-4);
}

.modal {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-xl);
  box-shadow: var(--shadow-3);
  width: 100%;
  max-width: 800px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  padding: var(--sp-5);
  border-bottom: 1px solid var(--border-2);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: none;
}

.modal-title {
  font-size: var(--fs-18);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0;
}

.modal-close {
  width: 32px;
  height: 32px;
  border: none;
  background: none;
  font-size: 20px;
  color: var(--fg-3);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--rad-sm);
  transition: all var(--dur-fast) var(--ease-out);
}

.modal-close:hover {
  background: var(--bg-hover);
  color: var(--fg-1);
}

.modal-body {
  padding: var(--sp-5);
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.chunk-details {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  margin-bottom: var(--sp-5);
  padding: var(--sp-4);
  background: var(--bg-panel-2);
  border-radius: var(--rad-lg);
  border: 1px solid var(--border-2);
}

.detail-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.detail-label {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  color: var(--fg-2);
  min-width: 120px;
}

.detail-value {
  font-size: var(--fs-14);
  color: var(--fg-1);
}

.chunk-text-section {
  margin-bottom: var(--sp-5);
}

.chunk-text-section:last-child {
  margin-bottom: 0;
}

.text-section-title {
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0 0 var(--sp-3) 0;
}

.chunk-text {
  font-family: var(--font-mono);
  font-size: var(--fs-13);
  line-height: var(--lh-normal);
  color: var(--fg-1);
  background: var(--bg-panel-2);
  border: 1px solid var(--border-2);
  border-radius: var(--rad-lg);
  padding: var(--sp-4);
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: break-word;
}
</style>