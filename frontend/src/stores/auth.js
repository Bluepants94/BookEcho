import { defineStore } from 'pinia'
import { authApi, setToken, getToken } from '@/api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: getToken(),
    bootstrapped: false,
    loading: false,
    error: '',
  }),
  getters: {
    isAuthenticated: (s) => Boolean(s.token && s.user),
    isAdmin: (s) => s.user?.role === 'admin',
    displayName: (s) => s.user?.username || s.user?.email || '听友',
  },
  actions: {
    async bootstrap() {
      if (this.bootstrapped) return
      this.loading = true
      try {
        if (this.token) {
          this.user = await authApi.me()
        }
      } catch {
        this.token = ''
        this.user = null
        setToken('')
      } finally {
        this.loading = false
        this.bootstrapped = true
      }
    },
    async login(form) {
      this.error = ''
      this.loading = true
      try {
        const data = await authApi.login(form)
        const token = data.access_token || data.token
        if (!token) throw new Error('登录响应缺少 token')
        this.token = token
        setToken(token)
        this.user = data.user || (await authApi.me())
        return true
      } catch (e) {
        this.error = e.message || '登录失败'
        throw e
      } finally {
        this.loading = false
      }
    },
    async register(form) {
      this.error = ''
      this.loading = true
      try {
        const data = await authApi.register(form)
        const token = data.access_token || data.token
        if (token) {
          this.token = token
          setToken(token)
          this.user = data.user || (await authApi.me())
        } else {
          await this.login({ username: form.username, password: form.password })
        }
        return true
      } catch (e) {
        this.error = e.message || '注册失败'
        throw e
      } finally {
        this.loading = false
      }
    },
    logout() {
      this.user = null
      this.token = ''
      setToken('')
    },
  },
})
