<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const form = reactive({
  username: '',
  password: '',
  invite_code: '',
})
const localError = ref('')
const inviteRequired = ref(false)

onMounted(async () => {
  const settings = await authApi.publicSettings()
  if (settings) {
    inviteRequired.value = Boolean(
      settings.invite_required ?? settings.require_invite_code ?? settings.registration_invite_only,
    )
  }
})

async function submit() {
  localError.value = ''
  if (!form.username || !form.password) {
    localError.value = '请填写用户名和密码'
    return
  }
  if (form.password.length < 6) {
    localError.value = '密码至少 6 位'
    return
  }
  if (inviteRequired.value && !form.invite_code) {
    localError.value = '当前需要邀请码才能注册'
    return
  }
  try {
    await auth.register({
      username: form.username,
      password: form.password,
      invite_code: form.invite_code || undefined,
    })
    router.replace('/')
  } catch (e) {
    localError.value = e.message || '注册失败'
  }
}
</script>

<template>
  <div class="auth-screen">
    <div class="auth-panel">
      <div class="auth-brand compact">
        <div class="logo-mark" aria-label="BookEcho"><img src="/favicon.svg" alt="BookEcho" width="72" height="72" decoding="async" /></div>
        <h1>创建账号</h1>
        <p>上传 TXT，一键开听</p>
      </div>

      <form class="auth-card" @submit.prevent="submit">
        <label class="field">
          <span>用户名</span>
          <input v-model.trim="form.username" autocomplete="username" placeholder="设置用户名" />
        </label>
        <label class="field">
          <span>密码</span>
          <input
            v-model="form.password"
            type="password"
            autocomplete="new-password"
            placeholder="至少 6 位密码" minlength="6"
          />
        </label>
        <label class="field">
          <span>
            邀请码
            <em v-if="!inviteRequired">（可选）</em>
            <em v-else class="required">（必填）</em>
          </span>
          <input v-model.trim="form.invite_code" placeholder="若管理员开启则需填写" />
        </label>
        <p v-if="localError || auth.error" class="form-error">{{ localError || auth.error }}</p>
        <button class="btn primary block" type="submit" :disabled="auth.loading">
          {{ auth.loading ? '提交中…' : '注册并登录' }}
        </button>
        <p class="auth-switch">
          已有账号？
          <RouterLink to="/login">去登录</RouterLink>
        </p>
      </form>
    </div>
  </div>
</template>
