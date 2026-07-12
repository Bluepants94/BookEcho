<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlayerStore, SPEEDS } from '@/stores/player'
import { useSettingsStore } from '@/stores/settings'
import { booksApi } from '@/api/client'
import { formatTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const player = usePlayerStore()
const settings = useSettingsStore()
const ready = ref(false)
const localError = ref('')
const readerEl = ref(null)
const suppressScrollFollow = ref(false)
let bootToken = 0
let userScrollTimer = null

const CHAPTER_PAGE_SIZE = 50
const POPOVER_LEAVE_MS = 3000
const chapterPopoverOpen = ref(false)
const speedPopoverOpen = ref(false)
const chapterPopoverEl = ref(null)
const speedPopoverEl = ref(null)
const chapterPageIndex = ref(0)
const chapterPageMenuOpen = ref(false)
const localChapterList = ref([])
const chapterListLoading = ref(false)

let chapterLeaveTimer = null
let speedLeaveTimer = null
let docClickHandler = null

const progressStyle = computed(() => ({
  width: `${player.progressPercent}%`,
}))

const canSeek = computed(() => Number(player.chapterDuration) > 0)

const durationLabel = computed(() => {
  if (!canSeek.value) return '时长未知'
  return formatTime(player.chapterDuration)
})

const headerChapter = computed(
  () => player.chapterTitle || '章节',
)

const chapterSource = computed(() => {
  if (player.chapterList?.length) return player.chapterList
  return localChapterList.value
})

const chapterTotal = computed(() => chapterSource.value.length)

const chapterPageCount = computed(() =>
  Math.max(1, Math.ceil((chapterTotal.value || 0) / CHAPTER_PAGE_SIZE)),
)

const chapterPageOptions = computed(() => {
  const total = chapterTotal.value
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

const chapterPageTriggerLabel = computed(() => `共${chapterTotal.value}章 ▾`)

const pagedChapters = computed(() => {
  const start = chapterPageIndex.value * CHAPTER_PAGE_SIZE
  return chapterSource.value
    .slice(start, start + CHAPTER_PAGE_SIZE)
    .map((chapter, offset) => ({
      chapter,
      index: start + offset,
    }))
})

const speedOptions = computed(() => SPEEDS)

function clearChapterLeaveTimer() {
  if (chapterLeaveTimer) {
    clearTimeout(chapterLeaveTimer)
    chapterLeaveTimer = null
  }
}

function clearSpeedLeaveTimer() {
  if (speedLeaveTimer) {
    clearTimeout(speedLeaveTimer)
    speedLeaveTimer = null
  }
}

function closeChapterPopover() {
  clearChapterLeaveTimer()
  chapterPopoverOpen.value = false
  chapterPageMenuOpen.value = false
}

function closeSpeedPopover() {
  clearSpeedLeaveTimer()
  speedPopoverOpen.value = false
}

function closeAllPopovers() {
  closeChapterPopover()
  closeSpeedPopover()
}

function focusCurrentChapterPage() {
  const list = chapterSource.value
  if (!list.length) {
    chapterPageIndex.value = 0
    return
  }
  const currentId = player.chapterId
  let index = -1
  if (currentId != null) {
    index = list.findIndex((c) => String(c.id) === String(currentId))
  }
  if (index < 0 && Number.isFinite(player.chapterOrderIndex) && player.chapterOrderIndex >= 0) {
    index = player.chapterOrderIndex
  }
  if (index < 0) {
    chapterPageIndex.value = 0
    return
  }
  chapterPageIndex.value = Math.floor(index / CHAPTER_PAGE_SIZE)
}

async function ensureLocalChapterList() {
  if (player.chapterList?.length) {
    localChapterList.value = player.chapterList
    return player.chapterList
  }
  const bookId = route.params.bookId || player.bookId
  if (!bookId) {
    localChapterList.value = []
    return []
  }
  chapterListLoading.value = true
  try {
    const chapters = await booksApi.chapters(bookId)
    const list = Array.isArray(chapters) ? chapters : chapters?.items || chapters?.data || []
    localChapterList.value = list.map((c, i) => ({
      id: c.id,
      title: c.title || `第 ${i + 1} 章`,
      index: i,
    }))
    return localChapterList.value
  } catch {
    localChapterList.value = []
    return []
  } finally {
    chapterListLoading.value = false
  }
}

async function openChapterPopover() {
  closeSpeedPopover()
  clearChapterLeaveTimer()
  await ensureLocalChapterList()
  focusCurrentChapterPage()
  chapterPageMenuOpen.value = false
  chapterPopoverOpen.value = true
}

function toggleChapterPopover() {
  if (chapterPopoverOpen.value) {
    closeChapterPopover()
    return
  }
  openChapterPopover()
}

function toggleSpeedPopover() {
  clearSpeedLeaveTimer()
  if (speedPopoverOpen.value) {
    closeSpeedPopover()
    return
  }
  closeChapterPopover()
  speedPopoverOpen.value = true
}

function onChapterPointerEnter() {
  clearChapterLeaveTimer()
}

function onChapterPointerLeave() {
  if (!chapterPopoverOpen.value) return
  clearChapterLeaveTimer()
  chapterLeaveTimer = setTimeout(() => {
    chapterLeaveTimer = null
    closeChapterPopover()
  }, POPOVER_LEAVE_MS)
}

function onSpeedPointerEnter() {
  clearSpeedLeaveTimer()
}

function onSpeedPointerLeave() {
  if (!speedPopoverOpen.value) return
  clearSpeedLeaveTimer()
  speedLeaveTimer = setTimeout(() => {
    speedLeaveTimer = null
    closeSpeedPopover()
  }, POPOVER_LEAVE_MS)
}

function onDocumentClick(event) {
  if (chapterPopoverOpen.value) {
    const root = chapterPopoverEl.value
    if (!root || !root.contains(event.target)) closeChapterPopover()
  }
  if (speedPopoverOpen.value) {
    const root = speedPopoverEl.value
    if (!root || !root.contains(event.target)) closeSpeedPopover()
  }
}

function setChapterPage(index) {
  const max = chapterPageCount.value - 1
  chapterPageIndex.value = Math.max(0, Math.min(max, Number(index) || 0))
  chapterPageMenuOpen.value = false
}

function toggleChapterPageMenu() {
  chapterPageMenuOpen.value = !chapterPageMenuOpen.value
}

function selectSpeed(rate) {
  player.setSpeed(rate)
  closeSpeedPopover()
}

function isCurrentChapter(chapter) {
  return player.chapterId != null && String(chapter.id) === String(player.chapterId)
}

async function selectChapter(chapter, index = 0) {
  if (!chapter?.id) return
  const bookId = route.params.bookId || player.bookId
  if (!bookId) return

  const chapterList = chapterSource.value.length
    ? chapterSource.value
    : [{ id: chapter.id, title: chapter.title || `第 ${index + 1} 章`, index }]

  closeAllPopovers()
  localError.value = ''

  try {
    await player.resumeFromServer(bookId, chapter.id, {
      bookTitle: player.bookTitle,
      chapterTitle: chapter.title || `第 ${index + 1} 章`,
      chapterList,
      autoplay: true,
    })
    const target = `/player/${bookId}/${chapter.id}`
    if (route.fullPath !== target) {
      await router.replace(target)
    }
  } catch (e) {
    localError.value = e.message || '切换章节失败'
  }
}

async function bootstrap() {
  const token = ++bootToken
  const bookId = route.params.bookId
  const chapterId = route.params.chapterId
  localError.value = ''
  ready.value = false
  try {
    let bookTitle = player.bookTitle
    let chapterTitle = player.chapterTitle
    let chapterList = null

    if (!bookTitle || String(player.bookId) !== String(bookId)) {
      try {
        const book = await booksApi.get(bookId)
        if (token !== bootToken) return
        bookTitle = book.title
      } catch {
        // ignore
      }
    }

    if (!player.chapterList?.length || String(player.bookId) !== String(bookId)) {
      try {
        const chapters = await booksApi.chapters(bookId)
        if (token !== bootToken) return
        const list = Array.isArray(chapters) ? chapters : chapters?.items || chapters?.data || []
        chapterList = list.map((c, i) => ({
          id: c.id,
          title: c.title || `第 ${i + 1} 章`,
          index: i,
        }))
        localChapterList.value = chapterList
        const found = chapterList.find((c) => String(c.id) === String(chapterId))
        if (found) chapterTitle = found.title
      } catch {
        // ignore
      }
    } else {
      chapterList = player.chapterList
      localChapterList.value = player.chapterList
      const found = chapterList.find((c) => String(c.id) === String(chapterId))
      if (found && !chapterTitle) chapterTitle = found.title
    }

    // Same track already loaded / opening: keep current audio session.
    // Critical for chapter auto-advance: store may have already open()ed with autoplay
    // before router.replace; re-bootstrapping with autoplay:false would kill continuous play.
    // Route params are strings; store IDs may be numbers — always compare via String().
    const sameTrack =
      String(player.bookId) === String(bookId) &&
      String(player.chapterId) === String(chapterId)
    const continuityActive =
      player.segments.length ||
      player.loading ||
      player.playing ||
      player.userStartedPlayback ||
      player.autoplayContinuity
    if (sameTrack && continuityActive) {
      if (token !== bootToken) return
      ready.value = true
      await nextTick()
      if (token !== bootToken) return
      scrollActiveIntoView(false)
      return
    }

    await player.resumeFromServer(bookId, chapterId, {
      bookTitle,
      chapterTitle,
      chapterList,
      autoplay: false,
    })
    if (token !== bootToken) return
    ready.value = true
    await nextTick()
    if (token !== bootToken) return
    scrollActiveIntoView(false)
  } catch (e) {
    if (token !== bootToken) return
    localError.value = e.message || '打开播放页失败'
    ready.value = true
  }
}

onMounted(() => {
  bootstrap()
  docClickHandler = onDocumentClick
  document.addEventListener('click', docClickHandler)
})

onUnmounted(() => {
  bootToken += 1
  if (userScrollTimer) {
    clearTimeout(userScrollTimer)
    userScrollTimer = null
  }
  if (docClickHandler) {
    document.removeEventListener('click', docClickHandler)
    docClickHandler = null
  }
  clearChapterLeaveTimer()
  clearSpeedLeaveTimer()
})

watch(
  () => [route.params.bookId, route.params.chapterId],
  () => {
    closeAllPopovers()
    bootstrap()
  },
)

function scrollActiveIntoView(smooth = true) {
  if (suppressScrollFollow.value) return
  const root = readerEl.value
  if (!root) return
  const el = root.querySelector(`[data-seg-index="${player.segmentIndex}"]`)
  if (!el) return
  el.scrollIntoView({
    behavior: smooth ? 'smooth' : 'auto',
    block: 'center',
  })
}

function onReaderScroll() {
  // User is manually browsing — pause auto-follow briefly.
  suppressScrollFollow.value = true
  if (userScrollTimer) clearTimeout(userScrollTimer)
  userScrollTimer = setTimeout(() => {
    suppressScrollFollow.value = false
    userScrollTimer = null
  }, 2500)
}

watch(
  () => player.segmentIndex,
  async () => {
    await nextTick()
    scrollActiveIntoView(true)
  },
)

// Light follow while time advances (e.g. after seek within segment re-centers if scrolled away).
watch(
  () => Math.floor(player.currentTime),
  () => {
    // Avoid thrashing: only nudge when active segment is far off-screen.
    const root = readerEl.value
    if (!root) return
    const el = root.querySelector(`[data-seg-index="${player.segmentIndex}"]`)
    if (!el) return
    const rootRect = root.getBoundingClientRect()
    const elRect = el.getBoundingClientRect()
    const margin = rootRect.height * 0.2
    const outOfView = elRect.bottom < rootRect.top + margin || elRect.top > rootRect.bottom - margin
    if (outOfView) scrollActiveIntoView(true)
  },
)

async function jumpToSegment(index) {
  if (index === player.segmentIndex && player.audio?.currentSrc) {
    // Restart current segment from beginning when re-clicked.
    if (player.audio) {
      player.audio.currentTime = 0
      try {
        await player.audio.play()
        player.userStartedPlayback = true
        player.ensureChapterWindowCache()
      } catch {
        // ignore
      }
    }
    return
  }
  player.resumeOffset = 0
  suppressScrollFollow.value = true
  player.userStartedPlayback = true
  await player.loadSegment(index, true)
  await nextTick()
  suppressScrollFollow.value = false
  scrollActiveIntoView(true)
}

async function onSeek(e) {
  if (!canSeek.value) return
  const rect = e.currentTarget.getBoundingClientRect()
  const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
  await player.seek(ratio)
}

async function onSeekKeydown(e) {
  if (!canSeek.value) return
  const step = e.shiftKey ? 0.05 : 0.02
  let next = player.progressPercent / 100
  if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
    e.preventDefault()
    next = Math.min(1, next + step)
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
    e.preventDefault()
    next = Math.max(0, next - step)
  } else if (e.key === 'Home') {
    e.preventDefault()
    next = 0
  } else if (e.key === 'End') {
    e.preventDefault()
    next = 1
  } else {
    return
  }
  await player.seek(next)
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

function dismissNotice() {
  settings.clearTtsNotice()
}
</script>

<template>
  <div class="player-page">
    <header class="player-top">
      <button class="icon-btn light" type="button" aria-label="返回" @click="goBack">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M15 6 9 12l6 6" />
        </svg>
      </button>
      <div class="player-top-main">
        <div class="player-titles">
          <p class="player-chapter-title">{{ headerChapter }}</p>
        </div>
      </div>
      <div class="player-top-status" aria-hidden="true">
        <div class="player-wave" :class="{ playing: player.playing }">
          <i /><i /><i /><i />
        </div>
      </div>
    </header>

    <div
      v-if="settings.ttsUpdatedNotice"
      class="player-notice"
      role="status"
    >
      <span>{{ settings.ttsUpdatedNotice }}</span>
      <button type="button" class="notice-close" aria-label="关闭提示" @click="dismissNotice">×</button>
    </div>

    <section
      ref="readerEl"
      class="reader-panel"
      aria-label="章节正文"
      @scroll.passive="onReaderScroll"
    >
      <p v-if="!ready" class="muted center reader-status">加载中…</p>
      <p v-else-if="!player.segments.length" class="muted center reader-status">暂无段落</p>
      <template v-else>
        <button
          v-for="(seg, index) in player.segments"
          :key="seg.id || index"
          type="button"
          class="reader-seg"
          :class="{
            'is-active': index === player.segmentIndex,
            'is-past': index < player.segmentIndex,
          }"
          :data-seg-index="index"
          @click="jumpToSegment(index)"
        >
          <span class="reader-seg-text">{{ seg.text || '（空段落）' }}</span>
        </button>
      </template>
    </section>

    <div class="player-panel player-controls-bar">
      <div class="seekbar">
        <div
          class="seekbar-track"
          :class="{ 'is-disabled': !canSeek }"
          role="slider"
          tabindex="0"
          :aria-disabled="canSeek ? 'false' : 'true'"
          :aria-valuemin="0"
          :aria-valuemax="100"
          :aria-valuenow="Math.round(player.progressPercent)"
          :aria-valuetext="canSeek ? `${formatTime(player.chapterElapsed)} / ${formatTime(player.chapterDuration)}` : '时长未知，暂不可拖动进度'"
          aria-label="播放进度"
          @click="onSeek"
          @keydown="onSeekKeydown"
        >
          <div class="seekbar-fill" :style="progressStyle" />
        </div>
        <div class="time-row">
          <span>{{ formatTime(player.chapterElapsed) }}</span>
          <span>{{ durationLabel }}</span>
        </div>
        <p v-if="!canSeek" class="muted seek-hint">时长计算中，暂不可跳转</p>
      </div>

      <div class="controls controls-row">
        <div class="controls-side controls-side-left">
        <div
          ref="chapterPopoverEl"
          class="player-popover-wrap"
          @pointerenter="onChapterPointerEnter"
          @pointerleave="onChapterPointerLeave"
        >
          <button
            class="chip chapter-btn"
            type="button"
            aria-label="章节"
            :aria-expanded="chapterPopoverOpen ? 'true' : 'false'"
            @click.stop="toggleChapterPopover"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
              <path d="M5 6h14v2H5V6Zm0 5h14v2H5v-2Zm0 5h10v2H5v-2Z" />
            </svg>
          </button>

          <div
            v-if="chapterPopoverOpen"
            class="player-popover chapter-popover"
            role="dialog"
            aria-label="章节列表"
          >
            <div class="player-chapter-page-bar">
              <button
                class="player-chapter-page-trigger"
                type="button"
                aria-haspopup="listbox"
                :aria-expanded="chapterPageMenuOpen ? 'true' : 'false'"
                @click.stop="toggleChapterPageMenu"
              >
                {{ chapterPageTriggerLabel }}
              </button>
              <div
                v-if="chapterPageMenuOpen"
                class="player-chapter-page-menu"
                role="listbox"
              >
                <button
                  v-for="opt in chapterPageOptions"
                  :key="opt.index"
                  type="button"
                  class="player-chapter-page-option"
                  :class="{ active: opt.index === chapterPageIndex }"
                  role="option"
                  :aria-selected="opt.index === chapterPageIndex"
                  @click.stop="setChapterPage(opt.index)"
                >
                  {{ opt.label }}
                </button>
              </div>
            </div>

            <p v-if="chapterListLoading" class="player-popover-empty">加载章节…</p>
            <p v-else-if="!pagedChapters.length" class="player-popover-empty">暂无章节</p>
            <ul v-else class="player-chapter-list">
              <li v-for="item in pagedChapters" :key="item.chapter.id">
                <button
                  type="button"
                  class="player-chapter-item"
                  :class="{ active: isCurrentChapter(item.chapter) }"
                  @click.stop="selectChapter(item.chapter, item.index)"
                >
                  {{ item.chapter.title || `第 ${item.index + 1} 章` }}
                </button>
              </li>
            </ul>
          </div>
        </div>
        </div>

        <div class="controls-main">
        <button class="ctrl" type="button" :disabled="!player.canPrev || player.loading" aria-label="上一段" @click="player.prev()">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true">
            <path d="M8 6H6v12h2V6Zm10 .5L11.5 12 18 17.5v-11Z" />
          </svg>
        </button>
        <button
          class="ctrl main"
          type="button"
          :disabled="player.loading && !player.objectUrl"
          :aria-label="player.playing ? '暂停' : '播放'"
          @click="player.toggle()"
        >
          <svg v-if="player.playing" viewBox="0 0 24 24" width="28" height="28" fill="currentColor" aria-hidden="true">
            <rect x="6" y="5" width="4" height="14" rx="1" />
            <rect x="14" y="5" width="4" height="14" rx="1" />
          </svg>
          <svg v-else viewBox="0 0 24 24" width="28" height="28" fill="currentColor" aria-hidden="true">
            <path d="M8 5.5v13l11-6.5-11-6.5Z" />
          </svg>
        </button>
        <button class="ctrl" type="button" :disabled="!player.canAdvance || player.loading" aria-label="下一段" @click="player.next()">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true">
            <path d="M16 6h2v12h-2V6ZM6 6.5v11L14.5 12 6 6.5Z" />
          </svg>
        </button>
        </div>

        <div class="controls-side controls-side-right">
        <div
          ref="speedPopoverEl"
          class="player-popover-wrap"
          @pointerenter="onSpeedPointerEnter"
          @pointerleave="onSpeedPointerLeave"
        >
          <button
            class="chip speed-btn"
            type="button"
            :aria-expanded="speedPopoverOpen ? 'true' : 'false'"
            aria-label="播放倍速"
            @click.stop="toggleSpeedPopover"
          >
            {{ player.speed }}x
          </button>
          <div
            v-if="speedPopoverOpen"
            class="player-popover speed-popover"
            role="listbox"
            aria-label="倍速选择"
          >
            <button
              v-for="rate in speedOptions"
              :key="rate"
              type="button"
              class="speed-option"
              :class="{ active: Number(player.speed) === Number(rate) }"
              role="option"
              :aria-selected="Number(player.speed) === Number(rate)"
              @click.stop="selectSpeed(rate)"
            >
              {{ rate }}x
            </button>
          </div>
        </div>
        </div>
      </div>

      <p v-if="localError || player.error" class="form-error center">
        {{ localError || player.error }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.seekbar-track.is-disabled {
  cursor: not-allowed;
  opacity: 0.65;
}
.seek-hint {
  margin: 0;
  font-size: 12px;
}
</style>
