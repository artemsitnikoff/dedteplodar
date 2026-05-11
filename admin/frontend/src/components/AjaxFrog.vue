<script setup>
defineProps({
  text: { type: String, default: 'Загрузка…' },
  size: { type: String, default: '24px' },
})
</script>

<template>
  <span class="ajax-frog-inline">
    <span class="ajax-frog-emoji" :style="{ fontSize: size }">🐸</span>
    <span v-if="text" class="ajax-frog-text">{{ text }}</span>
  </span>
</template>

<style scoped>
.ajax-frog-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--fg-3, #9ca3af);
  font-size: 13px;
  user-select: none;
}

.ajax-frog-emoji {
  display: inline-block;
  line-height: 1;
  transform-origin: 50% 90%;
  animation: frogDance 520ms ease-in-out infinite;
}

.ajax-frog-text {
  font-weight: 500;
  letter-spacing: 0.01em;
}

@keyframes frogDance {
  0%   { transform: rotate(-14deg) translateY(0) scale(1); }
  20%  { transform: rotate(12deg) translateY(-4px) scale(1.07); }
  40%  { transform: rotate(-8deg) translateY(0) scale(1); }
  60%  { transform: rotate(14deg) translateY(-3px) scale(1.05); }
  80%  { transform: rotate(-10deg) translateY(0) scale(1); }
  100% { transform: rotate(-14deg) translateY(0) scale(1); }
}
</style>
