<script setup>
const props = defineProps({
  show: {
    type: Boolean,
    required: true
  },
  title: {
    type: String,
    default: 'Подтверждение'
  },
  message: {
    type: String,
    required: true
  },
  confirmText: {
    type: String,
    default: 'Подтвердить'
  },
  cancelText: {
    type: String,
    default: 'Отмена'
  },
  danger: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['confirm', 'cancel'])

function handleConfirm() {
  emit('confirm')
}

function handleCancel() {
  emit('cancel')
}

function handleBackdropClick(event) {
  if (event.target === event.currentTarget) {
    handleCancel()
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="dialog-backdrop" @click="handleBackdropClick">
      <div class="dialog">
        <div class="dialog-header">
          <h3 class="dialog-title">{{ title }}</h3>
        </div>
        <div class="dialog-body">
          <p class="dialog-message">{{ message }}</p>
        </div>
        <div class="dialog-footer">
          <button class="btn btn-outline" @click="handleCancel">
            {{ cancelText }}
          </button>
          <button
            :class="['btn', danger ? 'btn-danger' : 'btn-primary']"
            @click="handleConfirm"
          >
            {{ confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: backdropIn 200ms var(--ease-out);
}

.dialog {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-xl);
  box-shadow: var(--shadow-3);
  width: 100%;
  max-width: 400px;
  margin: var(--sp-4);
  animation: dialogIn 200ms var(--ease-out);
}

.dialog-header {
  padding: var(--sp-5) var(--sp-5) var(--sp-2);
}

.dialog-title {
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0;
}

.dialog-body {
  padding: 0 var(--sp-5) var(--sp-4);
}

.dialog-message {
  font-size: var(--fs-14);
  color: var(--fg-1);
  line-height: var(--lh-normal);
  margin: 0;
}

.dialog-footer {
  padding: var(--sp-4) var(--sp-5) var(--sp-5);
  display: flex;
  gap: var(--sp-3);
  justify-content: flex-end;
}

.btn {
  padding: var(--sp-2) var(--sp-4);
  border-radius: var(--rad-md);
  border: 1px solid;
  font: inherit;
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}

.btn-outline {
  background: var(--bg-elevated);
  border-color: var(--border-1);
  color: var(--fg-1);
}

.btn-outline:hover {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--fg-on-accent);
}

.btn-primary:hover {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}

.btn-danger {
  background: var(--danger);
  border-color: var(--danger);
  color: var(--fg-on-accent);
}

.btn-danger:hover {
  background: var(--ark-red-600);
  border-color: var(--ark-red-600);
}

@keyframes backdropIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes dialogIn {
  from {
    opacity: 0;
    transform: scale(0.9) translateY(-20px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}
</style>