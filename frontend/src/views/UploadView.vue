<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { booksApi } from '@/api/client'

const router = useRouter()
const file = ref(null)
const uploading = ref(false)
const message = ref('')
const error = ref('')

function onFileChange(e) {
  const f = e.target.files?.[0]
  file.value = f || null
}

async function submit() {
  error.value = ''
  message.value = ''
  if (!file.value) {
    error.value = '请选择 TXT 文件'
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    fd.append('visibility', 'private')
    const result = await booksApi.upload(fd)
    message.value = '上传成功，后台解析中，正在跳转…'
    const id = result?.id || result?.book_id
    if (id) router.push(`/books/${id}`)
    else router.push('/')
  } catch (e) {
    error.value = e.message || '上传失败'
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="page">
    <PageHeader title="上传" subtitle="选择 TXT 文件上传到书架" />
    <form class="card form-card" @submit.prevent="submit">
      <label class="field">
        <span>TXT 文件</span>
        <input type="file" accept=".txt,text/plain" @change="onFileChange" />
      </label>
      <p v-if="file" class="form-hint">已选择：{{ file.name }}</p>
      <p v-if="error" class="form-error">{{ error }}</p>
      <p v-if="message" class="form-ok">{{ message }}</p>
      <button class="btn primary block" type="submit" :disabled="uploading">
        {{ uploading ? '上传中…' : '上传' }}
      </button>
    </form>
  </div>
</template>
