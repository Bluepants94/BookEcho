<script setup>
import { onMounted, ref } from 'vue'
import { adminApi } from '@/api/client'
import LoadingState from '@/components/LoadingState.vue'

const info = ref(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    info.value = await adminApi.system()
  } catch (e) {
    info.value = null
    error.value = e.message || '系统信息暂不可用'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="section">
    <div class="section-head">
      <h2>系统信息</h2>
      <button class="link-btn" type="button" @click="load">刷新</button>
    </div>
    <LoadingState v-if="loading" />
    <div v-else-if="error" class="empty-panel">
      <p class="form-error">{{ error }}</p>
      <p class="form-hint">系统接口暂不可用，可稍后重试。不影响听书主流程。</p>
    </div>
    <pre v-else class="code-block">{{ JSON.stringify(info, null, 2) }}</pre>
  </section>
</template>
