/**
 * Shared badge helpers for eval / journal categories and query types.
 * Single source of truth — keep aligned with the CSS classes in the
 * consumer SFCs.
 */

const CAT_CLASSES = {
  'подбор': 'cat-selection',
  'характеристики': 'cat-specs',
  'установка': 'cat-install',
  'компания': 'cat-company',
  'дилер': 'cat-dealer',
}

const QTYPE_CLASSES = {
  RAG_PRODUCT: 'qt-rag',
  FAQ_COMPANY: 'qt-ref',
  FAQ_DEALER: 'qt-dealer',
  FAQ_EXACT: 'qt-faq',
  ERROR: 'qt-error',
}

const QTYPE_LABELS = {
  RAG_PRODUCT: 'RAG',
  FAQ_COMPANY: 'О компании',
  FAQ_DEALER: 'Дилер',
  FAQ_EXACT: 'FAQ',
  ERROR: 'Ошибка',
}

export function categoryBadgeClass(category) {
  return CAT_CLASSES[category] || ''
}

export function qtypeCls(qtype) {
  return QTYPE_CLASSES[qtype] || ''
}

export function qtypeLabel(qtype) {
  return QTYPE_LABELS[qtype] || qtype || '—'
}
