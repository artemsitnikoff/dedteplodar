<script setup>
import { ref, computed, onMounted, inject, watch } from 'vue'
import { api } from '@/api'
import PageHeader from '@/components/PageHeader.vue'

const props = defineProps({
  type: {
    type: String,
    required: true,
    validator: (value) => ['company', 'dealers'].includes(value)
  }
})

const toast = inject('toast')

const content = ref('')
const originalContent = ref('')
const loading = ref(true)
const saving = ref(false)

const isDirty = computed(() => content.value !== originalContent.value)

const title = computed(() => {
  return props.type === 'company' ? 'О компании' : 'Дилеры'
})

const description = computed(() => {
  return props.type === 'company'
    ? 'Информация о компании в формате YAML'
    : 'Справочник дилеров в формате YAML'
})

async function loadFaq() {
  try {
    loading.value = true
    const response = props.type === 'company'
      ? await api.getFaqCompany()
      : await api.getFaqDealers()

    content.value = response.data.content || ''
    originalContent.value = content.value
  } catch (error) {
    console.error('Failed to load FAQ:', error)
    toast('Ошибка загрузки данных', 'error')
  } finally {
    loading.value = false
  }
}

async function saveFaq() {
  try {
    saving.value = true

    if (props.type === 'company') {
      await api.updateFaqCompany(content.value)
    } else {
      await api.updateFaqDealers(content.value)
    }

    originalContent.value = content.value
    toast('Данные сохранены', 'success')
  } catch (error) {
    console.error('Failed to save FAQ:', error)
    toast('Ошибка сохранения данных', 'error')
  } finally {
    saving.value = false
  }
}

function handleKeyDown(event) {
  // Handle Tab key for indentation
  if (event.key === 'Tab') {
    event.preventDefault()
    const start = event.target.selectionStart
    const end = event.target.selectionEnd

    // Insert 2 spaces at cursor position
    content.value = content.value.substring(0, start) + '  ' + content.value.substring(end)

    // Move cursor after the inserted spaces
    event.target.setSelectionRange(start + 2, start + 2)
  }
}

// Load data when component mounts or type changes
watch(() => props.type, loadFaq, { immediate: true })
</script>

<template>
  <div>
    <PageHeader :title="title">
      <template #actions>
        <div class="header-actions">
          <div v-if="isDirty" class="unsaved-indicator">
            Несохраненные изменения
          </div>
          <button
            class="btn btn-primary"
            :disabled="saving || !isDirty"
            @click="saveFaq"
          >
            {{ saving ? 'Сохранение...' : 'Сохранить' }}
          </button>
        </div>
      </template>
    </PageHeader>

    <div class="content">
      <div v-if="loading" class="loading">
        Загрузка данных...
      </div>

      <div v-else class="editor-container">
        <div class="editor-header">
          <h3 class="editor-title">{{ description }}</h3>
          <div class="editor-tips">
            <p class="tip">
              <strong>Совет:</strong> Используйте правильный YAML синтаксис.
              Для отступов используйте пробелы, не табы.
            </p>
            <p class="tip">
              Нажмите <kbd>Tab</kbd> для добавления отступа (2 пробела).
            </p>
          </div>
        </div>

        <div class="editor-wrapper">
          <textarea
            v-model="content"
            class="yaml-editor"
            :placeholder="type === 'company' ? companyPlaceholder : dealersPlaceholder"
            spellcheck="false"
            @keydown="handleKeyDown"
          />
        </div>

        <div class="editor-footer">
          <div class="stats">
            Строк: {{ content.split('\n').length }} |
            Символов: {{ content.length }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      companyPlaceholder: `# Информация о компании Теплодар
name: "Теплодар"
description: "Производитель отопительного оборудования"
founded: 2000
location: "Новосибирск, Россия"
website: "https://teplodar.ru"
contact:
  phone: "+7 (383) 000-00-00"
  email: "info@teplodar.ru"
  address: "г. Новосибирск, ул. Промышленная, 1"
`,
      dealersPlaceholder: `# Справочник дилеров Теплодар
dealers:
  - name: "Дилер 1"
    city: "Москва"
    region: "Московская область"
    contact:
      phone: "+7 (495) 000-00-00"
      email: "moscow@dealer1.ru"
      address: "г. Москва, ул. Строительная, 10"

  - name: "Дилер 2"
    city: "Санкт-Петербург"
    region: "Ленинградская область"
    contact:
      phone: "+7 (812) 000-00-00"
      email: "spb@dealer2.ru"
      address: "г. СПб, пр. Невский, 100"
`
    }
  }
}
</script>

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

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.unsaved-indicator {
  font-size: var(--fs-13);
  color: var(--warning);
  font-weight: var(--fw-medium);
}

.editor-container {
  max-width: 1000px;
}

.editor-header {
  margin-bottom: var(--sp-5);
}

.editor-title {
  font-size: var(--fs-18);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0 0 var(--sp-3) 0;
}

.editor-tips {
  background: var(--bg-panel-2);
  border: 1px solid var(--border-2);
  border-radius: var(--rad-lg);
  padding: var(--sp-4);
}

.tip {
  font-size: var(--fs-13);
  color: var(--fg-2);
  margin: 0 0 var(--sp-2) 0;
  line-height: var(--lh-normal);
}

.tip:last-child {
  margin-bottom: 0;
}

kbd {
  display: inline-block;
  padding: 2px 6px;
  font-family: var(--font-mono);
  font-size: var(--fs-11);
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-sm);
  box-shadow: 0 1px 1px rgba(0, 0, 0, 0.1);
}

.editor-wrapper {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  overflow: hidden;
  box-shadow: var(--shadow-1);
}

.yaml-editor {
  width: 100%;
  height: 500px;
  padding: var(--sp-4);
  border: none;
  background: var(--bg-elevated);
  font-family: var(--font-mono);
  font-size: var(--fs-14);
  line-height: var(--lh-relaxed);
  color: var(--fg-1);
  resize: vertical;
  outline: none;
  tab-size: 2;
}

.yaml-editor::placeholder {
  color: var(--fg-3);
  font-style: italic;
}

.yaml-editor:focus {
  background: var(--bg-elevated);
}

.editor-footer {
  margin-top: var(--sp-3);
  display: flex;
  justify-content: flex-end;
}

.stats {
  font-size: var(--fs-12);
  color: var(--fg-3);
  font-family: var(--font-mono);
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
</style>