<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { authApi } from '@/api/client'

const router = useRouter()
const form = reactive({
  old_password: '',
  new_password: '',
  confirm: '',
})
const msg = ref('')
const err = ref('')
const loading = ref(false)

async function submit() {
  msg.value = ''
  err.value = ''
  if (!form.old_password || !form.new_password) {
    err.value = '请填写原密码和新密码'
    return
  }
  if (form.new_password.length < 6) {
    err.value = '新密码至少 6 位'
    return
  }
  if (form.new_password !== form.confirm) {
    err.value = '两次输入的新密码不一致'
    return
  }
  loading.value = true
  try {
    await authApi.changePassword({
      old_password: form.old_password,
      new_password: form.new_password,
    })
    msg.value = '密码已修改'
    form.old_password = ''
    form.new_password = ''
    form.confirm = ''
  } catch (e) {
    err.value = e.message || '修改失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <PageHeader title="修改密码" back />
    <form class="card form-card" @submit.prevent="submit">
      <label class="field">
        <span>原密码</span>
        <input v-model="form.old_password" type="password" autocomplete="current-password" />
      </label>
      <label class="field">
        <span>新密码</span>
        <input v-model="form.new_password" type="password" autocomplete="new-password" />
      </label>
      <label class="field">
        <span>确认新密码</span>
        <input v-model="form.confirm" type="password" autocomplete="new-password" />
      </label>
      <p v-if="err" class="form-error">{{ err }}</p>
      <p v-if="msg" class="form-ok">{{ msg }}</p>
      <button class="btn primary block" type="submit" :disabled="loading">
        {{ loading ? '提交中…' : '保存' }}
      </button>
      <button class="btn block" type="button" style="margin-top: 8px" @click="router.back()">返回</button>
    </form>
  </div>
</template>
