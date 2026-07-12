<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authApi } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const form = reactive({ username: '', password: '' })
const localError = ref('')
const registrationEnabled = ref(true)

onMounted(async () => {
  try {
    const settings = await authApi.publicSettings()
    if (settings && typeof settings === 'object') {
      const enabled =
        settings.registration_enabled ??
        settings.allow_register ??
        settings.register_enabled
      if (enabled != null) registrationEnabled.value = Boolean(enabled)
    }
  } catch {
    // Keep register link visible when status cannot be loaded.
  }
})

function safeRedirectPath(raw) {
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value !== 'string') return '/'
  if (!value.startsWith('/') || value.startsWith('//')) return '/'
  return value
}

async function submit() {
  localError.value = ''
  if (!form.username || !form.password) {
    localError.value = '请输入用户名和密码'
    return
  }
  try {
    await auth.login(form)
    router.replace(safeRedirectPath(route.query.redirect))
  } catch (e) {
    localError.value = e.message || '登录失败'
  }
}
</script>

<template>
  <div class="auth-screen">
    <div class="auth-panel">
      <div class="auth-brand">
        <div class="logo-mark" aria-label="BookEcho"><img src="/favicon.svg" alt="BookEcho" width="72" height="72" decoding="async" /></div>
        <h1>BookEcho</h1>
        <p>把文字变成随身听书时光</p>
      </div>

      <form class="auth-card" @submit.prevent="submit">
        <h2>登录</h2>
        <label class="field">
          <span>用户名</span>
          <input
            v-model.trim="form.username"
            autocomplete="username"
            placeholder="请输入用户名"
          />
        </label>
        <label class="field">
          <span>密码</span>
          <input
            v-model="form.password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
          />
        </label>
        <p v-if="localError || auth.error" class="form-error">{{ localError || auth.error }}</p>
        <button class="btn primary block" type="submit" :disabled="auth.loading">
          {{ auth.loading ? '登录中…' : '进入听书' }}
        </button>
        <p v-if="registrationEnabled" class="auth-switch">
          还没有账号？
          <RouterLink to="/register">立即注册</RouterLink>
        </p>
      </form>
    </div>
  </div>
</template>
