<script setup>
import { ref, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import CategoryNode from '@/components/CategoryNode.vue'

const router = useRouter()
const toast = inject('toast', () => {})

const categories = ref([])
const loading = ref(true)
const expandedNodes = ref(new Set())

async function loadCategories() {
  try {
    loading.value = true
    const response = await api.getCategoriesTree()
    categories.value = response.data
    // Auto-expand root nodes that have children
    response.data.forEach(cat => {
      if (cat.children && cat.children.length > 0) expandedNodes.value.add(cat.id)
    })
  } catch (error) {
    console.error('Failed to load categories:', error)
    toast('Ошибка загрузки категорий', 'error')
  } finally {
    loading.value = false
  }
}

function toggleNode(categoryId) {
  const set = new Set(expandedNodes.value)
  if (set.has(categoryId)) set.delete(categoryId)
  else set.add(categoryId)
  expandedNodes.value = set
}

function handleSelect(category) {
  router.push({ name: 'products', query: { category_id: category.id } })
}

onMounted(loadCategories)
</script>

<template>
  <div>
    <PageHeader title="Категории товаров">
      <template #actions>
        <span class="cat-summary" v-if="!loading">
          {{ categories.length }} разделов
        </span>
      </template>
    </PageHeader>

    <div class="content">
      <div v-if="loading" class="loading">Загрузка…</div>

      <div v-else class="tree-container">
        <div class="tree-card">
          <CategoryNode
            v-for="cat in categories"
            :key="cat.id"
            :category="cat"
            :expanded-nodes="expandedNodes"
            :level="0"
            @toggle="toggleNode"
            @select="handleSelect"
          />
          <div v-if="categories.length === 0" class="empty-state">
            Категории не найдены
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content { padding: var(--sp-6); }

.cat-summary {
  font-size: var(--fs-13);
  color: var(--fg-3);
}

.loading {
  text-align: center;
  padding: var(--sp-8);
  color: var(--fg-3);
  font-size: var(--fs-14);
}

.tree-container { max-width: 860px; }

.tree-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  overflow: hidden;
  box-shadow: var(--shadow-1);
}

.empty-state {
  text-align: center;
  padding: var(--sp-8);
  color: var(--fg-3);
  font-size: var(--fs-14);
}
</style>
