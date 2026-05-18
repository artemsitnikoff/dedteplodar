<script setup>
import { ref, onMounted, inject } from 'vue'
import { api } from '@/api/index.js'
import AjaxFrog from '@/components/AjaxFrog.vue'
import { categoryBadgeClass, qtypeCls, qtypeLabel } from '@/utils/badges.js'

const toast = inject('toast')

const dataset = ref([])
const datasetLoading = ref(false)
const selectedDataset = ref('synthetic')

const DATASETS = [
  { value: 'synthetic', label: 'Synthetic (50)', hint: '50 синтетических вопросов, ручная составка' },
  { value: 'mango',     label: 'Mango (50)',     hint: '50 реальных вопросов из транскрибаций звонков ТП' },
]

async function loadDataset() {
  datasetLoading.value = true
  try {
    const res = await api.getEvalDataset(selectedDataset.value)
    dataset.value = res.data.items
  } catch {
    toast('Ошибка загрузки датасета', 'error')
  } finally {
    datasetLoading.value = false
  }
}

onMounted(loadDataset)

defineExpose({ dataset })
</script>

<template>
  <div class="eval-dataset-tab">
    <div class="dataset-toolbar">
      <select v-model="selectedDataset" class="dataset-select" @change="loadDataset">
        <option v-for="d in DATASETS" :key="d.value" :value="d.value">
          {{ d.label }}
        </option>
      </select>
      <div class="dataset-hint">
        {{ DATASETS.find(d => d.value === selectedDataset)?.hint }}
      </div>
    </div>

    <div class="table-wrap">
      <div v-if="datasetLoading" class="loading-state">
        <AjaxFrog />
      </div>
      <table v-else class="log-table">
        <colgroup>
          <col style="width: 56px" />
          <col style="width: 110px" />
          <col style="width: auto" />
          <col style="width: 120px" />
        </colgroup>
        <thead>
          <tr>
            <th>#</th>
            <th>Категория</th>
            <th>Вопрос</th>
            <th>Ожид. тип</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in dataset" :key="item.id" class="log-row">
            <td class="cell-num">{{ item.id }}</td>
            <td>
              <span :class="['cat-badge', categoryBadgeClass(item.category)]">
                {{ item.category }}
              </span>
            </td>
            <td class="cell-q">{{ item.question }}</td>
            <td>
              <span :class="['qtype-badge', qtypeCls(item.expected_type)]">
                {{ qtypeLabel(item.expected_type) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.dataset-toolbar {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
  flex-wrap: wrap;
}

.dataset-select {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-input);
  color: var(--fg-1);
  font-size: var(--fs-14);
  cursor: pointer;
  min-width: 180px;
}

.dataset-hint {
  font-size: var(--fs-12);
  color: var(--fg-3);
}

.loading-state {
  padding: var(--sp-8);
  text-align: center;
}

/* Badge styles moved to global @/assets/badges.css */
</style>
