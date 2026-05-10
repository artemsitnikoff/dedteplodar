<script setup>
defineProps({
  title: {
    type: String,
    required: true
  }
})
</script>

<template>
  <header class="page-header">
    <h1 class="page-title">{{ title }}</h1>
    <div class="page-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: var(--sp-6) var(--sp-6) var(--sp-4);
  border-bottom: 1px solid var(--border-2);
  background: var(--bg-app);
}

.page-title {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  line-height: var(--lh-tight);
  letter-spacing: var(--ls-tight);
  color: var(--fg-1);
  margin: 0;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex: none;
}
</style>