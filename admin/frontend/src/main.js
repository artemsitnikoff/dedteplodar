import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import '@/assets/tokens.css'

// Lazy-loaded views for better performance
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

const routes = [
  { path: '/', name: 'dashboard', component: DashboardView },
  { path: '/products', name: 'products', component: ProductsView },
  { path: '/products/:id', name: 'product-edit', component: ProductEditView, props: true },
  { path: '/categories', name: 'categories', component: CategoriesView },
  { path: '/documents', name: 'documents', component: DocumentsView },
  { path: '/chunks', name: 'chunks', component: ChunksView },
  { path: '/faq/company', name: 'faq-company', component: FaqView, props: { type: 'company' } },
  { path: '/faq/dealers', name: 'faq-dealers', component: FaqView, props: { type: 'dealers' } },
  { path: '/pipeline', name: 'pipeline', component: PipelineView },
  { path: '/journal', name: 'journal', component: JournalView },
  { path: '/faq-entries', name: 'faq-entries', component: FaqEntriesView },
  { path: '/eval', name: 'eval', component: () => import('@/views/EvalView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

const app = createApp(App)
app.use(router)
app.mount('#app')