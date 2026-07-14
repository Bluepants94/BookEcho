<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import { booksApi, playbackApi } from '@/api/client'
import { useBooksStore } from '@/stores/books'
import { usePlayerStore } from '@/stores/player'
import { listCachedChapterIds } from '@/utils/audioCache'
import { getTtsCacheFingerprint } from '@/utils/ttsSettings'

const CHAPTER_PAGE_SIZE = 50

const route = useRoute()
const router = useRouter()
const books = useBooksStore()
const player = usePlayerStore()
const booting = ref(true)
const deleting = ref(false)
const actionError = ref('')
const bookProgress = ref(null)
const cachedChapterIds = ref(new Set())
const chapterPageIndex = ref(0)
const pageSelectOpen = ref(false)
const pageSelectEl = ref(null)

const PAGE_SELECT_LEAVE_MS = 3000
let pageSelectLeaveTimer = null
let pageSelectDocHandler = null

const book = computed(() => books.currentBook)
const chapters = computed(() => books.chapters)

const chapterPageCount = computed(() =>
  Math.max(1, Math.ceil((chapters.value.length || 0) / CHAPTER_PAGE_SIZE)),
)

const chapterPageOptions = computed(() => {
  const total = chapters.value.length
  if (!total) return []
  const pages = []
  for (let i = 0; i < chapterPageCount.value; i += 1) {
    const start = i * CHAPTER_PAGE_SIZE + 1
    const end = Math.min(total, (i + 1) * CHAPTER_PAGE_SIZE)
    pages.push({
      index: i,
      label: `第${start}章 ~ 第${end}章`,
    })
  }
  return pages
})

const pagedChapters = computed(() => {
  const start = chapterPageIndex.value * CHAPTER_PAGE_SIZE
  return chapters.value
    .slice(start, start + CHAPTER_PAGE_SIZE)
    .map((chapter, offset) => ({
      chapter,
      index: start + offset,
    }))
})

const chapterPageTriggerLabel = computed(() => `共${chapters.value.length}章 ▾`)

const latestChapterId = computed(() => {
  const id = bookProgress.value?.chapter_id
  return id == null ? null : String(id)
})

let focusHandler = null
let refreshTimer = null

function refreshCacheBadges() {
  if (!book.value?.id) {
    cachedChapterIds.value = new Set()
    return
  }
  try {
    const fp = getTtsCacheFingerprint()
    const ids = listCachedChapterIds(fp, book.value.id)
    cachedChapterIds.value = new Set(ids.map(String))
  } catch {
    cachedChapterIds.value = new Set()
  }
}

async function refreshBookProgress() {
  if (!book.value?.id) {
    bookProgress.value = null
    return
  }
  try {
    bookProgress.value = await playbackApi.getProgress(book.value.id)
  } catch {
    bookProgress.value = null
  }
}

function isChapterCached(chapterId) {
  return cachedChapterIds.value.has(String(chapterId))
}

function isLatestChapter(chapter) {
  return latestChapterId.value != null && String(chapter.id) === latestChapterId.value
}

function chapterProgressPercent(chapter) {
  const progress = bookProgress.value
  // Only the chapter that has stored progress shows a bar; others stay empty.
  if (!progress || progress.chapter_id == null) return 0
  if (String(progress.chapter_id) !== String(chapter.id)) return 0

  const segIndex = Math.max(0, Number(progress.segment_index) || 0)
  const position = Math.max(0, Number(progress.position_seconds) || 0)
  // Coarse fraction when we only know absolute seconds on current segment.
  const positionFraction = position > 0 ? Math.min(0.95, position / 30) : 0

  const segmentCount = Number(chapter.segment_count)
  if (Number.isFinite(segmentCount) && segmentCount > 0) {
    const ratio = (segIndex + positionFraction) / segmentCount
    return Math.max(0, Math.min(100, ratio * 100))
  }

  // Unknown total: show a thin non-zero bar once any progress exists.
  if (segIndex <= 0 && position <= 0) return 0
  return Math.max(4, Math.min(90, (segIndex + 1) * 8 + positionFraction * 8))
}

function clearPageSelectLeaveTimer() {
  if (pageSelectLeaveTimer) {
    window.clearTimeout(pageSelectLeaveTimer)
    pageSelectLeaveTimer = null
  }
}

function closePageSelect() {
  clearPageSelectLeaveTimer()
  pageSelectOpen.value = false
}

function togglePageSelect() {
  clearPageSelectLeaveTimer()
  pageSelectOpen.value = !pageSelectOpen.value
}

function onPageSelectPointerEnter() {
  clearPageSelectLeaveTimer()
}

function onPageSelectPointerLeave() {
  if (!pageSelectOpen.value) return
  clearPageSelectLeaveTimer()
  pageSelectLeaveTimer = window.setTimeout(() => {
    pageSelectOpen.value = false
    pageSelectLeaveTimer = null
  }, PAGE_SELECT_LEAVE_MS)
}

function onPageSelectDocumentClick(event) {
  if (!pageSelectOpen.value) return
  const root = pageSelectEl.value
  if (root && root.contains(event.target)) return
  closePageSelect()
}

function setChapterPage(index) {
  const max = chapterPageCount.value - 1
  chapterPageIndex.value = Math.max(0, Math.min(max, Number(index) || 0))
  closePageSelect()
}

function focusLatestChapterPage() {
  const list = chapters.value
  if (!list.length) {
    chapterPageIndex.value = 0
    return -1
  }
  const progressId = latestChapterId.value
  if (!progressId) {
    chapterPageIndex.value = 0
    return -1
  }
  const index = list.findIndex((c) => String(c.id) === progressId)
  if (index < 0) {
    chapterPageIndex.value = 0
    return -1
  }
  chapterPageIndex.value = Math.floor(index / CHAPTER_PAGE_SIZE)
  return index
}

async function scrollLatestChapterIntoView() {
  await nextTick()
  const el = document.querySelector('.chapter-item.is-latest')
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

onMounted(async () => {
  try {
    await books.fetchBook(route.params.id)
    await refreshBookProgress()
    refreshCacheBadges()
    focusLatestChapterPage()
    await scrollLatestChapterIntoView()
  } finally {
    booting.value = false
  }

  focusHandler = () => {
    refreshCacheBadges()
    refreshBookProgress().then(() => {
      // Keep current page unless progress points elsewhere and page is empty selection.
    })
  }
  window.addEventListener('focus', focusHandler)
  refreshTimer = window.setInterval(() => {
    refreshCacheBadges()
  }, 8000)
  pageSelectDocHandler = onPageSelectDocumentClick
  document.addEventListener('click', pageSelectDocHandler)
})

onUnmounted(() => {
  if (focusHandler) window.removeEventListener('focus', focusHandler)
  if (refreshTimer) window.clearInterval(refreshTimer)
  if (pageSelectDocHandler) document.removeEventListener('click', pageSelectDocHandler)
  clearPageSelectLeaveTimer()
})

async function openChapter(chapter) {
  if (!chapter?.id || !book.value?.id) return
  const bookId = book.value.id
  const chapterList = chapters.value.map((c, index) => ({
    id: c.id,
    title: c.title || `第 ${index + 1} 章`,
    index,
  }))
  const found = chapterList.find((c) => String(c.id) === String(chapter.id))
  const chapterTitle = found?.title || chapter.title || `第 ${(chapter.index ?? 0) + 1} 章`

  // Kick off chapter open under the click gesture for autoplay eligibility,
  // but never wait for TTS/audio before navigating into the player page.
  // Content and audio are independent: the player page can render text as
  // soon as segments arrive while the play control shows a spinner.
  void player
    .resumeFromServer(bookId, chapter.id, {
      bookTitle: book.value.title || player.bookTitle || '',
      chapterTitle,
      chapterList,
      autoplay: true,
    })
    .catch(() => {
      // PlayerView bootstrap / on-page retry will surface the error.
    })

  router.push({
    name: 'player',
    params: { bookId, chapterId: chapter.id },
    query: { autoplay: '1' },
  })
}

async function removeBook() {
  if (!book.value) return
  if (!confirm(`确认删除《${book.value.title || book.value.id}》？`)) return
  deleting.value = true
  actionError.value = ''
  try {
    await booksApi.remove(book.value.id)
    router.replace('/')
  } catch (e) {
    actionError.value = e.message || '删除失败'
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="page">
    <PageHeader title="书籍详情" back />
    <LoadingState v-if="booting" />
    <template v-else-if="book">
      <div class="book-detail-hero">
        <div>
          <h2>{{ book.title }}</h2>
          <p>{{ book.author || book.owner_name || '未知作者' }}</p>
          <p class="muted">{{ book.description || '暂无简介' }}</p>
          <div class="book-meta-row">
            <button class="btn sm danger-outline" type="button" :disabled="deleting" @click="removeBook">
              {{ deleting ? '删除中…' : '删除书籍' }}
            </button>
          </div>
          <p v-if="actionError" class="form-error">{{ actionError }}</p>
        </div>
      </div>

      <section class="section">
        <div class="section-head">
          <h2>章节列表</h2>
          <div
            v-if="chapters.length"
            ref="pageSelectEl"
            class="chapter-page-select"
            @pointerenter="onPageSelectPointerEnter"
            @pointerleave="onPageSelectPointerLeave"
          >
            <button
              class="chapter-page-trigger"
              type="button"
              :aria-expanded="pageSelectOpen ? 'true' : 'false'"
              @click.stop="togglePageSelect"
            >
              {{ chapterPageTriggerLabel }}
            </button>
            <div v-if="pageSelectOpen" class="chapter-page-menu" role="listbox">
              <button
                v-for="opt in chapterPageOptions"
                :key="opt.index"
                type="button"
                class="chapter-page-option"
                :class="{ active: opt.index === chapterPageIndex }"
                role="option"
                :aria-selected="opt.index === chapterPageIndex"
                @click.stop="setChapterPage(opt.index)"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <span v-else class="muted">0 章</span>
        </div>
        <EmptyState v-if="!chapters.length" message="暂无章节，可能仍在解析中" />
        <ul v-else class="chapter-list">
          <li v-for="item in pagedChapters" :key="item.chapter.id">
            <button
              type="button"
              class="chapter-item"
              :class="{ 'is-latest': isLatestChapter(item.chapter) }"
              :data-chapter-id="item.chapter.id"
              @click="openChapter(item.chapter)"
            >
              <div class="chapter-item-main">
                <div class="chapter-title-row">
                  <strong>{{ item.chapter.title || `第 ${item.index + 1} 章` }}</strong>
                  <span v-if="isChapterCached(item.chapter.id)" class="chapter-cache-badge">已缓存</span>
                </div>
                <div class="chapter-progress" aria-hidden="true">
                  <div
                    class="chapter-progress-fill"
                    :style="{ width: `${chapterProgressPercent(item.chapter)}%` }"
                  />
                </div>
              </div>
            </button>
          </li>
        </ul>
      </section>
    </template>
    <EmptyState v-else :message="books.error || '书籍不存在'" />
  </div>
</template>

