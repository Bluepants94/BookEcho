<script setup>
import { onMounted, ref } from 'vue'
import { adminApi } from '@/api/client'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import { normalizeBooks } from '@/utils/format'

const books = ref([])
const loading = ref(true)
const error = ref('')
const actionError = ref('')

async function load() {
  loading.value = true
  error.value = ''
  actionError.value = ''
  try {
    books.value = normalizeBooks(await adminApi.books())
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function removeBook(book) {
  actionError.value = ''
  if (!confirm(`确认删除《${book.title || book.id}》？此操作不可恢复。`)) return
  try {
    await adminApi.deleteBook(book.id)
    await load()
  } catch (e) {
    actionError.value = e.message || '删除失败'
  }
}

onMounted(load)
</script>

<template>
  <section class="section">
    <div class="section-head">
      <h2>书籍管理</h2>
      <button class="link-btn" type="button" @click="load">刷新</button>
    </div>
    <p class="muted" style="margin: 0 0 12px">可查看并删除全站书籍；公共书开关已下线。</p>
    <LoadingState v-if="loading" />
    <p v-else-if="error" class="form-error">{{ error }}</p>
    <template v-else>
      <p v-if="actionError" class="form-error">{{ actionError }}</p>
      <EmptyState v-if="!books.length" message="暂无书籍" />
      <div v-else class="table-list">
        <article v-for="book in books" :key="book.id" class="table-row">
          <div>
            <strong>{{ book.title || book.id }}</strong>
            <p class="muted">#{{ book.id }} · {{ book.author || '未知作者' }} · owner {{ book.owner_id ?? '-' }}</p>
          </div>
          <div class="row-actions">
            <button class="btn sm danger" type="button" @click="removeBook(book)">删除</button>
          </div>
        </article>
      </div>
    </template>
  </section>
</template>
