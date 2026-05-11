<script setup>
import { computed } from 'vue'
import { activeRequests } from '@/api'

const isBusy = computed(() => activeRequests.value > 0)
</script>

<template>
  <span class="ajax-frog" :class="{ busy: isBusy }" :title="isBusy ? 'Загружаю…' : ''">🐸</span>
</template>

<style scoped>
.ajax-frog {
  display: inline-block;
  font-size: 18px;
  line-height: 1;
  user-select: none;
  opacity: 0.35;
  filter: grayscale(0.6);
  transition: opacity 200ms ease, filter 200ms ease;
  transform-origin: 50% 90%;
}

.ajax-frog:hover {
  opacity: 1;
  filter: none;
  animation: frogDance 600ms ease-in-out infinite;
}

.ajax-frog.busy {
  opacity: 1;
  filter: none;
  animation: frogDance 480ms ease-in-out infinite;
}

@keyframes frogDance {
  0%   { transform: rotate(-12deg) translateY(0); }
  25%  { transform: rotate(10deg) translateY(-3px); }
  50%  { transform: rotate(-8deg) translateY(0); }
  75%  { transform: rotate(12deg) translateY(-2px); }
  100% { transform: rotate(-12deg) translateY(0); }
}
</style>
