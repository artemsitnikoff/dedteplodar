import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import '@/assets/tokens.css'
import '@/assets/badges.css'
import '@/assets/scores.css'

// Lazy-loaded views for better performance
const ChatView = () => import('@/views/ChatView.vue')
const DashboardView = () => import('@/views/DashboardView.vue')
const ProductsView = () => import('@/views/ProductsView.vue')
const ProductEditView = () => import('@/views/ProductEditView.vue')
const CategoriesView = () => import('@/views/CategoriesView.vue')
const DocumentsView = () => import('@/views/DocumentsView.vue')
const ChunksView = () => import('@/views/ChunksView.vue')
const FaqView = () => import('@/views/FaqView.vue')
const PipelineView = () => import('@/views/PipelineView.vue')
const JournalView = () => import('@/views/JournalView.vue')
const FaqEntriesView = () => import('@/views/FaqEntriesView.vue')

// Route names are unchanged from before the /admin move, so every
// router.push({ name }) in the app keeps working — only paths shifted.
const routes = [
  // Web chat — main entry for the client's experts (no admin shell).
  { path: '/', name: 'chat', component: ChatView, meta: { layout: 'chat' } },

  // Admin — knowledge-base management, now under /admin.
  { path: '/admin', name: 'dashboard', component: DashboardView, meta: { layout: 'admin' } },
  { path: '/admin/products', name: 'products', component: ProductsView, meta: { layout: 'admin' } },
  { path: '/admin/products/:id', name: 'product-edit', component: ProductEditView, props: true, meta: { layout: 'admin' } },
  { path: '/admin/categories', name: 'categories', component: CategoriesView, meta: { layout: 'admin' } },
  { path: '/admin/documents', name: 'documents', component: DocumentsView, meta: { layout: 'admin' } },
  { path: '/admin/chunks', name: 'chunks', component: ChunksView, meta: { layout: 'admin' } },
  { path: '/admin/faq/company', name: 'faq-company', component: FaqView, props: { type: 'company' }, meta: { layout: 'admin' } },
  { path: '/admin/faq/dealers', name: 'faq-dealers', component: FaqView, props: { type: 'dealers' }, meta: { layout: 'admin' } },
  { path: '/admin/pipeline', name: 'pipeline', component: PipelineView, meta: { layout: 'admin' } },
  { path: '/admin/journal', name: 'journal', component: JournalView, meta: { layout: 'admin' } },
  { path: '/admin/faq-entries', name: 'faq-entries', component: FaqEntriesView, meta: { layout: 'admin' } },
  { path: '/admin/eval', name: 'eval', component: () => import('@/views/EvalView.vue'), meta: { layout: 'admin' } },
  { path: '/admin/synonyms', name: 'synonyms', component: () => import('@/views/SynonymsView.vue'), meta: { layout: 'admin' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

const app = createApp(App)
app.use(router)
app.mount('#app')