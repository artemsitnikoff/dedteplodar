<script setup>
import { ref, nextTick } from 'vue'
import ChatMessage from '@/components/ChatMessage.vue'
import { sendChatStream } from '@/api/index.js'
import { getSessionId, resetSession } from '@/utils/chatSession.js'

const messages = ref([])
const input = ref('')
const sending = ref(false)
const scrollRef = ref(null)
const taRef = ref(null)

let sessionId = getSessionId()
let idc = 0
const nextId = () => ++idc

const EXAMPLES = [
  'Какие банные печи есть на парилку 12 м³?',
  'Чем печь Русь отличается от Сахары?',
  'Сколько стоит доставка до Красноярска?',
  'Есть ли магазины в Новосибирске?',
]

async function scrollToBottom() {
  await nextTick()
  const el = scrollRef.value
  if (el) el.scrollTop = el.scrollHeight
}

function autoGrow() {
  const el = taRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

function resetTextarea() {
  const el = taRef.value
  if (el) el.style.height = 'auto'
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return

  // Last few completed turns (oldest first) for anaphora resolution.
  const history = messages.value
    .filter((m) => !m.pending && m.content && !m.isError)
    .slice(-6)
    .map((m) => ({ role: m.role, content: m.content }))

  input.value = ''
  resetTextarea()
  messages.value.push({ id: nextId(), role: 'user', content: text })

  const pendingId = nextId()
  messages.value.push({ id: pendingId, role: 'assistant', content: '', pending: true, phase: 'intent' })
  sending.value = true
  scrollToBottom()

  const patch = (fields) => {
    const m = messages.value.find((x) => x.id === pendingId)
    if (m) Object.assign(m, fields)
  }

  await sendChatStream(
    { message: text, session_id: sessionId, history },
    {
      onPhase: (phase) => { patch({ phase }); scrollToBottom() },
      onDone: (ev) => {
        patch({
          pending: false,
          content: ev.answer_html || '',
          meta: ev.meta || null,
          logId: ev.log_id || null,
        })
        sending.value = false
        scrollToBottom()
      },
      onError: (err) => {
        patch({
          pending: false,
          isError: true,
          content: (err && err.message) ||
            'Извините, не удалось получить ответ. Попробуйте ещё раз.',
        })
        sending.value = false
        scrollToBottom()
      },
    },
  )
}

function useExample(q) {
  input.value = q
  send()
}

function newChat() {
  if (sending.value) return
  messages.value = []
  sessionId = resetSession()
  input.value = ''
  resetTextarea()
}
</script>

<template>
  <div class="chat">
    <!-- Header -->
    <header class="chat-header">
      <div class="brand">
        <span class="brand-emoji">🔥</span>
        <span class="brand-text">Теплодар — Консультант</span>
      </div>
      <button class="new-chat" :disabled="sending || messages.length === 0" @click="newChat">
        + Новый диалог
      </button>
    </header>

    <!-- Messages -->
    <div ref="scrollRef" class="chat-scroll">
      <div class="chat-inner">
        <!-- Empty state -->
        <div v-if="messages.length === 0" class="empty">
          <div class="empty-emoji">🔥</div>
          <h1 class="empty-title">Чем помочь?</h1>
          <p class="empty-sub">
            Спрашивайте про печи, котлы, бани «Теплодар» — подбор по параметрам,
            характеристики, цены, доставку и магазины.
          </p>
          <div class="examples">
            <button v-for="ex in EXAMPLES" :key="ex" class="example" @click="useExample(ex)">
              {{ ex }}
            </button>
          </div>
        </div>

        <ChatMessage v-for="m in messages" :key="m.id" :message="m" />
      </div>
    </div>

    <!-- Input -->
    <div class="chat-input-bar">
      <div class="chat-input-inner">
        <div class="input-wrap">
          <textarea
            ref="taRef"
            v-model="input"
            class="chat-textarea"
            rows="1"
            placeholder="Спросите о продукции Теплодар…"
            @input="autoGrow"
            @keydown.enter.exact.prevent="send"
          ></textarea>
          <button class="send-btn" :disabled="sending || !input.trim()" title="Отправить" @click="send">
            <span v-if="!sending">➤</span>
            <span v-else class="spin">⏳</span>
          </button>
        </div>
        <div class="input-hint">Enter — отправить · Shift+Enter — новая строка</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-app);
}

/* Header */
.chat-header {
  flex-shrink: 0;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--sp-5);
  border-bottom: 1px solid var(--border-1);
  background: var(--bg-panel);
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-16);
  font-weight: var(--fw-bold);
  letter-spacing: var(--ls-tight);
}
.brand-emoji { font-size: 18px; }
.new-chat {
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-md);
  padding: 6px 12px;
  font: inherit;
  font-size: var(--fs-13);
  font-weight: var(--fw-medium);
  color: var(--fg-1);
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out);
}
.new-chat:hover:not(:disabled) { background: var(--bg-hover); }
.new-chat:disabled { opacity: 0.45; cursor: not-allowed; }

/* Scroll area */
.chat-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.chat-inner {
  max-width: 760px;
  margin: 0 auto;
  padding: var(--sp-6) var(--sp-4) var(--sp-8);
}

/* Empty state */
.empty {
  text-align: center;
  padding: var(--sp-12) var(--sp-2) var(--sp-6);
  display: flex;
  flex-direction: column;
  align-items: center;
}
.empty-emoji { font-size: 44px; margin-bottom: var(--sp-3); }
.empty-title {
  margin: 0 0 var(--sp-2);
  font-size: var(--fs-24);
  font-weight: var(--fw-bold);
  color: var(--fg-1);
}
.empty-sub {
  margin: 0 0 var(--sp-6);
  max-width: 460px;
  color: var(--fg-2);
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
}
.examples {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  width: 100%;
  max-width: 440px;
}
.example {
  text-align: left;
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-lg);
  padding: var(--sp-3) var(--sp-4);
  font: inherit;
  font-size: var(--fs-14);
  color: var(--fg-1);
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out);
}
.example:hover { background: var(--bg-hover); border-color: var(--border-strong); }

/* Input bar */
.chat-input-bar {
  flex-shrink: 0;
  border-top: 1px solid var(--border-1);
  background: var(--bg-app);
}
.chat-input-inner {
  max-width: 760px;
  margin: 0 auto;
  padding: var(--sp-3) var(--sp-4) var(--sp-4);
}
.input-wrap {
  display: flex;
  align-items: flex-end;
  gap: var(--sp-2);
  background: var(--bg-elevated);
  border: 1px solid var(--border-1);
  border-radius: var(--rad-xl);
  padding: var(--sp-2) var(--sp-2) var(--sp-2) var(--sp-4);
  box-shadow: var(--shadow-1);
}
.input-wrap:focus-within { border-color: var(--border-focus); box-shadow: var(--shadow-focus); }
.chat-textarea {
  flex: 1;
  border: 0;
  outline: none;
  resize: none;
  background: transparent;
  font: inherit;
  font-size: var(--fs-15);
  line-height: var(--lh-normal);
  color: var(--fg-1);
  max-height: 200px;
  padding: 6px 0;
}
.send-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 15px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--dur-fast) var(--ease-out), opacity var(--dur-fast) var(--ease-out);
}
.send-btn:hover:not(:disabled) { background: var(--accent-hover); }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.spin { animation: spin 1.4s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.input-hint {
  margin-top: 6px;
  text-align: center;
  font-size: var(--fs-11);
  color: var(--fg-3);
}
</style>
