<script setup>
import { computed } from 'vue'
import { activeRequests } from '@/api'

const isBusy = computed(() => activeRequests.value > 0)
</script>

<template>
  <Transition name="frog-fade">
    <div v-if="isBusy" class="ajax-frog-chip" title="Загружаю…">
      <span class="ajax-frog-emoji">🐸</span>
      <span class="ajax-frog-text">загружаю…</span>
    </div>
  </Transition>
</template>

<style scoped>
.ajax-frog-chip {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px 6px 10px;
  background: var(--bg-elevated, #1f2937);
  color: var(--fg-1, #f3f4f6);
  border: 1px solid var(--border-1, rgba(255,255,255,0.12));
  border-radius: 999px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.25);
  font-size: 13px;
  pointer-events: none;
}

.ajax-frog-emoji {
  font-size: 20px;
  line-height: 1;
  display: inline-block;
  transform-origin: 50% 90%;
  animation: frogDance 480ms ease-in-out infinite;
}

.ajax-frog-text {
  font-weight: 500;
  letter-spacing: 0.01em;
}

@keyframes frogDance {
  0%   { transform: rotate(-14deg) translateY(0) scale(1); }
  20%  { transform: rotate(12deg) translateY(-4px) scale(1.08); }
  40%  { transform: rotate(-8deg) translateY(0) scale(1); }
  60%  { transform: rotate(14deg) translateY(-3px) scale(1.05); }
  80%  { transform: rotate(-10deg) translateY(0) scale(1); }
  100% { transform: rotate(-14deg) translateY(0) scale(1); }
}

/* Smooth show/hide */
.frog-fade-enter-from,
.frog-fade-leave-to {
  opacity: 0;
  transform: translate(-50%, 8px);
}
.frog-fade-enter-active,
.frog-fade-leave-active {
  transition: opacity 180ms ease, transform 180ms ease;
}
</style>
