<script setup>
import { computed } from 'vue'
import { activeRequests } from '@/api'

const isBusy = computed(() => activeRequests.value > 0)
</script>

<template>
  <span class="ajax-frog" :class="{ busy: isBusy }" title="ДедТеплодарова лягушка-помощник">
    🐸
  </span>
</template>

<style scoped>
.ajax-frog {
  display: inline-block;
  font-size: 22px;
  line-height: 1;
  user-select: none;
  cursor: pointer;
  transform-origin: 50% 90%;
  transition: filter 200ms ease;
  filter: grayscale(0.1);
}

.ajax-frog:hover {
  animation: frogDance 600ms ease-in-out infinite;
  filter: grayscale(0);
}

.ajax-frog.busy {
  animation: frogDance 480ms ease-in-out infinite;
  filter: grayscale(0) drop-shadow(0 0 6px rgba(34, 197, 94, 0.55));
}

@keyframes frogDance {
  0%   { transform: rotate(-12deg) translateY(0) scale(1); }
  20%  { transform: rotate(10deg) translateY(-4px) scale(1.06); }
  40%  { transform: rotate(-8deg) translateY(0) scale(1); }
  60%  { transform: rotate(12deg) translateY(-3px) scale(1.05); }
  80%  { transform: rotate(-10deg) translateY(0) scale(1); }
  100% { transform: rotate(-12deg) translateY(0) scale(1); }
}
</style>
