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
  getEvalDataset: () => client.get('/eval/dataset'),
  runEvalDataset: (note = null) => client.post('/eval/run', null, { params: note ? { note } : {} }),
  getEvalRuns: () => client.get('/eval/runs'),
  getEvalRun: (id) => client.get(`/eval/runs/${id}`),
  getEvalRunProgress: (id) => client.get(`/eval/runs/${id}/progress`),
  getEvalAnswer: (runId, questionId) => client.get(`/eval/runs/${runId}/results/${questionId}/answer`),
  compareEvalRuns: (id_a, id_b) => client.get(`/eval/runs/${id_a}/compare/${id_b}`),
  deleteEvalRun: (id) => client.delete(`/eval/runs/${id}`),
}

export default client