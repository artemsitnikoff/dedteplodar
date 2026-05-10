import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import '@/assets/tokens.css'

// Views
import DashboardView from '@/views/DashboardView.vue'
import ProductsView from '@/views/ProductsView.vue'
import ProductEditView from '@/views/ProductEditView.vue'
import CategoriesView from '@/views/CategoriesView.vue'
import DocumentsView from '@/views/DocumentsView.vue'
import ChunksView from '@/views/ChunksView.vue'
import FaqView from '@/views/FaqView.vue'
import PipelineView from '@/views/PipelineView.vue'
import JournalView from '@/views/JournalView.vue'
import FaqEntriesView from '@/views/FaqEntriesView.vue'

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