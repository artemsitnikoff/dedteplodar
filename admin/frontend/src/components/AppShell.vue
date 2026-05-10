<script setup>
import AppSidebar from '@/components/AppSidebar.vue'
</script>

<template>
  <AppSidebar />
  <main class="main-content">
    <RouterView />
  </main>
</template>

<style scoped>
.main-content {
  background: var(--bg-app);
  overflow-y: auto;
  min-height: 0;
}
</style>