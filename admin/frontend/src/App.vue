<script setup>
import { ref, provide } from 'vue'
import AppShell from '@/components/AppShell.vue'

// Toast notifications
const toasts = ref([])
let toastId = 0

function showToast(message, type = 'info') {
  const id = ++toastId
  toasts.value.push({ id, message, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 4000)
}

provide('toast', showToast)
</script>

<template>
  <div class="app">
    <AppShell />

    <!-- Toast notifications -->
    <div class="toast-container">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        :class="['toast', `toast-${toast.type}`]"
      >
        {{ toast.message }}
      </div>
    </div>
  </div>
</template>

<style>
html, body, #app {
  height: 100%;
  margin: 0;
  padding: 0;
}

body {
  font-family: var(--font-sans);
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--fg-1);
  background: var(--bg-app);
  font-feature-settings: 'cv11', 'ss01', 'tnum';
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

* {
  box-sizing: border-box;
}

.app {
  display: grid;
  grid-template-columns: 240px 1fr;
  height: 100vh;
  background: var(--bg-app);
  color: var(--fg-1);
  min-width: 1180px;
}

/* Toast notifications */
.toast-container {
  position: fixed;
  top: var(--sp-4);
  right: var(--sp-4);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.toast {
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--rad-md);
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  box-shadow: var(--shadow-2);
  font-size: var(--fs-14);
  max-width: 400px;
  animation: toastIn 200ms var(--ease-out);
}

.toast-success {
  background: var(--ark-green-100);
  border-color: var(--ark-green-500);
  color: var(--ark-green-600);
}

.toast-error {
  background: var(--ark-red-100);
  border-color: var(--ark-red-500);
  color: var(--ark-red-600);
}

.toast-info {
  background: var(--ark-blue-100);
  border-color: var(--ark-blue-500);
  color: var(--ark-blue-700);
}

@keyframes toastIn {
  from {
    opacity: 0;
    transform: translateX(100px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>