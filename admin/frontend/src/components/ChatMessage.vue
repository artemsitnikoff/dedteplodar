<script setup>
import { ref, computed, inject } from 'vue'
import { api } from '@/api/index.js'
import { sanitizeAnswer } from '@/utils/sanitizeHtml.js'

const props = defineProps({
  message: { type: Object, required: true },
})

const toast = inject('toast', () => {})

const isUser = computed(() => props.message.role === 'user')
const html = computed(() => sanitizeAnswer(props.message.content || ''))

// ── phase indicator (while pending) ──────────────────────────────────
const PHASE_LABELS = {
  intent: 'Понимаю вопрос…',
  retrieval: 'Ищу в базе знаний…',
  answer: 'Формулирую ответ…',
}
const phaseLabel = computed(() => PHASE_LABELS[props.message.phase] || 'Печатаю…')

// ── meta chip ────────────────────────────────────────────────────────
const meta = computed(() => props.message.meta || null)
const TYPE_LABELS = {
  RAG_PRODUCT: 'Каталог',
  FAQ_COMPANY: 'О компании',
  FAQ_DEALER: 'Дилеры',
  FAQ_EXACT: 'FAQ',
}
const typeLabel = computed(() => TYPE_LABELS[meta.value?.query_type] || meta.value?.query_type || '')
const scoreClass = computed(() => {
  const s = meta.value?.top_score
  if (s == null) return ''
  if (s >= 0.85) return 'score-green'
  if (s >= 0.8) return 'score-yellow'
  return 'score-red'
})

// ── feedback ─────────────────────────────────────────────────────────
const feedback = ref(props.message.feedback || null)
const showNote = ref(false)
const noteText = ref('')
const done = ref(false)        // note submitted or skipped
const sending = ref(false)

async function rate(kind) {
  if (!props.message.logId || sending.value) return
  feedback.value = kind
  try {
    await api.sendChatFeedback({ log_id: props.message.logId, feedback: kind })
  } catch {
    toast('Не удалось сохранить оценку', 'error')
  }
  if (kind === 'bad') {
    showNote.value = true
  } else {
    done.value = true
  }
}

async function submitNote() {
  if (sending.value) return
  sending.value = true
  try {
    await api.sendChatFeedback({
      log_id: props.message.logId,
      feedback: 'bad',
      note: noteText.value.trim() || null,
    })
    done.value = true
    showNote.value = false
  } catch {
    toast('Не удалось отправить', 'error')
  } finally {
    sending.value = false
  }
}

function skipNote() {
  showNote.value = false
  done.value = true
}
</script>

<template>
  <div :class="['msg', isUser ? 'msg-user' : 'msg-assistant']">
    <!-- User -->
    <div v-if="isUser" class="bubble-user">{{ message.content }}</div>

    <!-- Assistant -->
    <div v-else class="assistant-block">
      <!-- typing / phases -->
      <div v-if="message.pending" class="typing">
        <span class="dots"><span /><span /><span /></span>
        <span class="phase">{{ phaseLabel }}</span>
      </div>

      <template v-else>
        <div class="answer" v-html="html"></div>

        <!-- meta chip (experts: see RAG confidence) -->
        <div v-if="meta" class="meta-chip">
          <span class="meta-type">{{ typeLabel }}</span>
          <span v-if="meta.top_score != null" :class="['meta-score', scoreClass]">
            score {{ meta.top_score.toFixed(2) }}
          </span>
          <span v-if="meta.chunks_used">· {{ meta.chunks_used }} фрагм.</span>
          <span v-if="meta.latency_ms">· {{ (meta.latency_ms / 1000).toFixed(1) }}с</span>
          <span v-if="meta.t_answer_model">· {{ meta.t_answer_model }}</span>
        </div>

        <!-- feedback -->
        <div v-if="message.logId" class="fb-row">
          <template v-if="!done">
            <button :class="['fb-btn', { active: feedback === 'good' }]" title="Полезно" @click="rate('good')">👍</button>
            <button :class="['fb-btn', { active: feedback === 'bad' }]" title="Не то" @click="rate('bad')">👎</button>
          </template>
          <span v-else class="fb-thanks">Спасибо за оценку!</span>
        </div>

        <!-- "что не так" note box on 👎 -->
        <div v-if="showNote" class="note-box">
          <div class="note-label">Что не так с ответом? Что нужно было ответить?</div>
          <textarea v-model="noteText" rows="3" placeholder="Можно одним сообщением…"></textarea>
          <div class="note-actions">
            <button class="btn btn-secondary" @click="skipNote">Пропустить</button>
            <button class="btn btn-primary" :disabled="sending" @click="submitNote">
              {{ sending ? 'Отправляю…' : 'Отправить' }}
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.msg {
  display: flex;
  margin-bottom: var(--sp-5);
}
.msg-user {
  justify-content: flex-end;
}
.msg-assistant {
  justify-content: flex-start;
}

.bubble-user {
  background: var(--accent-soft);
  color: var(--fg-1);
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--rad-xl);
  border-bottom-right-radius: var(--rad-sm);
  max-width: 80%;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: var(--fs-15);
  line-height: var(--lh-normal);
}

.assistant-block {
  max-width: 100%;
  width: 100%;
}

.answer {
  font-size: var(--fs-15);
  line-height: var(--lh-relaxed);
  color: var(--fg-1);
  white-space: pre-wrap;
  word-wrap: break-word;
}
.answer :deep(b) { font-weight: var(--fw-semibold); }
.answer :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.9em;
  background: var(--ark-gray-100);
  padding: 1px 5px;
  border-radius: var(--rad-sm);
}
.answer :deep(a) { color: var(--fg-link); text-decoration: none; }
.answer :deep(a:hover) { text-decoration: underline; }

/* typing dots */
.typing {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  color: var(--fg-3);
  font-size: var(--fs-14);
}
.dots {
  display: inline-flex;
  gap: 4px;
}
.dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--fg-3);
  animation: blink 1.4s infinite both;
}
.dots span:nth-child(2) { animation-delay: 0.2s; }
.dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 80%, 100% { opacity: 0.25; }
  40% { opacity: 1; }
}
.phase { font-style: italic; }

/* meta chip */
.meta-chip {
  margin-top: var(--sp-3);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-11);
  color: var(--fg-3);
  font-variant-numeric: tabular-nums;
}
.meta-type {
  background: var(--bg-panel-2);
  color: var(--fg-2);
  padding: 1px 7px;
  border-radius: var(--rad-sm);
  font-weight: var(--fw-semibold);
}
.meta-score { font-weight: var(--fw-semibold); }
.score-green { color: var(--ark-green-600); }
.score-yellow { color: var(--ark-yellow-600); }
.score-red { color: var(--ark-red-600); }

/* feedback */
.fb-row {
  margin-top: var(--sp-2);
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  min-height: 28px;
}
.fb-btn {
  background: transparent;
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  padding: 2px 8px;
  font-size: 14px;
  cursor: pointer;
  line-height: 1.4;
  transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out);
}
.fb-btn:hover { background: var(--bg-hover); }
.fb-btn.active { background: var(--accent-soft); border-color: var(--accent); }
.fb-thanks { font-size: var(--fs-12); color: var(--fg-3); }

/* note box */
.note-box {
  margin-top: var(--sp-3);
  background: var(--bg-panel-2);
  border: 1px solid var(--border-2);
  border-radius: var(--rad-lg);
  padding: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  max-width: 520px;
}
.note-label { font-size: var(--fs-12); color: var(--fg-2); font-weight: var(--fw-medium); }
.note-box textarea {
  resize: vertical;
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  padding: 8px 10px;
  font: inherit;
  font-size: var(--fs-14);
  color: var(--fg-1);
  background: var(--bg-elevated);
}
.note-box textarea:focus { outline: none; border-color: var(--border-focus); box-shadow: var(--shadow-focus); }
.note-actions { display: flex; justify-content: flex-end; gap: var(--sp-2); }
.btn {
  padding: 6px 14px;
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  background: var(--bg-panel);
  color: var(--fg-1);
  font: inherit;
  font-size: var(--fs-13);
  cursor: pointer;
}
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-secondary { background: var(--bg-panel-2); }
</style>
