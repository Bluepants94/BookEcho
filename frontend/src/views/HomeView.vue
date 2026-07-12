<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import BookCard from '@/components/BookCard.vue'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useAuthStore } from '@/stores/auth'
import { useBooksStore } from '@/stores/books'

const HOME_PAGE_SIZE = 15

const auth = useAuthStore()
const books = useBooksStore()
const pageIndex = ref(0)

const totalBooks = computed(() => books.myBooks.length)
const pageCount = computed(() => Math.max(1, Math.ceil(totalBooks.value / HOME_PAGE_SIZE)))
const pagedBooks = computed(() => {
  const start = pageIndex.value * HOME_PAGE_SIZE
  return books.myBooks.slice(start, start + HOME_PAGE_SIZE)
})
const pageLabel = computed(() => {
  if (!totalBooks.value) return '0 / 0'
  return `${pageIndex.value + 1} / ${pageCount.value}`
})
const canPrev = computed(() => pageIndex.value > 0)
const canNext = computed(() => pageIndex.value + 1 < pageCount.value)

watch(totalBooks, () => {
  const max = Math.max(0, pageCount.value - 1)
  if (pageIndex.value > max) pageIndex.value = max
})

function prevPage() {
  if (!canPrev.value) return
  pageIndex.value -= 1
}

function nextPage() {
  if (!canNext.value) return
  pageIndex.value += 1
}

async function refresh() {
  pageIndex.value = 0
  await books.fetchHome()
}

onMounted(() => {
  books.fetchHome()
})
</script>

<template>
  <div class="page">
    <PageHeader :title="`你好，${auth.displayName}`" />

    <section class="section">
      <div class="section-head">
        <h2>我的书架</h2>
        <button class="link-btn" type="button" @click="refresh">刷新</button>
      </div>
      <LoadingState v-if="books.loading && !books.myBooks.length" />
      <EmptyState v-else-if="!books.myBooks.length" message="书架还是空的">
        <RouterLink class="btn primary sm" to="/upload">去上传</RouterLink>
      </EmptyState>
      <template v-else>
        <div class="book-grid">
          <BookCard
            v-for="book in pagedBooks"
            :key="book.id"
            :book="book"
          />
        </div>
        <div v-if="totalBooks > HOME_PAGE_SIZE" class="home-pagination" aria-label="书架分页">
          <button class="btn sm" type="button" :disabled="!canPrev" @click="prevPage">上一页</button>
          <span class="home-pagination-label">{{ pageLabel }}</span>
          <button class="btn sm" type="button" :disabled="!canNext" @click="nextPage">下一页</button>
        </div>
      </template>
      <p v-if="books.error" class="form-error center">{{ books.error }}</p>
    </section>
  </div>
</template>
