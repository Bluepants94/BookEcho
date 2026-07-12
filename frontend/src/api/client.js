const TOKEN_KEY = 'bookecho_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

async function parseError(res) {
  let message = `请求失败 (${res.status})`
  try {
    const data = await res.json()
    message = data.detail || data.message || data.error || message
    if (Array.isArray(data.detail)) {
      message = data.detail.map((d) => d.msg || JSON.stringify(d)).join('；')
    }
  } catch {
    // ignore
  }
  const err = new Error(typeof message === 'string' ? message : JSON.stringify(message))
  err.status = res.status
  return err
}

let unauthorizedHandling = false

async function syncUnauthorizedSession() {
  if (unauthorizedHandling) return
  unauthorizedHandling = true
  try {
    setToken('')
    try {
      const { useAuthStore } = await import('@/stores/auth')
      const auth = useAuthStore()
      if (auth.token || auth.user) auth.logout()
    } catch {
      // pinia may not be ready during early boot
    }

    try {
      const { default: router } = await import('@/router')
      const current = router.currentRoute?.value
      const name = current?.name
      if (name !== 'login' && name !== 'register') {
        const redirect = current?.fullPath || '/'
        await router.replace({ name: 'login', query: { redirect } })
      }
    } catch {
      // router may not be ready
    }
  } finally {
    setTimeout(() => {
      unauthorizedHandling = false
    }, 800)
  }
}

export async function api(path, options = {}) {
  const {
    method = 'GET',
    body,
    auth = true,
    headers = {},
    raw = false,
    signal,
  } = options

  const finalHeaders = { ...headers }
  if (auth) {
    const token = getToken()
    if (token) finalHeaders.Authorization = `Bearer ${token}`
  }

  let payload = body
  if (body && !(body instanceof FormData) && !(body instanceof Blob) && !(body instanceof URLSearchParams)) {
    finalHeaders['Content-Type'] = finalHeaders['Content-Type'] || 'application/json'
    payload = JSON.stringify(body)
  }

  const res = await fetch(`/api${path}`, {
    method,
    headers: finalHeaders,
    body: payload,
    signal,
  })

  if (res.status === 401 && auth) {
    void syncUnauthorizedSession()
  }

  if (!res.ok) {
    throw await parseError(res)
  }

  if (raw) return res
  if (res.status === 204) return null

  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return res.json()
  }
  return res.blob()
}

export const authApi = {
  login: (data) => {
    const body = new URLSearchParams()
    body.set('username', data.username ?? data.email ?? '')
    body.set('password', data.password ?? '')
    if (data.grant_type) body.set('grant_type', data.grant_type)
    return api('/auth/login', {
      method: 'POST',
      body,
      auth: false,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },
  register: (data) => api('/auth/register', { method: 'POST', body: data, auth: false }),
  me: () => api('/auth/me'),
  changePassword: (data) => api('/auth/change-password', { method: 'POST', body: data }),
  publicSettings: async () => {
    try {
      return await api('/auth/registration-status', { auth: false })
    } catch {
      try {
        return await api('/auth/public-settings', { auth: false })
      } catch {
        return null
      }
    }
  },
}

export const booksApi = {
  list: (params = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') q.set(key, value)
    })
    const qs = q.toString()
    return api(`/books${qs ? `?${qs}` : ''}`)
  },
  get: (id) => api(`/books/${id}`),
  chapters: (id) => api(`/books/${id}/chapters`),
  segments: (bookId, chapterId) => api(`/books/${bookId}/chapters/${chapterId}/segments`),
  upload: async (formData) => {
    try {
      return await api('/books', { method: 'POST', body: formData })
    } catch (err) {
      if (err?.status === 404 || err?.status === 405) {
        return api('/books/upload', { method: 'POST', body: formData })
      }
      throw err
    }
  },
  mine: () => api('/books?scope=mine'),
  remove: (id) => api(`/books/${id}`, { method: 'DELETE' }),
  public: () => api('/books?scope=public'),
}

export const playbackApi = {
  getProgress: async (bookId, chapterId = null) => {
    const q = new URLSearchParams()
    q.set('book_id', bookId)
    if (chapterId != null && chapterId !== '') q.set('chapter_id', chapterId)
    const data = await api(`/playback/progress?${q.toString()}`)
    if (!data || typeof data !== 'object') return data
    const position =
      data.position_seconds ?? data.offset_seconds ?? data.position ?? data.offset ?? 0
    return {
      ...data,
      position_seconds: Number(position) || 0,
      offset_seconds: Number(position) || 0,
    }
  },
  putProgress: (data) => {
    const position =
      data.position_seconds ?? data.offset_seconds ?? data.position ?? data.offset ?? 0
    return api('/playback/progress', {
      method: 'PUT',
      body: {
        book_id: data.book_id,
        chapter_id: data.chapter_id,
        segment_index: data.segment_index ?? 0,
        position_seconds: Number(position) || 0,
        offset_seconds: Number(position) || 0,
      },
    })
  },
}

export const ttsApi = {
  synthesize: (data) =>
    api('/tts/synthesize', {
      method: 'POST',
      body: data,
      raw: true,
    }),
}

export const adminApi = {
  users: () => api('/admin/users'),
  createUser: (data) => api('/admin/users', { method: 'POST', body: data }),
  updateUser: (id, data) => api(`/admin/users/${id}`, { method: 'PATCH', body: data }),
  deleteUser: (id) => api(`/admin/users/${id}`, { method: 'DELETE' }),
  settings: () => api('/admin/settings'),
  updateSettings: (data) => api('/admin/settings', { method: 'PUT', body: data }),
  books: () => api('/admin/books'),
  setBookPublic: (id, isPublic) =>
    api(`/admin/books/${id}`, {
      method: 'PATCH',
      body: {
        visibility: isPublic ? 'public' : 'private',
        is_public: Boolean(isPublic),
      },
    }),
  deleteBook: (id) => api(`/admin/books/${id}`, { method: 'DELETE' }),
  jobs: () => api('/admin/jobs'),
  system: () => api('/admin/system'),
}
