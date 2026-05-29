// Stable per-browser chat session id, persisted in localStorage.
// Maps server-side to a synthetic user_id so a session's turns group
// together in the admin Journal. "Новый диалог" rotates it.

const KEY = 'teplodar_chat_session_id'

function uuid() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  // Fallback for older browsers.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export function getSessionId() {
  let id = localStorage.getItem(KEY)
  if (!id) {
    id = uuid()
    localStorage.setItem(KEY, id)
  }
  return id
}

export function resetSession() {
  const id = uuid()
  localStorage.setItem(KEY, id)
  return id
}
