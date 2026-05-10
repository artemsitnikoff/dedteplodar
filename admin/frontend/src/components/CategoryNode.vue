<script setup>
import { computed } from 'vue'

const props = defineProps({
  category: Object,
  expandedNodes: Object,  // Set passed down from the view
  level: { type: Number, default: 0 }
})

const emit = defineEmits(['toggle', 'select'])

const hasChildren = computed(() =>
  props.category.children && props.category.children.length > 0
)

const isExpanded = computed(() => props.expandedNodes.has(props.category.id))
</script>

<template>
  <div class="tree-node">
    <div
      class="node-content"
      :style="{ paddingLeft: `${level * 24 + 12}px` }"
      @click="emit('select', category)"
    >
      <button
        v-if="hasChildren"
        :class="['expand-btn', { expanded: isExpanded }]"
        @click.stop="emit('toggle', category.id)"
      >▶</button>
      <span v-else class="expand-placeholder" />
      <span class="node-icon">{{ hasChildren ? '📂' : '📄' }}</span>
      <span class="node-name">{{ category.name }}</span>
      <span class="node-count">{{ category.products_count || 0 }}</span>
    </div>

    <template v-if="isExpanded && hasChildren">
      <CategoryNode
        v-for="child in category.children"
        :key="child.id"
        :category="child"
        :expanded-nodes="expandedNodes"
        :level="level + 1"
        @toggle="emit('toggle', $event)"
        @select="emit('select', $event)"
      />
    </template>
  </div>
</template>

<style scoped>
.node-content {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 10px var(--sp-4);
  cursor: pointer;
  border-bottom: 1px solid var(--border-2);
  transition: background var(--dur-fast) var(--ease-out);
}
.node-content:hover { background: var(--bg-hover); }

.expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex: none;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 10px;
  color: var(--fg-3);
  transition: transform var(--dur-fast) var(--ease-out);
}
.expand-btn.expanded { transform: rotate(90deg); }
.expand-placeholder { width: 20px; flex: none; }

.node-icon { font-size: 15px; flex: none; }

.node-name {
  flex: 1;
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  color: var(--fg-1);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-count {
  font-size: var(--fs-12);
  color: var(--fg-3);
  font-family: var(--font-mono);
  background: var(--bg-panel);
  border: 1px solid var(--border-2);
  border-radius: var(--rad-pill);
  padding: 1px 8px;
  flex: none;
}
</style>
