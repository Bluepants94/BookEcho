<script setup>
import { onMounted, ref } from 'vue'
import { adminApi } from '@/api/client'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import { normalizeList } from '@/utils/format'

const jobs = ref([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    jobs.value = normalizeList(await adminApi.jobs())
  } catch (e) {
    error.value = e.message || '加载任务失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="section">
    <div class="section-head">
      <h2>任务 Jobs</h2>
      <button class="link-btn" type="button" @click="load">刷新</button>
    </div>
    <LoadingState v-if="loading" />
    <p v-else-if="error" class="form-error">{{ error }}</p>
    <EmptyState v-else-if="!jobs.length" message="暂无任务" />
    <div v-else class="table-list">
      <article v-for="job in jobs" :key="job.id" class="table-row">
        <div>
          <strong>{{ job.type || job.name || job.id }}</strong>
          <p class="muted">
            {{ job.status || 'unknown' }}
            <template v-if="job.created_at"> · {{ job.created_at }}</template>
          </p>
        </div>
      </article>
    </div>
  </section>
</template>
