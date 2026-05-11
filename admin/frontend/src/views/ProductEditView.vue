<script setup>
import { ref, computed, onMounted, inject, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import AjaxFrog from '@/components/AjaxFrog.vue'

const route = useRoute()
const router = useRouter()
const toast = inject('toast')

const product = ref({})
const chunks = ref([])
const documents = ref([])
const loading = ref(true)
const saving = ref(false)

const textModal = ref(null)   // { id, title, source_url, text, char_count }
const textLoading = ref(false)

async function openTextModal(doc) {
  textModal.value = { id: doc.id, title: doc.title || doc.source_url, source_url: doc.source_url, text: null, char_count: doc.char_count, text_source: doc.text_source }
  textLoading.value = true
  try {
    const r = await api.getDocumentText(doc.id)
    textModal.value.text = r.data.text
    textModal.value.has_text = r.data.has_text
  } catch {
    textModal.value.text = ''
  } finally {
    textLoading.value = false
  }
}

function closeTextModal() {
  textModal.value = null
}

const form = ref({
  name: '',
  model: '',
  price: '',
  description: ''
})

async function loadProduct() {
  try {
    loading.value = true
    const response = await api.getProduct(route.params.id)
    product.value = response.data

    // Fill form
    form.value = {
      name: product.value.name || '',
      model: product.value.model || '',
      price: product.value.price || '',
      description: product.value.description || ''
    }

    const [chunksResponse, docsResponse] = await Promise.all([
      api.getChunks({ product_id: route.params.id, per_page: 50 }),
      api.getProductDocuments(route.params.id, { per_page: 100 }),
    ])
    chunks.value = chunksResponse.data.items || []
    documents.value = docsResponse.data.items || []
  } catch (error) {
    console.error('Failed to load product:', error)
    toast('Ошибка загрузки товара', 'error')
    router.push({ name: 'products' })
  } finally {
    loading.value = false
  }
}

async function saveProduct() {
  try {
    saving.value = true
    const data = { ...form.value }

    // Convert price to number
    if (data.price) {
      data.price = parseFloat(data.price)
    }

    await api.updateProduct(route.params.id, data)
    toast('Товар сохранен', 'success')

    // Reload product data
    await loadProduct()
  } catch (error) {
    console.error('Failed to save product:', error)
    toast('Ошибка сохранения товара', 'error')
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.push({ name: 'products' })
}

function formatPrice(price) {
  return price ? `${price.toLocaleString('ru-RU')} ₽` : '—'
}

function formatSize(chars) {
  if (!chars) return '—'
  if (chars >= 1000) return `${(chars / 1000).toFixed(1)}k симв.`
  return `${chars} симв.`
}

function docTypeLabel(t) {
  return t === 'pdf' ? 'PDF' : 'HTML'
}

onMounted(() => {
  loadProduct()
})
</script>

<template>
  <div>
    <PageHeader :title="loading ? 'Загрузка...' : `Товар: ${product.name || 'Без названия'}`">
      <template #actions>
        <button class="btn btn-outline" @click="goBack">
          Назад к списку
        </button>
        <button
          class="btn btn-primary"
          :disabled="saving"
          @click="saveProduct"
        >
          {{ saving ? 'Сохранение...' : 'Сохранить' }}
        </button>
      </template>
    </PageHeader>

    <div class="content">
      <div v-if="loading" class="loading">
        <AjaxFrog text="Загрузка товара…" size="32px" />
      </div>

      <div v-else class="layout">
        <!-- Product form -->
        <div class="form-section">
          <div class="section-card">
            <h3 class="section-title">Основная информация</h3>

            <div class="form-grid">
              <div class="form-field">
                <label class="form-label">Название</label>
                <input
                  v-model="form.name"
                  class="form-input"
                  placeholder="Название товара"
                />
              </div>

              <div class="form-field">
                <label class="form-label">Модель</label>
                <input
                  v-model="form.model"
                  class="form-input"
                  placeholder="Модель товара"
                />
              </div>

              <div class="form-field">
                <label class="form-label">Цена (₽)</label>
                <input
                  v-model="form.price"
                  type="number"
                  class="form-input"
                  placeholder="0"
                  step="0.01"
                />
              </div>

              <div class="form-field full-width">
                <label class="form-label">Описание</label>
                <textarea
                  v-model="form.description"
                  class="form-textarea"
                  rows="4"
                  placeholder="Описание товара..."
                />
              </div>
            </div>
          </div>

          <!-- Parameters -->
          <div v-if="product.params?.length" class="section-card">
            <h3 class="section-title">Параметры</h3>
            <div class="params-table">
              <div
                v-for="param in product.params"
                :key="param.name"
                class="param-row"
              >
                <span class="param-name">{{ param.name }}</span>
                <span class="param-value">{{ param.value }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Product details -->
        <div class="details-section">
          <div class="section-card">
            <h3 class="section-title">Детали товара</h3>
            <div class="details-grid">
              <div class="detail-item">
                <span class="detail-label">ID</span>
                <span class="detail-value">{{ product.id }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Категория</span>
                <span class="detail-value">{{ product.category_name || '—' }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">URL</span>
                <a
                  v-if="product.url"
                  :href="product.url"
                  target="_blank"
                  class="detail-value link"
                >
                  Открыть
                </a>
                <span v-else class="detail-value">—</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Вендор</span>
                <span class="detail-value">{{ product.vendor || '—' }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Документов</span>
                <span class="detail-value">{{ product.documents_count || 0 }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">RAG чанков</span>
                <span class="detail-value">{{ product.chunks_count || 0 }}</span>
              </div>
            </div>

            <div v-if="product.picture_url" class="product-image">
              <img :src="product.picture_url" :alt="product.name" />
            </div>
          </div>

          <!-- Documents -->
          <div class="section-card">
            <h3 class="section-title">Документы ({{ documents.length }})</h3>
            <div v-if="documents.length === 0" class="empty-section">Нет документов</div>
            <table v-else class="doc-table">
              <colgroup>
                <col style="width: 44px">
                <col>
                <col style="width: 80px">
                <col style="width: 76px">
                <col style="width: 52px">
              </colgroup>
              <thead>
                <tr>
                  <th>Тип</th>
                  <th>Название / URL</th>
                  <th>Размер</th>
                  <th>Дата</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="doc in documents" :key="doc.id">
                  <td><span :class="['doc-badge', doc.doc_type]">{{ docTypeLabel(doc.doc_type) }}</span></td>
                  <td class="doc-title-cell">
                    <a :href="doc.source_url" target="_blank" class="doc-link" :title="doc.source_url">
                      {{ doc.title || doc.source_url }}
                    </a>
                  </td>
                  <td class="mono">{{ formatSize(doc.char_count) }}</td>
                  <td class="mono">{{ doc.fetched_at ? new Date(doc.fetched_at).toLocaleDateString('ru-RU') : '—' }}</td>
                  <td>
                    <button
                      v-if="doc.char_count"
                      :class="['text-btn', { 'ocr-btn': doc.text_source === 'ocr' }]"
                      :title="doc.text_source === 'ocr' ? 'Текст получен через OCR' : 'Текст документа'"
                      @click="openTextModal(doc)"
                    >{{ doc.text_source === 'ocr' ? 'OCR' : 'Текст' }}</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Chunks -->
          <div v-if="chunks.length" class="section-card">
            <h3 class="section-title">RAG Чанки ({{ chunks.length }})</h3>
            <div class="chunks-list">
              <div
                v-for="chunk in chunks.slice(0, 10)"
                :key="chunk.id"
                class="chunk-item"
              >
                <div class="chunk-type">{{ chunk.chunk_type }}</div>
                <div class="chunk-preview">{{ chunk.chunk_text_preview }}</div>
                <div class="chunk-tokens">{{ chunk.token_count }} токенов</div>
              </div>
              <div v-if="chunks.length > 10" class="chunk-more">
                ... и еще {{ chunks.length - 10 }} чанков
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- OCR Text Modal -->
  <Teleport to="body">
    <div v-if="textModal" class="modal-backdrop" @click.self="closeTextModal">
      <div class="modal">
        <div class="modal-header">
          <div class="modal-title-block">
            <span class="modal-title">{{ textModal.title }}</span>
            <a :href="textModal.source_url" target="_blank" class="modal-url">↗ открыть оригинал</a>
          </div>
          <button class="modal-close" @click="closeTextModal">✕</button>
        </div>
        <div class="modal-meta" v-if="textModal.char_count">
          {{ formatSize(textModal.char_count) }} ·
          <span v-if="textModal.text_source === 'ocr'" style="color: var(--ark-violet-500); font-weight: 600;">OCR</span>
          <span v-else>текст PDF</span>
        </div>
        <div class="modal-body">
          <div v-if="textLoading" class="modal-loading"><AjaxFrog /></div>
          <div v-else-if="!textModal.has_text" class="modal-empty">Текст документа отсутствует</div>
          <pre v-else class="modal-text">{{ textModal.text }}</pre>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.content {
  padding: var(--sp-6);
}

.loading {
  text-align: center;
  padding: var(--sp-8);
  color: var(--fg-3);
  font-size: var(--fs-14);
}

.layout {
  display: grid;
  grid-template-columns: 1fr 460px;
  gap: var(--sp-6);
  align-items: start;
}

.section-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-5);
  box-shadow: var(--shadow-1);
  margin-bottom: var(--sp-4);
}

.section-title {
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0 0 var(--sp-4) 0;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-4);
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.form-field.full-width {
  grid-column: 1 / -1;
}

.form-label {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  color: var(--fg-1);
}

.form-input {
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

.form-textarea {
  padding: var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  font: inherit;
  font-size: var(--fs-14);
  color: var(--fg-1);
  resize: vertical;
  min-height: 80px;
  transition: border-color var(--dur-fast) var(--ease-out);
}

.form-textarea:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--shadow-focus);
}

.params-table {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.param-row {
  display: flex;
  justify-content: space-between;
  padding: var(--sp-2) 0;
  border-bottom: 1px solid var(--border-2);
}

.param-row:last-child {
  border-bottom: none;
}

.param-name {
  font-size: var(--fs-13);
  color: var(--fg-2);
  font-weight: var(--fw-medium);
}

.param-value {
  font-size: var(--fs-13);
  color: var(--fg-1);
}

.details-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--sp-3);
  margin-bottom: var(--sp-4);
}

.detail-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--sp-2) 0;
  border-bottom: 1px solid var(--border-2);
}

.detail-item:last-child {
  border-bottom: none;
}

.detail-label {
  font-size: var(--fs-13);
  color: var(--fg-2);
  font-weight: var(--fw-medium);
}

.detail-value {
  font-size: var(--fs-13);
  color: var(--fg-1);
  text-align: right;
}

.detail-value.link {
  color: var(--accent);
  text-decoration: none;
}

.detail-value.link:hover {
  text-decoration: underline;
}

.product-image {
  margin-top: var(--sp-4);
  padding-top: var(--sp-4);
  border-top: 1px solid var(--border-2);
}

.product-image img {
  max-width: 100%;
  height: auto;
  border-radius: var(--rad-md);
  box-shadow: var(--shadow-1);
}

.empty-section {
  font-size: var(--fs-13);
  color: var(--fg-3);
  padding: var(--sp-3) 0;
}

.doc-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: var(--fs-13);
}

.doc-table th {
  text-align: left;
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  color: var(--fg-3);
  padding: var(--sp-2) var(--sp-2) var(--sp-2) 0;
  border-bottom: 1px solid var(--border-1);
  white-space: nowrap;
}

.doc-table td {
  padding: var(--sp-2) var(--sp-2) var(--sp-2) 0;
  border-bottom: 1px solid var(--border-2);
  vertical-align: middle;
  color: var(--fg-1);
}

.doc-table tr:last-child td { border-bottom: none; }

.doc-badge {
  display: inline-block;
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  font-family: var(--font-mono);
  padding: 1px 6px;
  border-radius: var(--rad-sm);
  text-transform: uppercase;
}
.doc-badge.pdf {
  background: var(--ark-red-100);
  color: var(--ark-red-600);
}
.doc-badge.html {
  background: var(--ark-blue-50);
  color: var(--ark-blue-600);
}

.doc-title-cell {
  max-width: 240px;
  overflow: hidden;
}

.doc-link {
  color: var(--fg-link);
  text-decoration: none;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-link:hover { text-decoration: underline; }

.mono {
  font-family: var(--font-mono);
  font-size: var(--fs-12);
  color: var(--fg-3);
  white-space: nowrap;
}

.chunks-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.chunk-item {
  padding: var(--sp-3);
  background: var(--bg-panel-2);
  border-radius: var(--rad-md);
  border: 1px solid var(--border-2);
}

.chunk-type {
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  color: var(--accent);
  text-transform: uppercase;
  margin-bottom: var(--sp-2);
}

.chunk-preview {
  font-size: var(--fs-13);
  color: var(--fg-1);
  line-height: var(--lh-normal);
  margin-bottom: var(--sp-2);
}

.chunk-tokens {
  font-size: var(--fs-12);
  color: var(--fg-3);
  font-family: var(--font-mono);
}

.chunk-more {
  font-size: var(--fs-13);
  color: var(--fg-3);
  text-align: center;
  padding: var(--sp-2);
  font-style: italic;
}

.text-btn {
  font-size: var(--fs-11);
  font-family: var(--font-mono);
  font-weight: var(--fw-semibold);
  padding: 2px 7px;
  border-radius: var(--rad-sm);
  border: 1px solid var(--border-1);
  background: var(--bg-panel);
  color: var(--fg-2);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}
.text-btn:hover {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
}
.ocr-btn {
  background: var(--ark-violet-100);
  border-color: var(--ark-violet-500);
  color: var(--ark-violet-500);
}
.ocr-btn:hover {
  background: var(--ark-violet-500);
  border-color: var(--ark-violet-500);
  color: #fff;
}

/* Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 22, 32, .45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--sp-6);
}

.modal {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-xl);
  box-shadow: var(--shadow-3);
  width: 100%;
  max-width: 780px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-5);
  border-bottom: 1px solid var(--border-1);
  flex: none;
}

.modal-title-block {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.modal-title {
  font-size: var(--fs-15);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.modal-url {
  font-size: var(--fs-12);
  color: var(--fg-link);
  text-decoration: none;
}
.modal-url:hover { text-decoration: underline; }

.modal-close {
  flex: none;
  width: 28px;
  height: 28px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 14px;
  color: var(--fg-3);
  border-radius: var(--rad-md);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--dur-fast) var(--ease-out);
}
.modal-close:hover { background: var(--bg-hover); color: var(--fg-1); }

.modal-meta {
  padding: var(--sp-2) var(--sp-5);
  font-size: var(--fs-12);
  color: var(--fg-3);
  font-family: var(--font-mono);
  background: var(--bg-panel-2);
  border-bottom: 1px solid var(--border-2);
  flex: none;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-4) var(--sp-5);
}

.modal-loading,
.modal-empty {
  text-align: center;
  padding: var(--sp-8);
  color: var(--fg-3);
  font-size: var(--fs-14);
}

.modal-text {
  font-family: var(--font-mono);
  font-size: var(--fs-13);
  line-height: var(--lh-relaxed);
  color: var(--fg-1);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
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
</style>