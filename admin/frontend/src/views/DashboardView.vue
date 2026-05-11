<script setup>
import { ref, onMounted, inject } from 'vue'
import { api } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import AjaxFrog from '@/components/AjaxFrog.vue'

const toast = inject('toast')
const stats = ref({})
const loading = ref(true)

async function loadStats() {
  try {
    loading.value = true
    const response = await api.getPipelineStats()
    stats.value = response.data
  } catch (error) {
    console.error('Failed to load stats:', error)
    toast('Ошибка загрузки статистики', 'error')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadStats()
})
</script>

<template>
  <div>
    <PageHeader title="Dashboard" />

    <div class="content">
      <div v-if="loading" class="loading">
        <AjaxFrog text="Загрузка статистики…" size="32px" />
      </div>

      <div v-else class="stats-grid">
        <div class="stat-card">
          <div class="stat-icon">📦</div>
          <div class="stat-content">
            <div class="stat-number">{{ stats.products || 0 }}</div>
            <div class="stat-label">Товары</div>
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-icon">📄</div>
          <div class="stat-content">
            <div class="stat-number">{{ stats.documents || 0 }}</div>
            <div class="stat-label">Документы</div>
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-icon">🧩</div>
          <div class="stat-content">
            <div class="stat-number">{{ stats.chunks || 0 }}</div>
            <div class="stat-label">RAG Чанки</div>
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-icon">🔄</div>
          <div class="stat-content">
            <div class="stat-number">{{ (stats.index_versions || []).length }}</div>
            <div class="stat-label">Версии индекса</div>
            <div class="stat-versions">
              <span v-for="v in (stats.index_versions || [])" :key="v" class="version-tag">{{ v }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!loading && stats.last_indexed" class="last-indexed">
        <div class="info-card">
          <h3 class="info-title">Последняя индексация</h3>
          <p class="info-text">{{ new Date(stats.last_indexed).toLocaleString('ru-RU') }}</p>
        </div>
      </div>
    </div>
  </div>
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

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--sp-6);
  margin-bottom: var(--sp-8);
}

.stat-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-6);
  box-shadow: var(--shadow-1);
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  transition: box-shadow var(--dur-fast) var(--ease-out);
}

.stat-card:hover {
  box-shadow: var(--shadow-2);
}

.stat-icon {
  font-size: 32px;
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-soft);
  border-radius: var(--rad-lg);
}

.stat-content {
  flex: 1;
}

.stat-number {
  font-size: var(--fs-24);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  line-height: var(--lh-tight);
  letter-spacing: var(--ls-tight);
  font-feature-settings: 'tnum';
}

.stat-label {
  font-size: var(--fs-12);
  color: var(--fg-2);
  font-weight: var(--fw-medium);
  margin-top: var(--sp-1);
}

.stat-versions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: var(--sp-1);
}

.version-tag {
  font-size: var(--fs-11);
  font-family: var(--font-mono);
  color: var(--accent);
  background: var(--accent-soft);
  border-radius: var(--rad-pill);
  padding: 1px 7px;
}

.last-indexed {
  display: flex;
  justify-content: center;
}

.info-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-5);
  box-shadow: var(--shadow-1);
  text-align: center;
  max-width: 400px;
}

.info-title {
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0 0 var(--sp-2) 0;
}

.info-text {
  font-size: var(--fs-14);
  color: var(--fg-2);
  margin: 0;
}
</style>