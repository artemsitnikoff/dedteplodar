<script setup>
import { ref, reactive, onMounted, onUnmounted, inject } from 'vue'
import { api } from '@/api'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import AjaxFrog from '@/components/AjaxFrog.vue'

const toast = inject('toast')

const stats = ref({})
const tasks = ref([])
const loading = ref(true)
const importFile = ref(null)
const uploading = ref(false)
const rebuildingIndex = ref(false)

let pollInterval = null

async function loadStats() {
  try {
    const response = await api.getPipelineStats()
    stats.value = response.data
  } catch (error) {
    console.error('Failed to load stats:', error)
  }
}

async function loadTasks() {
  try {
    // In a real app, we'd have an endpoint to get recent tasks
    // For now, we'll just keep the tasks we've created
  } catch (error) {
    console.error('Failed to load tasks:', error)
  }
}

async function pollTaskStatus(taskId) {
  try {
    const response = await api.getTask(taskId)
    const taskData = response.data

    // Update task in our list
    const taskIndex = tasks.value.findIndex(t => t.id === taskId)
    if (taskIndex !== -1) {
      tasks.value[taskIndex] = { ...tasks.value[taskIndex], ...taskData }
    }

    // If task is still running, continue polling
    if (taskData.status === 'running') {
      setTimeout(() => pollTaskStatus(taskId), 2000)
    } else {
      // Task finished, reload stats
      await loadStats()
      if (taskData.status === 'done') {
        toast('Задача выполнена успешно', 'success')
      } else if (taskData.status === 'failed') {
        toast('Задача завершилась с ошибкой', 'error')
      }
    }
  } catch (error) {
    console.error('Failed to poll task status:', error)
  }
}

function handleFileSelect(event) {
  const file = event.target.files[0]
  if (file) {
    if (file.name.endsWith('.xml') || file.name.endsWith('.yml')) {
      importFile.value = file
    } else {
      toast('Выберите файл формата XML или YML', 'error')
      event.target.value = ''
    }
  }
}

async function importYml() {
  if (!importFile.value) {
    toast('Выберите файл для импорта', 'error')
    return
  }

  try {
    uploading.value = true
    const response = await api.importYml(importFile.value)
    const taskData = response.data

    // Add task to our list
    const newTask = {
      id: taskData.task_id,
      type: 'import',
      status: taskData.status,
      created_at: new Date().toISOString(),
      description: `Импорт ${importFile.value.name}`
    }
    tasks.value.unshift(newTask)

    toast('Импорт запущен', 'info')
    importFile.value = null

    // Reset file input
    const fileInput = document.getElementById('import-file')
    if (fileInput) fileInput.value = ''

    // Start polling for this task
    pollTaskStatus(taskData.task_id)
  } catch (error) {
    console.error('Failed to import YML:', error)
    toast('Ошибка запуска импорта', 'error')
  } finally {
    uploading.value = false
  }
}

async function rebuildIndex() {
  try {
    rebuildingIndex.value = true
    const response = await api.rebuildIndex()
    const taskData = response.data

    // Add task to our list
    const newTask = {
      id: taskData.task_id,
      type: 'rebuild',
      status: taskData.status,
      created_at: new Date().toISOString(),
      description: 'Пересборка индекса'
    }
    tasks.value.unshift(newTask)

    toast('Пересборка индекса запущена', 'info')

    // Start polling for this task
    pollTaskStatus(taskData.task_id)
  } catch (error) {
    console.error('Failed to rebuild index:', error)
    toast('Ошибка запуска пересборки индекса', 'error')
  } finally {
    rebuildingIndex.value = false
  }
}

function getTaskStatusBadge(status) {
  switch (status) {
    case 'running': return { type: 'info', text: 'Выполняется' }
    case 'done': return { type: 'success', text: 'Завершено' }
    case 'failed': return { type: 'danger', text: 'Ошибка' }
    default: return { type: 'default', text: status }
  }
}

function getTaskIcon(type) {
  switch (type) {
    case 'import': return '📥'
    case 'rebuild': return '🔄'
    default: return '⚙️'
  }
}

const formatDate = (dateStr) => {
  return new Date(dateStr).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(async () => {
  loading.value = true
  await Promise.all([loadStats(), loadTasks()])
  loading.value = false
})

onUnmounted(() => {
  if (pollInterval) {
    clearInterval(pollInterval)
  }
})
</script>

<template>
  <div>
    <PageHeader title="Конвейер обработки данных" />

    <div class="content">
      <div v-if="loading" class="loading">
        <AjaxFrog text="Загрузка данных конвейера…" size="32px" />
      </div>

      <div v-else class="pipeline-layout">
        <!-- Stats section -->
        <div class="stats-section">
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-icon">📦</div>
              <div class="stat-content">
                <div class="stat-number">{{ stats.products || 0 }}</div>
                <div class="stat-label">Товары</div>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">🧩</div>
              <div class="stat-content">
                <div class="stat-number">{{ stats.chunks || 0 }}</div>
                <div class="stat-label">RAG Чанки</div>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">🔄</div>
              <div class="stat-content">
                <div class="stat-number">v{{ stats.index_versions || 0 }}</div>
                <div class="stat-label">Версия индекса</div>
              </div>
            </div>
          </div>

          <div v-if="stats.last_indexed" class="last-indexed-info">
            <span class="info-label">Последняя индексация:</span>
            <span class="info-value">{{ new Date(stats.last_indexed).toLocaleString('ru-RU') }}</span>
          </div>
        </div>

        <!-- Actions section -->
        <div class="actions-section">
          <!-- Import YML -->
          <div class="action-card">
            <div class="card-header">
              <h3 class="card-title">
                <span class="card-icon">📥</span>
                Импорт YML каталога
              </h3>
            </div>
            <div class="card-body">
              <p class="card-description">
                Загрузите файл каталога товаров в формате XML/YML для обновления базы данных.
              </p>

              <div class="file-upload">
                <input
                  id="import-file"
                  type="file"
                  accept=".xml,.yml"
                  class="file-input"
                  @change="handleFileSelect"
                />
                <label for="import-file" class="file-label">
                  <span class="file-icon">📁</span>
                  <span class="file-text">
                    {{ importFile ? importFile.name : 'Выберите XML/YML файл' }}
                  </span>
                </label>
              </div>

              <button
                class="btn btn-primary"
                :disabled="!importFile || uploading"
                @click="importYml"
              >
                {{ uploading ? 'Импорт...' : 'Запустить импорт' }}
              </button>
            </div>
          </div>

          <!-- Rebuild index -->
          <div class="action-card">
            <div class="card-header">
              <h3 class="card-title">
                <span class="card-icon">🔄</span>
                Пересборка RAG индекса
              </h3>
            </div>
            <div class="card-body">
              <p class="card-description">
                Пересоберите векторный индекс для всех текстовых фрагментов в базе данных.
              </p>

              <div class="rebuild-stats">
                <span class="rebuild-stat">
                  Чанков для индексации: <strong>{{ stats.chunks || 0 }}</strong>
                </span>
              </div>

              <button
                class="btn btn-warning"
                :disabled="rebuildingIndex"
                @click="rebuildIndex"
              >
                {{ rebuildingIndex ? 'Пересборка...' : 'Запустить пересборку' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Tasks section -->
        <div class="tasks-section">
          <h3 class="tasks-title">Статус задач</h3>

          <div v-if="tasks.length === 0" class="no-tasks">
            Активных задач нет
          </div>

          <div v-else class="tasks-list">
            <div
              v-for="task in tasks.slice(0, 10)"
              :key="task.id"
              class="task-item"
            >
              <div class="task-header">
                <div class="task-info">
                  <span class="task-icon">{{ getTaskIcon(task.type) }}</span>
                  <span class="task-description">{{ task.description }}</span>
                </div>
                <StatusBadge
                  :status="getTaskStatusBadge(task.status).text"
                  :type="getTaskStatusBadge(task.status).type"
                />
              </div>

              <div class="task-meta">
                <span class="task-id">ID: {{ task.id }}</span>
                <span class="task-time">{{ formatDate(task.created_at) }}</span>
              </div>

              <div v-if="task.output_tail" class="task-output">
                <pre class="output-text">{{ task.output_tail }}</pre>
              </div>

              <div v-if="task.status === 'running'" class="task-progress">
                <div class="progress-bar">
                  <div class="progress-indicator"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content {
  padding: var(--sp-6);
}

.loading {
  text-align: center;
  padding: var(--sp-8);
  color: var(--fg-3);
  font-size: var(--fs-14);
}

.pipeline-layout {
  max-width: 1200px;
  display: flex;
  flex-direction: column;
  gap: var(--sp-8);
}

/* Stats section */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--sp-4);
  margin-bottom: var(--sp-4);
}

.stat-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-5);
  box-shadow: var(--shadow-1);
  display: flex;
  align-items: center;
  gap: var(--sp-4);
}

.stat-icon {
  font-size: 24px;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-soft);
  border-radius: var(--rad-lg);
}

.stat-content {
  flex: 1;
}

.stat-number {
  font-size: var(--fs-24);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  line-height: var(--lh-tight);
  font-feature-settings: 'tnum';
}

.stat-label {
  font-size: var(--fs-13);
  color: var(--fg-2);
  font-weight: var(--fw-medium);
  margin-top: var(--sp-1);
}

.last-indexed-info {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-3);
  background: var(--bg-panel-2);
  border-radius: var(--rad-md);
  border: 1px solid var(--border-2);
}

.info-label {
  font-size: var(--fs-13);
  color: var(--fg-2);
  font-weight: var(--fw-medium);
}

.info-value {
  font-size: var(--fs-13);
  color: var(--fg-1);
  font-family: var(--font-mono);
}

/* Actions section */
.actions-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-6);
}

.action-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  box-shadow: var(--shadow-1);
  overflow: hidden;
}

.card-header {
  padding: var(--sp-5) var(--sp-5) var(--sp-3);
  border-bottom: 1px solid var(--border-2);
}

.card-title {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-16);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0;
}

.card-icon {
  font-size: 20px;
}

.card-body {
  padding: var(--sp-5);
}

.card-description {
  font-size: var(--fs-14);
  color: var(--fg-2);
  line-height: var(--lh-normal);
  margin: 0 0 var(--sp-4) 0;
}

/* File upload */
.file-upload {
  margin-bottom: var(--sp-4);
}

.file-input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.file-label {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-4);
  background: var(--bg-panel-2);
  border: 2px dashed var(--border-1);
  border-radius: var(--rad-lg);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}

.file-label:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.file-icon {
  font-size: 18px;
  color: var(--fg-3);
}

.file-text {
  font-size: var(--fs-14);
  color: var(--fg-1);
  font-weight: var(--fw-medium);
}

.rebuild-stats {
  margin-bottom: var(--sp-4);
  padding: var(--sp-3);
  background: var(--bg-panel-2);
  border-radius: var(--rad-md);
  border: 1px solid var(--border-2);
}

.rebuild-stat {
  font-size: var(--fs-13);
  color: var(--fg-2);
}

/* Tasks section */
.tasks-title {
  font-size: var(--fs-18);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0 0 var(--sp-5) 0;
}

.no-tasks {
  text-align: center;
  padding: var(--sp-8);
  color: var(--fg-3);
  font-size: var(--fs-14);
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
}

.tasks-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.task-item {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-4);
  box-shadow: var(--shadow-1);
}

.task-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-3);
}

.task-info {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.task-icon {
  font-size: 18px;
}

.task-description {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  color: var(--fg-1);
}

.task-meta {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  margin-bottom: var(--sp-3);
}

.task-id,
.task-time {
  font-size: var(--fs-12);
  color: var(--fg-3);
  font-family: var(--font-mono);
}

.task-output {
  background: var(--bg-panel-2);
  border: 1px solid var(--border-2);
  border-radius: var(--rad-md);
  padding: var(--sp-3);
  margin-bottom: var(--sp-3);
}

.output-text {
  font-family: var(--font-mono);
  font-size: var(--fs-12);
  color: var(--fg-1);
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  max-height: 120px;
  overflow-y: auto;
}

.task-progress {
  margin-top: var(--sp-3);
}

.progress-bar {
  height: 4px;
  background: var(--bg-panel-2);
  border-radius: var(--rad-pill);
  overflow: hidden;
}

.progress-indicator {
  height: 100%;
  width: 100%;
  background: linear-gradient(90deg, var(--accent) 0%, var(--accent-hover) 50%, var(--accent) 100%);
  background-size: 200% 100%;
  animation: progressSlide 2s ease-in-out infinite;
}

@keyframes progressSlide {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.btn {
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--rad-md);
  border: 1px solid;
  font: inherit;
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--fg-on-accent);
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}

.btn-warning {
  background: var(--warning);
  border-color: var(--warning);
  color: var(--fg-on-accent);
}

.btn-warning:hover:not(:disabled) {
  background: var(--ark-yellow-600);
  border-color: var(--ark-yellow-600);
}
</style>