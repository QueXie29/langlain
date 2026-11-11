const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

let refreshPromise = null

function getTokens() {
  try {
    return JSON.parse(localStorage.getItem('rag_tokens')) || {}
  } catch {
    return {}
  }
}

export function setTokens(tokens) {
  localStorage.setItem('rag_tokens', JSON.stringify(tokens))
}

export function clearTokens() {
  localStorage.removeItem('rag_tokens')
}

async function refreshAccessToken() {
  const { refresh } = getTokens()
  if (!refresh) throw new Error('登录状态已失效，请重新登录。')
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE}/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('登录状态已失效，请重新登录。')
        const data = await response.json()
        setTokens({ access: data.access, refresh: data.refresh || refresh })
        return data.access
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

function messageFromPayload(payload, fallback) {
  if (!payload) return fallback
  if (typeof payload === 'string') return payload
  if (payload.detail) return payload.detail
  const firstValue = Object.values(payload)[0]
  if (Array.isArray(firstValue)) return firstValue[0]
  if (typeof firstValue === 'string') return firstValue
  return fallback
}

export async function api(path, options = {}, canRetry = true) {
  const tokens = getTokens()
  const headers = new Headers(options.headers || {})
  if (!(options.body instanceof FormData) && options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }
  if (tokens.access) headers.set('Authorization', `Bearer ${tokens.access}`)

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (response.status === 401 && canRetry && tokens.refresh) {
    try {
      await refreshAccessToken()
      return api(path, options, false)
    } catch (error) {
      clearTokens()
      localStorage.removeItem('rag_user')
      window.dispatchEvent(new Event('auth-expired'))
      throw error
    }
  }
  if (response.status === 204) return null

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(messageFromPayload(payload, `请求失败（${response.status}）`))
  }
  return payload
}

