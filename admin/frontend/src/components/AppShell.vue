<script setup>
import AppSidebar from '@/components/AppSidebar.vue'
import AjaxFrog from '@/components/AjaxFrog.vue'
</script>

<template>
  <AppSidebar />
  <div class="main-column">
    <header class="topbar">
      <div class="topbar-title">
        <span class="topbar-emoji">🔥</span>
        <span class="topbar-text">ДедТеплодар</span>
      </div>
      <div class="topbar-right">
        <AjaxFrog />
      </div>
    </header>
    <main class="main-content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.main-column {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--bg-app);
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-3) var(--sp-6);
  border-bottom: 1px solid var(--border-1);
  background: var(--bg-panel);
  height: 52px;
  flex-shrink: 0;
}

.topbar-title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-16);
  font-weight: var(--fw-bold);
  color: var(--fg-1);
  letter-spacing: 0.01em;
}

.topbar-emoji {
  font-size: 18px;
  line-height: 1;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.main-content {
  background: var(--bg-app);
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
</style>
