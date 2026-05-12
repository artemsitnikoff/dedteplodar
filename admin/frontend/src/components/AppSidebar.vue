<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const catalogExpanded = ref(true)
const faqExpanded = ref(true)

const isActive = (routeName) => route.name === routeName
const isActiveParent = (routes) => routes.some(r => route.name === r)

function navigate(routeName) {
  router.push({ name: routeName })
}
</script>

<template>
  <aside class="sidebar">
    <!-- Brand -->
    <div class="brand">
      <div class="brand-mark">
        <span class="brand-emoji">🔥</span>
      </div>
      <div class="brand-name">
        ДедТеплодар
        <span class="brand-version">v1.1</span>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="nav">
      <!-- Dashboard -->
      <button
        :class="['nav-item', { active: isActive('dashboard') }]"
        @click="navigate('dashboard')"
      >
        <span class="nav-icon">📊</span>
        <span class="nav-label">Dashboard</span>
      </button>

      <!-- Каталог -->
      <button
        :class="['nav-item', 'nav-parent', { active: isActiveParent(['products', 'product-edit', 'categories']) }]"
        @click="catalogExpanded = !catalogExpanded"
      >
        <span class="nav-icon">📦</span>
        <span class="nav-label">Каталог</span>
        <span :class="['nav-chevron', { open: catalogExpanded }]">▼</span>
      </button>

      <div v-if="catalogExpanded" class="nav-sub">
        <button
          :class="['nav-sub-item', { active: isActive('products') || isActive('product-edit') }]"
          @click="navigate('products')"
        >
          Товары
        </button>
        <button
          :class="['nav-sub-item', { active: isActive('categories') }]"
          @click="navigate('categories')"
        >
          Категории
        </button>
      </div>

      <!-- Документы -->
      <button
        :class="['nav-item', { active: isActive('documents') }]"
        @click="navigate('documents')"
      >
        <span class="nav-icon">📄</span>
        <span class="nav-label">Документы</span>
      </button>

      <!-- RAG Чанки -->
      <button
        :class="['nav-item', { active: isActive('chunks') }]"
        @click="navigate('chunks')"
      >
        <span class="nav-icon">🧩</span>
        <span class="nav-label">RAG Чанки</span>
      </button>

      <!-- Справочники -->
      <button
        :class="['nav-item', 'nav-parent', { active: isActiveParent(['faq-company', 'faq-dealers']) }]"
        @click="faqExpanded = !faqExpanded"
      >
        <span class="nav-icon">📚</span>
        <span class="nav-label">Справочники</span>
        <span :class="['nav-chevron', { open: faqExpanded }]">▼</span>
      </button>

      <div v-if="faqExpanded" class="nav-sub">
        <button
          :class="['nav-sub-item', { active: isActive('faq-company') }]"
          @click="navigate('faq-company')"
        >
          О компании
        </button>
        <button
          :class="['nav-sub-item', { active: isActive('faq-dealers') }]"
          @click="navigate('faq-dealers')"
        >
          Дилеры
        </button>
      </div>

      <!-- Конвейер -->
      <button
        :class="['nav-item', { active: isActive('pipeline') }]"
        @click="navigate('pipeline')"
      >
        <span class="nav-icon">⚙️</span>
        <span class="nav-label">Конвейер</span>
      </button>

      <!-- Журнал -->
      <button
        :class="['nav-item', { active: isActive('journal') }]"
        @click="navigate('journal')"
      >
        <span class="nav-icon">📋</span>
        <span class="nav-label">Журнал</span>
      </button>

      <!-- FAQ -->
      <button
        :class="['nav-item', { active: isActive('faq-entries') }]"
        @click="navigate('faq-entries')"
      >
        <span class="nav-icon">⚡</span>
        <span class="nav-label">FAQ</span>
      </button>

      <!-- Eval -->
      <button
        :class="['nav-item', { active: isActive('eval') }]"
        @click="navigate('eval')"
      >
        <span class="nav-icon">🧪</span>
        <span class="nav-label">Eval</span>
      </button>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  background: var(--bg-panel);
  border-right: 1px solid var(--border-1);
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-4);
  border-bottom: 1px solid var(--border-1);
  flex: none;
}

.brand-mark {
  width: 28px;
  height: 28px;
  border-radius: var(--rad-md);
  background: linear-gradient(135deg, #FFD2E8 0%, #FFB1D6 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

.brand-emoji {
  font-size: 18px;
  line-height: 1;
}

.brand-name {
  font-weight: var(--fw-bold);
  font-size: var(--fs-15);
  letter-spacing: var(--ls-tight);
  color: var(--fg-1);
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
}

.brand-version {
  font-size: 10px;
  font-weight: var(--fw-medium);
  color: var(--fg-3);
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}

.nav {
  flex: 1;
  padding: var(--sp-3) var(--sp-2);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: 100%;
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--rad-md);
  border: 0;
  background: transparent;
  font: inherit;
  font-size: var(--fs-13);
  font-weight: var(--fw-medium);
  color: var(--fg-1);
  cursor: pointer;
  text-align: left;
  transition: background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}

.nav-item:hover {
  background: var(--bg-hover);
}

.nav-item.active {
  background: var(--bg-elevated);
  color: var(--accent);
  box-shadow: var(--shadow-1);
}

.nav-icon {
  flex: none;
  font-size: 16px;
  width: 18px;
  text-align: center;
}

.nav-label {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-chevron {
  flex: none;
  font-size: 10px;
  color: var(--fg-3);
  transition: transform var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}

.nav-chevron.open {
  transform: rotate(180deg);
  color: var(--accent);
}

.nav-parent.active .nav-chevron {
  color: var(--accent);
}

.nav-sub {
  margin: var(--sp-1) 0 var(--sp-2) 0;
  padding: var(--sp-2) var(--sp-1);
  background: var(--bg-panel-2);
  border-radius: var(--rad-lg);
  border: 1px solid var(--border-2);
  animation: subDown 180ms var(--ease-out);
}

@keyframes subDown {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.nav-sub-item {
  display: block;
  width: 100%;
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--rad-sm);
  border: 0;
  background: transparent;
  font: inherit;
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
  color: var(--fg-1);
  cursor: pointer;
  text-align: left;
  transition: background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}

.nav-sub-item:hover {
  background: var(--bg-hover);
}

.nav-sub-item.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: var(--fw-semibold);
}
</style>