import { reactive } from 'vue'

import { api, clearTokens, setTokens } from '../api/http'

function readUser() {
  try {
    return JSON.parse(localStorage.getItem('rag_user'))
  } catch {
    return null
  }
}

export const auth = reactive({
  user: readUser(),
  get isAuthenticated() {
    return Boolean(this.user)
  },
})

function persistSession(data) {
  setTokens({ access: data.access, refresh: data.refresh })
  localStorage.setItem('rag_user', JSON.stringify(data.user))
  auth.user = data.user
}

export async function login(credentials) {
  const data = await api('/auth/login/', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
  persistSession(data)
}

export async function register(form) {
  const data = await api('/auth/register/', {
    method: 'POST',
    body: JSON.stringify(form),
  })
  persistSession(data)
}

export async function logout() {
  let refresh = null
  try {
    refresh = JSON.parse(localStorage.getItem('rag_tokens'))?.refresh
    if (refresh) {
      await api('/auth/logout/', { method: 'POST', body: JSON.stringify({ refresh }) })
    }
  } catch {
    // 本地退出不应被网络错误阻塞。
  } finally {
    clearTokens()
    localStorage.removeItem('rag_user')
    auth.user = null
  }
}
