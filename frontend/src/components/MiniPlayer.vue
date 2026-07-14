<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '@/stores/player'
import { formatTime } from '@/utils/format'

const player = usePlayerStore()
const router = useRouter()

const waitingForAudio = computed(() => {
  if (player.objectUrl) return false
  return Boolean(
    player.chapterOpening ||
      player.audioLoading ||
      player.loading ||
      player.autoplayContinuity,
  )
})

function openPlayer() {
  if (!player.bookId || !player.chapterId) return
  router.push(`/player/${player.bookId}/${player.chapterId}`)
}
</script>

<template>
  <div class="mini-player" role="button" tabindex="0" @click="openPlayer" @keydown.enter="openPlayer">
    <div class="mini-cover" aria-hidden="true">
      <div class="wave">
        <i /><i /><i /><i />
      </div>
    </div>
    <div class="mini-meta">
      <div class="mini-title">{{ player.chapterTitle || '正在播放' }}</div>
      <div class="mini-sub">
        {{ formatTime(player.chapterElapsed) }}
        <template v-if="player.chapterDuration"> / {{ formatTime(player.chapterDuration) }}</template>
      </div>
    </div>
    <button
      class="mini-btn"
      type="button"
      :disabled="waitingForAudio"
      :aria-label="waitingForAudio ? '音频加载中' : player.playing ? '暂停' : '播放'"
      :aria-busy="waitingForAudio ? 'true' : 'false'"
      @click.stop="player.toggle()"
    >
      <span v-if="waitingForAudio" class="mini-loading-spinner" role="status" aria-label="音频加载中" />
      <svg v-else-if="player.playing" viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
        <rect x="6" y="5" width="4" height="14" rx="1" />
        <rect x="14" y="5" width="4" height="14" rx="1" />
      </svg>
      <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
        <path d="M8 5.5v13l11-6.5-11-6.5Z" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.mini-btn:disabled {
  opacity: 0.85;
  cursor: wait;
}
.mini-loading-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: mini-loading-spin 0.8s linear infinite;
}
@keyframes mini-loading-spin {
  to { transform: rotate(360deg); }
}
</style>
