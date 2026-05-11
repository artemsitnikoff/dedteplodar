<script setup>
import { ref, onMounted, inject } from 'vue'
import { api } from '@/api/index.js'
import AjaxFrog from '@/components/AjaxFrog.vue'
import { categoryBadgeClass, qtypeCls, qtypeLabel } from '@/utils/badges.js'

const toast = inject('toast')

const dataset = ref([])
const datasetLoading = ref(false)

async function loadDataset() {
  datasetLoading.value = true
  try {
    const res = await api.getEvalDataset()
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
/* Styles will be inherited from parent component */
.loading-state {
  padding: var(--sp-8);
  text-align: center;
}

.cat-badge {
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  padding: 2px 6px;
  border-radius: var(--rad-sm);
  white-space: nowrap;
  background: var(--bg-panel-2);
  color: var(--fg-2);
}

.cat-selection { background: color-mix(in srgb, var(--ark-blue-600) 15%, transparent); color: var(--ark-blue-600); }
.cat-specs { background: color-mix(in srgb, var(--ark-green-600) 15%, transparent); color: var(--ark-green-600); }
.cat-install { background: color-mix(in srgb, var(--ark-purple-600) 15%, transparent); color: var(--ark-purple-600); }
.cat-company { background: color-mix(in srgb, var(--ark-amber-600) 15%, transparent); color: var(--ark-amber-600); }
.cat-dealer { background: color-mix(in srgb, var(--ark-red-600) 15%, transparent); color: var(--ark-red-600); }

.qtype-badge {
  font-size: var(--fs-11);
  font-weight: var(--fw-semibold);
  padding: 2px 6px;
  border-radius: var(--rad-sm);
  white-space: nowrap;
  background: var(--bg-panel-2);
  color: var(--fg-3);
}

.qt-rag { background: color-mix(in srgb, var(--ark-blue-600) 15%, transparent); color: var(--ark-blue-600); }
.qt-ref { background: color-mix(in srgb, var(--ark-green-600) 15%, transparent); color: var(--ark-green-600); }
.qt-dealer { background: color-mix(in srgb, var(--ark-purple-600) 15%, transparent); color: var(--ark-purple-600); }
.qt-faq { background: color-mix(in srgb, var(--ark-amber-600) 15%, transparent); color: var(--ark-amber-600); }
.qt-error { background: color-mix(in srgb, var(--ark-red-600) 15%, transparent); color: var(--ark-red-600); }
</style>