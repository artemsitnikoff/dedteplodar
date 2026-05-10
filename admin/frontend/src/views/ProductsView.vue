<script setup>
import { ref, reactive, onMounted, watch, inject } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import DataTable from '@/components/DataTable.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

const router = useRouter()
const route = useRoute()
const toast = inject('toast')

const products = ref([])
const categories = ref([])
const loading = ref(false)
const pagination = ref({ page: 1, per_page: 50, total: 0 })

const filters = reactive({
  search: '',
  category_id: ''
})

const confirmDelete = ref({
  show: false,
  product: null
})

const columns = [
  { key: 'id', title: 'ID', width: '80px', align: 'center' },
  { key: 'name', title: 'Название' },
  { key: 'model', title: 'Модель', width: '150px' },
  { key: 'price', title: 'Цена', width: '120px', align: 'right' },
  { key: 'category_name', title: 'Категория', width: '200px' },
  { key: 'chunks_count', title: 'Чанков', width: '100px', align: 'center' },
  { key: 'updated_at', title: 'Обновлено', width: '140px' },
]

async function loadProducts() {
  try {
    loading.value = true
    const params = {
      page: pagination.value.page,
      per_page: pagination.value.per_page,
      ...filters
    }

    if (!params.search) delete params.search
    if (!params.category_id) delete params.category_id

    const response = await api.getProducts(params)
    products.value = response.data.items
    pagination.value = {
      page: response.data.page,
      per_page: response.data.per_page,
      total: response.data.total
    }
  } catch (error) {
    console.error('Failed to load products:', error)
    toast('Ошибка загрузки товаров', 'error')
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  try {
    const response = await api.getCategoriesTree()
    categories.value = flattenCategories(response.data)
  } catch (error) {
    console.error('Failed to load categories:', error)
  }
}

function flattenCategories(cats, prefix = '') {
  const result = []
  for (const cat of cats) {
    const name = prefix ? `${prefix} / ${cat.name}` : cat.name
    result.push({ id: cat.id, name })
    if (cat.children && cat.children.length > 0) {
      result.push(...flattenCategories(cat.children, name))
    }
  }
  return result
}

function handleRowClick(product) {
  router.push({ name: 'product-edit', params: { id: product.id } })
}

function handlePageChange(page) {
  pagination.value.page = page
  loadProducts()
}

function handleSearch() {
  pagination.value.page = 1
  router.replace({
    query: {
      ...(filters.search ? { search: filters.search } : {}),
      ...(filters.category_id ? { category_id: filters.category_id } : {}),
    }
  })
  loadProducts()
}

function handleDeleteClick(product, event) {
  event.stopPropagation()
  confirmDelete.value = { show: true, product }
}

async function confirmDeleteProduct() {
  try {
    await api.deleteProduct(confirmDelete.value.product.id)
    toast('Товар удален', 'success')
    confirmDelete.value = { show: false, product: null }
    loadProducts()
  } catch (error) {
    console.error('Failed to delete product:', error)
    toast('Ошибка удаления товара', 'error')
  }
}

function cancelDelete() {
  confirmDelete.value = { show: false, product: null }
}

const formatPrice = (price) => {
  return price ? `${price.toLocaleString('ru-RU')} ₽` : '—'
}

const formatDate = (dateStr) => {
  return dateStr ? new Date(dateStr).toLocaleDateString('ru-RU') : '—'
}

// Sync filters from URL query params whenever route.query changes (incl. initial navigation)
watch(
  () => route.query,
  (q) => {
    filters.category_id = q.category_id ? Number(q.category_id) : ''
    filters.search = q.search || ''
    pagination.value.page = 1
    loadProducts()
  },
  { immediate: true }
)

onMounted(() => {
  loadCategories()
})
</script>

<template>
  <div>
    <PageHeader title="Товары">
      <template #actions>
        <div class="filters">
          <input
            v-model="filters.search"
            placeholder="Поиск по названию..."
            class="search-input"
            @input="handleSearch"
          />
          <select
            v-model="filters.category_id"
            class="category-select"
            @change="handleSearch"
          >
            <option value="">Все категории</option>
            <option
              v-for="category in categories"
              :key="category.id"
              :value="category.id"
            >
              {{ category.name }}
            </option>
          </select>
        </div>
      </template>
    </PageHeader>

    <div class="content">
      <DataTable
        :columns="columns"
        :data="products"
        :loading="loading"
        :pagination="pagination"
        @row-click="handleRowClick"
        @page-change="handlePageChange"
      >
        <template #cell-price="{ value }">
          {{ formatPrice(value) }}
        </template>

        <template #cell-updated_at="{ value }">
          {{ formatDate(value) }}
        </template>

        <template #cell-chunks_count="{ value, item }">
          <div class="chunks-count">
            <span class="count">{{ value || 0 }}</span>
            <button
              v-if="value > 0"
              class="delete-btn"
              @click="handleDeleteClick(item, $event)"
            >
              🗑
            </button>
          </div>
        </template>
      </DataTable>
    </div>

    <ConfirmDialog
      :show="confirmDelete.show"
      title="Удалить товар"
      :message="`Вы уверены, что хотите удалить товар «${confirmDelete.product?.name}»?`"
      confirm-text="Удалить"
      danger
      @confirm="confirmDeleteProduct"
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

.category-select {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  font: inherit;
  font-size: var(--fs-14);
  color: var(--fg-1);
  width: 200px;
  cursor: pointer;
}

.category-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--shadow-focus);
}

.chunks-count {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}

.count {
  font-family: var(--font-mono);
  font-weight: var(--fw-medium);
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
</style>