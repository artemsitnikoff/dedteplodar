<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: {
    type: String,
    required: true
  },
  type: {
    type: String,
    default: 'default' // default, success, warning, danger, info
  }
})

const statusClass = computed(() => {
  switch (props.type) {
    case 'success': return 'badge-success'
    case 'warning': return 'badge-warning'
    case 'danger': return 'badge-danger'
    case 'info': return 'badge-info'
    default: return 'badge-default'
  }
})
</script>

<template>
  <span :class="['badge', statusClass]">
    {{ status }}
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-1) var(--sp-2);
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
  border-radius: var(--rad-sm);
  text-transform: uppercase;
  letter-spacing: var(--ls-wide);
}

.badge-default {
  background: var(--ark-gray-200);
  color: var(--ark-gray-700);
}

.badge-success {
  background: var(--ark-green-100);
  color: var(--ark-green-600);
}

.badge-warning {
  background: var(--ark-yellow-100);
  color: var(--ark-yellow-600);
}

.badge-danger {
  background: var(--ark-red-100);
  color: var(--ark-red-600);
}

.badge-info {
  background: var(--ark-blue-100);
  color: var(--ark-blue-700);
}
</style>