<script setup>
import { computed } from 'vue'
import AjaxFrog from '@/components/AjaxFrog.vue'

const props = defineProps({
  columns: {
    type: Array,
    required: true
  },
  data: {
    type: Array,
    required: true
  },
  loading: {
    type: Boolean,
    default: false
  },
  pagination: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['row-click', 'page-change'])

function handleRowClick(item) {
  emit('row-click', item)
}

function handlePageChange(page) {
  emit('page-change', page)
}

const totalPages = computed(() => {
  if (!props.pagination) return 0
  return Math.ceil(props.pagination.total / props.pagination.per_page)
})
</script>

<template>
  <div class="data-table">
    <div v-if="loading" class="table-loading">
      <AjaxFrog />
    </div>

    <table v-else class="table">
      <thead>
        <tr>
          <th
            v-for="col in columns"
            :key="col.key"
            :class="['th', col.align && `align-${col.align}`]"
            :style="{ width: col.width }"
          >
            {{ col.title }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in data"
          :key="item.id"
          class="tr"
          @click="handleRowClick(item)"
        >
          <td
            v-for="col in columns"
            :key="col.key"
            :class="['td', col.align && `align-${col.align}`]"
          >
            <slot
              :name="`cell-${col.key}`"
              :item="item"
              :value="item[col.key]"
            >
              {{ item[col.key] }}
            </slot>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="data.length === 0 && !loading" class="table-empty">
      Нет данных
    </div>

    <!-- Pagination -->
    <div v-if="pagination && totalPages > 1" class="pagination">
      <div class="pagination-info">
        {{ (pagination.page - 1) * pagination.per_page + 1 }}–{{ Math.min(pagination.page * pagination.per_page, pagination.total) }} из {{ pagination.total }}
      </div>
      <div class="pagination-controls">
        <button
          class="pagination-btn"
          :disabled="pagination.page === 1"
          @click="handlePageChange(pagination.page - 1)"
        >
          Назад
        </button>
        <span class="pagination-current">{{ pagination.page }} из {{ totalPages }}</span>
        <button
          class="pagination-btn"
          :disabled="pagination.page === totalPages"
          @click="handlePageChange(pagination.page + 1)"
        >
          Далее
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.data-table {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  overflow: hidden;
}

.table-loading {
  padding: var(--sp-8);
  text-align: center;
  color: var(--fg-3);
  font-size: var(--fs-14);
}

.table {
  width: 100%;
  border-collapse: collapse;
}

.th {
  background: var(--bg-panel);
  padding: var(--sp-3) var(--sp-4);
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  color: var(--fg-2);
  text-align: left;
  border-bottom: 1px solid var(--border-1);
}

.th.align-center { text-align: center; }
.th.align-right { text-align: right; }

.tr {
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out);
}

.tr:hover {
  background: var(--bg-hover);
}

.td {
  padding: var(--sp-3) var(--sp-4);
  font-size: var(--fs-13);
  color: var(--fg-1);
  border-bottom: 1px solid var(--border-2);
}

.td.align-center { text-align: center; }
.td.align-right { text-align: right; }

.tr:last-child .td {
  border-bottom: none;
}

.table-empty {
  padding: var(--sp-8);
  text-align: center;
  color: var(--fg-3);
  font-size: var(--fs-14);
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4);
  border-top: 1px solid var(--border-2);
  background: var(--bg-panel);
}

.pagination-info {
  font-size: var(--fs-13);
  color: var(--fg-2);
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.pagination-btn {
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  font-size: var(--fs-13);
  font-weight: var(--fw-medium);
  color: var(--fg-1);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}

.pagination-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.pagination-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pagination-current {
  font-size: var(--fs-13);
  color: var(--fg-2);
  font-weight: var(--fw-medium);
}
</style>