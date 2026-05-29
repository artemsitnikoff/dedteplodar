import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json'
  },
})

// Counter of in-flight requests (kept for any future global indicator)
let activeRequests = 0

const SLOW_MS = 800
const VERY_SLOW_MS = 2500

client.interceptors.request.use((config) => {
  activeRequests++
  config.metadata = { startedAt: performance.now() }
  if (import.meta.env.DEV) console.log(`[api] → ${config.method?.toUpperCase()} ${config.url}`)
  return config
})

function logResponse(config, status, label = '') {
  const ms = Math.round(performance.now() - (config?.metadata?.startedAt ?? performance.now()))
  const tag = `[api]${label}`
  const line = `${tag} ← ${status} ${config?.method?.toUpperCase() ?? '?'} ${config?.url ?? '?'}  ${ms}ms`
  if (import.meta.env.DEV) {
    if (ms >= VERY_SLOW_MS) console.error(line + '  ⚠ VERY SLOW')
    else if (ms >= SLOW_MS) console.warn(line + '  ⚠ slow')
    else console.log(line)
  }
}

client.interceptors.response.use(
  (resp) => {
    if (activeRequests > 0) activeRequests--
    logResponse(resp.config, resp.status)
    return resp
  },
  (err) => {
    if (activeRequests > 0) activeRequests--
    const status = err.response?.status ?? 'ERR'
    logResponse(err.config, status, ' FAIL')
    return Promise.reject(err)
  }
)

// API endpoints
export const api = {
  // Pipeline
  getPipelineStats: () => client.get('/pipeline/stats'),
  importYml: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return client.post('/pipeline/import-yml', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  rebuildIndex: () => client.post('/pipeline/rebuild-index'),
  getTask: (taskId) => client.get(`/pipeline/tasks/${taskId}`),

  // Categories
  getCategoriesTree: () => client.get('/categories/tree'),

  // Products
  getProducts: (params = {}) => client.get('/products', { params }),
  getProduct: (id) => client.get(`/products/${id}`),
  getProductDocuments: (id, params = {}) => client.get(`/products/${id}/documents`, { params }),
  updateProduct: (id, data) => client.patch(`/products/${id}`, data),
  deleteProduct: (id) => client.delete(`/products/${id}`),

  // Documents
  getDocuments: (params = {}) => client.get('/documents', { params }),
  getDocumentText: (id) => client.get(`/documents/${id}/text`),
  deleteDocument: (id) => client.delete(`/documents/${id}`),
  uploadDocument: (file, productId = null) => {
    const formData = new FormData()
    formData.append('file', file)
    if (productId) formData.append('product_id', productId)
    return client.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  // Chunks
  getChunks: (params = {}) => client.get('/chunks', { params }),
  getChunk: (id) => client.get(`/chunks/${id}`),
  deleteChunk: (id) => client.delete(`/chunks/${id}`),

  // Journal
  getJournal: (params = {}) => client.get('/journal', { params }),
  getJournalContext: (id) => client.get(`/journal/${id}/context`),

  // Synonyms (fuzzy-match dictionary)
  getSynonyms: (params = {}) => client.get('/synonyms', { params }),
  createSynonym: (payload) => client.post('/synonyms', payload),
  updateSynonym: (id, payload) => client.put(`/synonyms/${id}`, payload),
  deleteSynonym: (id) => client.delete(`/synonyms/${id}`),
  reloadSynonyms: () => client.post('/synonyms/reload'),

  // FAQ Entries
  getFaqEntries: (params = {}) => client.get('/faq-entries', { params }),
  createFaqEntry: (data) => client.post('/faq-entries', data),
  updateFaqEntry: (id, data) => client.patch(`/faq-entries/${id}`, data),
  deleteFaqEntry: (id) => client.delete(`/faq-entries/${id}`),

  // FAQ
  getFaqCompany: () => client.get('/faq/company'),
  updateFaqCompany: (content) => client.put('/faq/company', { content }),
  getFaqDealers: () => client.get('/faq/dealers'),
  updateFaqDealers: (content) => client.put('/faq/dealers', { content }),

  // Eval
  getEvalDataset: (name = 'synthetic') => client.get('/eval/dataset', { params: { name } }),
  runEvalDataset: (note = null, dataset = 'synthetic') => {
    const params = { dataset }
    if (note) params.note = note
    return client.post('/eval/run', null, { params })
  },
  getEvalRuns: () => client.get('/eval/runs'),
  getEvalRun: (id) => client.get(`/eval/runs/${id}`),
  getEvalRunProgress: (id) => client.get(`/eval/runs/${id}/progress`),
  getEvalAnswer: (runId, questionId) => client.get(`/eval/runs/${runId}/results/${questionId}/answer`),
  compareEvalRuns: (id_a, id_b) => client.get(`/eval/runs/${id_a}/compare/${id_b}`),
  deleteEvalRun: (id) => client.delete(`/eval/runs/${id}`),

  // Chat (web consultant)
  sendChatFeedback: (payload) => client.post('/chat/feedback', payload),
}

// Streaming chat — native fetch + ReadableStream. axios doesn't surface a
// streaming body in the browser, and we need a POST body (so EventSource is
// out). Same-origin request → the browser attaches the cached basic-auth
// credentials automatically. Callbacks: onPhase(name), onDone(event),
// onError(err). Pass an AbortSignal to cancel.
export async function sendChatStream({ message, session_id, history }, { onPhase, onDone, onError, signal } = {}) {
  try {
    const resp = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id, history }),
      signal,
    })
    if (!resp.ok || !resp.body) {
      onError?.(new Error(`HTTP ${resp.status}`))
      return
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // SSE frames are separated by a blank line.
      let sep
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        const dataLine = frame.split('\n').find((l) => l.startsWith('data:'))
        if (!dataLine) continue
        const payload = dataLine.slice(5).trim()
        if (!payload) continue
        let ev
        try { ev = JSON.parse(payload) } catch { continue }
        if (ev.type === 'phase') onPhase?.(ev.phase)
        else if (ev.type === 'done') onDone?.(ev)
        else if (ev.type === 'error') onError?.(new Error(ev.message || 'stream error'), ev)
      }
    }
  } catch (e) {
    if (e?.name === 'AbortError') return
    onError?.(e)
  }
}

export default client