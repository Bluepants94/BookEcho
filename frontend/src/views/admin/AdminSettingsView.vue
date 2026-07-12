<script setup>
import { onMounted, reactive, ref } from 'vue'
import { adminApi } from '@/api/client'

const form = reactive({
  registration_enabled: true,
  invite_required: false,
  invite_code: '',
})
const loading = ref(true)
const message = ref('')
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await adminApi.settings()
    form.registration_enabled = data.registration_enabled ?? data.allow_register ?? true
    form.invite_required = data.invite_required ?? data.require_invite_code ?? false
    form.invite_code = data.invite_code || data.current_invite_code || ''
  } catch (e) {
    error.value = e.message || '加载设置失败'
  } finally {
    loading.value = false
  }
}

async function save() {
  message.value = ''
  error.value = ''
  try {
    await adminApi.updateSettings({
      registration_enabled: form.registration_enabled,
      invite_required: form.invite_required,
      invite_code: form.invite_code,
    })
    message.value = '已保存'
  } catch (e) {
    error.value = e.message || '保存失败'
  }
}

onMounted(load)
</script>

<template>
  <section class="section">
    <div class="section-head">
      <h2>注册 / 邀请码</h2>
    </div>
    <form class="card form-card" @submit.prevent="save">
      <label class="switch-row">
        <span>开放注册</span>
        <input v-model="form.registration_enabled" type="checkbox" />
      </label>
      <label class="switch-row">
        <span>需要邀请码</span>
        <input v-model="form.invite_required" type="checkbox" />
      </label>
      <label class="field">
        <span>邀请码</span>
        <input v-model.trim="form.invite_code" placeholder="设置或轮换邀请码" />
      </label>
      <p v-if="error" class="form-error">{{ error }}</p>
      <p v-if="message" class="form-ok">{{ message }}</p>
      <button class="btn primary" type="submit" :disabled="loading">保存</button>
    </form>
  </section>
</template>
