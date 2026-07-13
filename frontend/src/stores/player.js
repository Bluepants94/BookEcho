import { defineStore } from 'pinia'
import { booksApi, playbackApi, ttsApi } from '@/api/client'
import {
  getCachedAudio,
  setCachedAudio,
  pruneChaptersOutsideWindow,
  chapterCachePrefix,
} from '@/utils/audioCache'
import {
  getTtsCacheFingerprint,
  loadTtsSettings,
  loadCacheSettings,
} from '@/utils/ttsSettings'
import { normalizeList } from '@/utils/format'

export const SPEEDS = [0.75, 1, 1.25, 1.5, 2]

/** Safari needs a real audio/* MIME; empty/octet-stream blobs often fail to decode. */
function asPlayableAudioBlob(blob, preferredFormat = '') {
  if (!blob) return blob
  const current = String(blob.type || '').toLowerCase()
  if (current.startsWith('audio/')) return blob
  const fmt = String(preferredFormat || '').toLowerCase()
  const mimeByFormat = {
    mp3: 'audio/mpeg',
    mpeg: 'audio/mpeg',
    wav: 'audio/wav',
    wave: 'audio/wav',
    pcm16: 'audio/wav',
    pcm: 'audio/wav',
    ogg: 'audio/ogg',
    opus: 'audio/ogg',
    m4a: 'audio/mp4',
    mp4: 'audio/mp4',
    aac: 'audio/aac',
  }
  const mime = mimeByFormat[fmt] || 'audio/mpeg'
  try {
    return new Blob([blob], { type: mime })
  } catch {
    return blob
  }
}

function configureSafariAudioElement(audio) {
  if (!audio) return audio
  try {
    audio.setAttribute('playsinline', 'true')
    audio.setAttribute('webkit-playsinline', 'true')
    audio.playsInline = true
  } catch {
    // ignore
  }
  try {
    audio.preload = 'auto'
    // Helps iOS keep the media pipeline ready for chained segment playback.
    audio.setAttribute('preload', 'auto')
  } catch {
    // ignore
  }
  return audio
}

export const usePlayerStore = defineStore('player', {
  state: () => ({
    bookId: null,
    chapterId: null,
    bookTitle: '',
    chapterTitle: '',
    /** Ordered chapter list for the active book: { id, title, index } */
    chapterList: [],
    chapterOrderIndex: -1,
    segments: [],
    /** Known per-segment durations (seconds); 0 means unknown. */
    segmentDurations: [],
    segmentIndex: 0,
    currentTime: 0,
    /** Current segment duration (internal clock); UI uses chapterDuration. */
    duration: 0,
    playing: false,
    loading: false,
    /** True while chapter text/segments are being fetched in open(). */
    chapterOpening: false,
    /** True while a segment audio blob is being synthesized/loaded. */
    audioLoading: false,
    error: '',
    speed: 1,
    audio: null,
    objectUrl: '',
    prefetching: new Set(),
    progressTimer: null,
    resumeOffset: 0,
    /** True after user explicitly starts playback in this session. */
    userStartedPlayback: false,
    /** True while chapter autoplay continuity is in progress (next-chapter open). */
    autoplayContinuity: false,
    /** Bumped on every open() — stale open/load results must ignore play. */
    sessionId: 0,
    /** Bumped on every loadSegment() — stale async blob loads must not apply. */
    loadToken: 0,
    /** Bumped on stopHard/loadSegment — stale ended/play/pause/error must ignore. */
    mediaGeneration: 0,
    /** Active play() promise generation guard against double-play races. */
    playGeneration: 0,
    /** Bumped to cancel in-flight chapter-window cache jobs. */
    cacheJobToken: 0,
    chapterCacheRunning: false,
    /** Prevents concurrent ended/next handlers from double-advancing. */
    advanceLock: false,
  }),
  getters: {
    hasTrack: (s) => Boolean(s.bookId && s.chapterId),
    currentSegment: (s) => s.segments[s.segmentIndex] || null,
    canPrev: (s) => s.segmentIndex > 0,
    canNext: (s) => s.segmentIndex < s.segments.length - 1,
    hasNextChapter: (s) => {
      if (!Array.isArray(s.chapterList) || !s.chapterList.length) return false
      const idx =
        s.chapterOrderIndex >= 0
          ? s.chapterOrderIndex
          : s.chapterList.findIndex((c) => String(c.id) === String(s.chapterId))
      return idx >= 0 && idx + 1 < s.chapterList.length
    },
    canAdvance: (s) => {
      if (s.segmentIndex < s.segments.length - 1) return true
      if (!Array.isArray(s.chapterList) || !s.chapterList.length) return false
      const idx =
        s.chapterOrderIndex >= 0
          ? s.chapterOrderIndex
          : s.chapterList.findIndex((c) => String(c.id) === String(s.chapterId))
      return idx >= 0 && idx + 1 < s.chapterList.length
    },
    chapterDuration: (s) => {
      if (!Array.isArray(s.segmentDurations) || !s.segmentDurations.length) return 0
      let total = 0
      for (const raw of s.segmentDurations) {
        const d = Number(raw)
        if (d > 0 && Number.isFinite(d)) total += d
      }
      return total
    },
    chapterElapsed: (s) => {
      let elapsed = 0
      const idx = Number(s.segmentIndex) || 0
      if (Array.isArray(s.segmentDurations)) {
        for (let i = 0; i < idx; i += 1) {
          const d = Number(s.segmentDurations[i])
          if (d > 0 && Number.isFinite(d)) elapsed += d
        }
      }
      elapsed += Number(s.currentTime) || 0
      return elapsed
    },
    progressPercent: (s) => {
      let total = 0
      if (Array.isArray(s.segmentDurations)) {
        for (const raw of s.segmentDurations) {
          const d = Number(raw)
          if (d > 0 && Number.isFinite(d)) total += d
        }
      }
      if (!(total > 0)) return 0
      let elapsed = 0
      const idx = Number(s.segmentIndex) || 0
      if (Array.isArray(s.segmentDurations)) {
        for (let i = 0; i < idx; i += 1) {
          const d = Number(s.segmentDurations[i])
          if (d > 0 && Number.isFinite(d)) elapsed += d
        }
      }
      elapsed += Number(s.currentTime) || 0
      return Math.max(0, Math.min(100, (elapsed / total) * 100))
    },
    speeds: () => SPEEDS,
  },
  actions: {
    applyPlaybackRate(audio = this.audio) {
      if (!audio) return
      const rate = Number(this.speed) || 1
      this.speed = rate
      try {
        // Safari may ignore playbackRate until defaultPlaybackRate is aligned.
        audio.defaultPlaybackRate = rate
      } catch {
        // ignore
      }
      try {
        audio.playbackRate = rate
      } catch {
        // ignore
      }
      // Some WebKit builds only apply rate after a microtask / while playing.
      if (typeof queueMicrotask === 'function') {
        queueMicrotask(() => {
          try {
            if (audio.defaultPlaybackRate !== rate) audio.defaultPlaybackRate = rate
            if (audio.playbackRate !== rate) audio.playbackRate = rate
          } catch {
            // ignore
          }
        })
      }
    },

    resetSegmentDurations(length = 0) {
      const n = Math.max(0, Number(length) || 0)
      this.segmentDurations = Array.from({ length: n }, () => 0)
    },

    setSegmentDuration(index, seconds) {
      const i = Number(index)
      const d = Number(seconds)
      if (!Number.isInteger(i) || i < 0) return
      if (!(d > 0) || !Number.isFinite(d)) return
      if (!Array.isArray(this.segmentDurations) || i >= this.segmentDurations.length) return
      const prev = Number(this.segmentDurations[i]) || 0
      if (prev > 0 && Math.abs(prev - d) < 0.05) return
      this.segmentDurations.splice(i, 1, d)
    },

    /**
     * Read duration from a blob via a temporary Audio element.
     * Always cleans up object URL; returns 0 on failure.
     */
    probeBlobDuration(blob) {
      return new Promise((resolve) => {
        if (!blob) {
          resolve(0)
          return
        }
        let settled = false
        let url = ''
        const audio = new Audio()
        const finish = (value) => {
          if (settled) return
          settled = true
          try {
            audio.removeAttribute('src')
            audio.src = ''
            audio.load()
          } catch {
            // ignore
          }
          if (url) {
            try {
              URL.revokeObjectURL(url)
            } catch {
              // ignore
            }
          }
          const d = Number(value)
          resolve(d > 0 && Number.isFinite(d) ? d : 0)
        }
        audio.preload = 'metadata'
        audio.addEventListener('loadedmetadata', () => finish(audio.duration))
        audio.addEventListener('error', () => finish(0))
        window.setTimeout(() => finish(0), 8000)
        try {
          url = URL.createObjectURL(blob)
          audio.src = url
        } catch {
          finish(0)
        }
      })
    },

    async rememberSegmentDuration(index, blob, { sessionId = this.sessionId } = {}) {
      if (!blob) return
      const d = await this.probeBlobDuration(blob)
      if (sessionId != null && sessionId !== this.sessionId) return
      if (d > 0) this.setSegmentDuration(index, d)
    },

    ensureAudio() {
      if (this.audio) return this.audio
      const audio = configureSafariAudioElement(new Audio())
      this.applyPlaybackRate(audio)

      const syncDurationFromAudio = () => {
        if (audio._mediaGeneration !== this.mediaGeneration) return
        const segDur = Number(audio.duration)
        if (segDur > 0 && Number.isFinite(segDur)) {
          this.duration = segDur
          this.setSegmentDuration(this.segmentIndex, segDur)
        }
      }

      const applyResumeOffset = () => {
        if (audio._mediaGeneration !== this.mediaGeneration) return
        if (!(this.resumeOffset > 0)) return
        const segDur = Number(audio.duration)
        if (segDur > 0 && Number.isFinite(segDur) && this.resumeOffset >= segDur) {
          this.resumeOffset = 0
          return
        }
        try {
          audio.currentTime = this.resumeOffset
          this.currentTime = audio.currentTime || this.resumeOffset
          this.resumeOffset = 0
        } catch {
          // Safari may reject seek until canplay.
        }
      }

      audio.addEventListener('timeupdate', () => {
        if (audio._mediaGeneration !== this.mediaGeneration) return
        this.currentTime = audio.currentTime || 0
        syncDurationFromAudio()
        // Keep rate sticky on iOS while playing.
        const rate = Number(this.speed) || 1
        if (Math.abs((audio.playbackRate || 1) - rate) > 0.01) {
          this.applyPlaybackRate(audio)
        }
      })
      audio.addEventListener('loadedmetadata', () => {
        if (audio._mediaGeneration !== this.mediaGeneration) return
        this.applyPlaybackRate(audio)
        syncDurationFromAudio()
        if (!(Number(audio.duration) > 0)) this.duration = 0
        applyResumeOffset()
      })
      // Safari often reports usable duration only on canplay/durationchange.
      audio.addEventListener('durationchange', () => {
        syncDurationFromAudio()
        applyResumeOffset()
      })
      audio.addEventListener('canplay', () => {
        if (audio._mediaGeneration !== this.mediaGeneration) return
        this.applyPlaybackRate(audio)
        syncDurationFromAudio()
        applyResumeOffset()
      })
      audio.addEventListener('ended', () => {
        if (audio._mediaGeneration !== this.mediaGeneration) return
        this.onEnded(audio._mediaGeneration)
      })
      audio.addEventListener('play', () => {
        if (audio._mediaGeneration !== this.mediaGeneration) return
        this.applyPlaybackRate(audio)
        this.playing = true
      })
      audio.addEventListener('playing', () => {
        if (audio._mediaGeneration !== this.mediaGeneration) return
        this.applyPlaybackRate(audio)
        this.playing = true
      })
      audio.addEventListener('pause', () => {
        if (audio._mediaGeneration !== this.mediaGeneration) return
        this.playing = false
      })
      audio.addEventListener('error', () => {
        if (audio._mediaGeneration !== this.mediaGeneration) return
        // Ignore errors from hard-stopped / emptied sources.
        if (!this.objectUrl || !audio.currentSrc) return
        this.error = '音频加载失败'
        this.playing = false
      })
      this.audio = audio
      return audio
    },

    /**
     * Hard-stop the singleton Audio: pause, reset clock, drop src, free object URL.
     * Prevents overlapping playback when switching book/chapter/segment.
     */
    stopHard() {
      // Invalidate all media event handlers / ended callbacks from previous source.
      this.mediaGeneration += 1
      this.playGeneration += 1
      const audio = this.audio
      if (audio) {
        // Keep teardown events STALE — never assign the live generation here.
        // Only loadSegment assigns audio._mediaGeneration when a new src is attached.
        audio._mediaGeneration = this.mediaGeneration - 1
        try {
          audio.pause()
        } catch {
          // ignore
        }
        // Revoke first so emptied/error events see no live object URL.
        if (this.objectUrl) {
          try {
            URL.revokeObjectURL(this.objectUrl)
          } catch {
            // ignore
          }
          this.objectUrl = ''
        }
        try {
          // Clear src and call load() to release old media resource (fix 复读).
          audio.removeAttribute('src')
          audio.src = ''
          audio.load()
        } catch {
          // ignore
        }
        // Never reset this.speed; only re-apply after load() side effects.
        this.applyPlaybackRate(audio)
        try {
          audio.currentTime = 0
        } catch {
          // ignore
        }
      } else if (this.objectUrl) {
        try {
          URL.revokeObjectURL(this.objectUrl)
        } catch {
          // ignore
        }
        this.objectUrl = ''
      }
      this.playing = false
      // Clear audioLoading here so a superseded in-flight loadSegment (whose
      // `token !== this.loadToken` finally no longer runs) cannot leave it stuck.
      this.audioLoading = false
      this.currentTime = 0
      this.duration = 0
    },

    resolveChapterOrderIndex(chapterId, chapterList = this.chapterList) {
      if (!chapterId || !Array.isArray(chapterList) || !chapterList.length) return -1
      return chapterList.findIndex((c) => String(c.id) === String(chapterId))
    },

    async ensureChapterList(bookId, preferredList = null) {
      if (Array.isArray(preferredList) && preferredList.length) {
        this.chapterList = preferredList.map((c, index) => ({
          id: c.id,
          title: c.title || `第 ${index + 1} 章`,
          index,
        }))
        return this.chapterList
      }
      if (
        String(this.bookId) === String(bookId) &&
        Array.isArray(this.chapterList) &&
        this.chapterList.length &&
        this.chapterList.every((c) => c && c.id != null)
      ) {
        return this.chapterList
      }
      try {
        const chapters = normalizeList(await booksApi.chapters(bookId))
        this.chapterList = chapters.map((c, index) => ({
          id: c.id,
          title: c.title || `第 ${index + 1} 章`,
          index,
        }))
      } catch {
        // Keep whatever we have; window cache will no-op without list.
        if (String(this.bookId) !== String(bookId)) this.chapterList = []
      }
      return this.chapterList
    },

    /**
     * Open a chapter for reading / playback preparation.
     * Default autoplay=false: show text + progress position, synthesize only on user play.
     */
    async open({
      bookId,
      chapterId,
      bookTitle = '',
      chapterTitle = '',
      segmentIndex = 0,
      offset = 0,
      autoplay = false,
      chapterList = null,
    }) {
      // New session: invalidate any in-flight open/loadSegment from previous book/chapter.
      const sessionId = ++this.sessionId
      this.loadToken += 1
      this.cacheJobToken += 1

      this.stopHard()
      this.stopProgressSync()
      this.prefetching = new Set()
      // Autoplay continuity: set intent immediately so PlayerView bootstrap
      // cannot clobber with resumeFromServer(autoplay:false) during async fetch.
      this.userStartedPlayback = Boolean(autoplay)
      if (!autoplay) this.autoplayContinuity = false
      this.chapterCacheRunning = false
      this.advanceLock = false

      this.bookId = bookId
      this.chapterId = chapterId
      this.bookTitle = bookTitle
      this.chapterTitle = chapterTitle
      this.segments = []
      this.segmentDurations = []
      this.segmentIndex = Number(segmentIndex) || 0
      this.resumeOffset = Number(offset) || 0
      this.error = ''
      this.loading = true
      this.chapterOpening = true

      try {
        await this.ensureChapterList(bookId, chapterList)
        if (sessionId !== this.sessionId) return

        this.chapterOrderIndex = this.resolveChapterOrderIndex(chapterId)
        if (!chapterTitle && this.chapterOrderIndex >= 0) {
          this.chapterTitle = this.chapterList[this.chapterOrderIndex]?.title || chapterTitle
        }

        const segs = await booksApi.segments(bookId, chapterId)
        if (sessionId !== this.sessionId) return

        this.segments = normalizeList(segs)
        this.resetSegmentDurations(this.segments.length)
        this.chapterOpening = false
        if (!this.segments.length) {
          throw new Error('本章暂无可用段落')
        }
        if (this.segmentIndex >= this.segments.length) this.segmentIndex = 0

        if (autoplay) {
          this.userStartedPlayback = true
          await this.loadSegment(this.segmentIndex, true)
          if (sessionId !== this.sessionId) return
          // Successful attach/play attempt ends continuity intent.
          if (this.objectUrl) this.autoplayContinuity = false
        } else {
          // Prepare reading position only — do not synthesize audio yet.
          this.autoplayContinuity = false
        }
        if (sessionId !== this.sessionId) return
        this.startProgressSync()
        if (autoplay) {
          this.ensureChapterWindowCache()
        }
      } catch (e) {
        if (sessionId !== this.sessionId) return
        this.autoplayContinuity = false
        this.error = e.message || '打开播放器失败'
        throw e
      } finally {
        if (sessionId === this.sessionId) {
          this.loading = false
          this.chapterOpening = false
        }
      }
    },

    async resumeFromServer(bookId, chapterId, meta = {}) {
      let progress = null
      try {
        // Fetch book-level progress (backend may fall back across chapters).
        progress = await playbackApi.getProgress(bookId, chapterId)
      } catch {
        progress = null
      }

      // Progress is per-book: only restore segment/offset when chapter matches.
      const progressChapterId = progress?.chapter_id
      const chapterMatches =
        progressChapterId != null && String(progressChapterId) === String(chapterId)

      const segmentIndex = chapterMatches ? Number(progress?.segment_index) || 0 : 0
      const offset = chapterMatches
        ? Number(
            progress?.position_seconds ??
              progress?.offset_seconds ??
              progress?.position ??
              0,
          ) || 0
        : 0

      return this.open({
        bookId,
        chapterId,
        bookTitle: meta.bookTitle || '',
        chapterTitle: meta.chapterTitle || (chapterMatches ? progress?.chapter_title : '') || '',
        segmentIndex,
        offset,
        autoplay: meta.autoplay === true ? true : false,
        chapterList: meta.chapterList || null,
      })
    },

    buildTtsBody(segmentIndex, { bookId, chapterId, segments, text, ttsSnapshot = loadTtsSettings() } = {}) {
      const tts = ttsSnapshot
      const segs = segments || this.segments
      const segment = segs[segmentIndex]
      return {
        book_id: bookId ?? this.bookId,
        chapter_id: chapterId ?? this.chapterId,
        segment_index: segmentIndex,
        segment_id: segment?.id,
        text: text ?? segment?.text,
        base_url: tts.base_url,
        api_key: tts.api_key,
        model: tts.model,
        voice: tts.voice,
        speed: 1,
        provider: tts.provider,
        style: tts.style,
        audio_format: tts.audio_format,
      }
    },

    /**
     * Fetch / synthesize one segment blob.
     * Fingerprint is fixed before synthesis; cache write only if fingerprint still matches
     * and (for current-session paths) session is still valid.
     */
    async fetchSegmentBlob(segmentIndex, options = {}) {
      const bookId = options.bookId ?? this.bookId
      const chapterId = options.chapterId ?? this.chapterId
      const segments = options.segments || this.segments
      const sessionId = options.sessionId ?? this.sessionId
      // Freeze TTS settings + fingerprint at synthesize-start so cache key matches body.
      const ttsSnapshot = loadTtsSettings()
      const fingerprint = getTtsCacheFingerprint(ttsSnapshot)
      const body = this.buildTtsBody(segmentIndex, {
        bookId,
        chapterId,
        segments,
        text: options.text,
        ttsSnapshot,
      })

      const cached = await getCachedAudio(fingerprint, bookId, chapterId, segmentIndex)
      if (cached) return asPlayableAudioBlob(cached, body.audio_format)

      if (!body.text && !body.segment_id) {
        throw new Error('段落内容为空')
      }
      if (!body.base_url && !body.api_key && !body.model) {
        // Unconfigured TTS — let caller surface error on explicit play.
        throw new Error('请先在设置中配置 TTS API')
      }

      const res = await ttsApi.synthesize(body)
      const rawBlob = await res.blob()
      const headerType = String(res.headers?.get?.('content-type') || '').split(';')[0].trim()
      let blob = rawBlob
      if (headerType.startsWith('audio/') && (!rawBlob.type || rawBlob.type === 'application/octet-stream')) {
        try {
          blob = new Blob([rawBlob], { type: headerType })
        } catch {
          blob = rawBlob
        }
      }
      blob = asPlayableAudioBlob(blob, body.audio_format)

      // Race guard: write only when fingerprint still matches AND session/token still valid.
      const stillSameFingerprint = fingerprint === getTtsCacheFingerprint()
      const stillSameSession = sessionId === this.sessionId
      const stillSameBook = String(this.bookId) === String(bookId)
      const chapterOk =
        options.allowOtherChapter || options.forPrefetch
          ? true
          : String(this.chapterId) === String(chapterId)

      if (stillSameFingerprint && stillSameSession && stillSameBook && chapterOk) {
        const cacheCfg = loadCacheSettings()
        const protect = this.windowProtectPrefixes(fingerprint, bookId)
        await setCachedAudio(fingerprint, bookId, chapterId, segmentIndex, blob, {
          maxSegments: cacheCfg.max_cached_segments,
          protectPrefixes: protect,
        })
      }

      return blob
    },

    windowProtectPrefixes(fingerprint, bookId) {
      const cfg = loadCacheSettings()
      const idx = this.chapterOrderIndex
      const list = this.chapterList || []
      if (idx < 0 || !list.length) return []
      // Window: current ± cache_chapters (forward + already-played).
      const start = Math.max(0, idx - cfg.cache_chapters)
      const end = Math.min(list.length - 1, idx + cfg.cache_chapters)
      const prefixes = []
      for (let i = start; i <= end; i += 1) {
        const ch = list[i]
        if (ch?.id != null) prefixes.push(chapterCachePrefix(fingerprint, bookId, ch.id))
      }
      return prefixes
    },

    targetChapterIdsForWindow() {
      const cfg = loadCacheSettings()
      const idx = this.chapterOrderIndex
      const list = this.chapterList || []
      if (idx < 0 || !list.length) return []
      // Window: current ± cache_chapters (forward + already-played).
      const start = Math.max(0, idx - cfg.cache_chapters)
      const end = Math.min(list.length - 1, idx + cfg.cache_chapters)
      const ids = []
      for (let i = start; i <= end; i += 1) {
        if (list[i]?.id != null) ids.push(list[i].id)
      }
      return ids
    },

    /**
     * Chapter-window prune window: current ± cache_chapters (default 3).
     * Prefetch order remains forward-only (current + next 1..N).
     * Triggered after user clicks play. Serial TTS to avoid flooding the API.
     */
    async ensureChapterWindowCache() {
      if (!this.bookId || !this.userStartedPlayback) return
      if (!this.chapterList?.length || this.chapterOrderIndex < 0) return

      const jobToken = ++this.cacheJobToken
      const sessionId = this.sessionId
      const bookId = this.bookId
      const fingerprint = getTtsCacheFingerprint()
      const keepIds = this.targetChapterIdsForWindow()
      if (!keepIds.length) return

      this.chapterCacheRunning = true
      try {
        try {
          await pruneChaptersOutsideWindow(fingerprint, bookId, keepIds)
        } catch {
          // ignore prune failures
        }
        if (jobToken !== this.cacheJobToken || sessionId !== this.sessionId) return

        // Order: current chapter first, then next 1..N.
        const cfg = loadCacheSettings()
        const idx = this.chapterOrderIndex
        const list = this.chapterList
        const ordered = []
        // current
        if (list[idx]) ordered.push(list[idx])
        // next 1..N
        for (let d = 1; d <= cfg.cache_chapters; d += 1) {
          if (list[idx + d]) ordered.push(list[idx + d])
        }

        for (const chapter of ordered) {
          if (jobToken !== this.cacheJobToken || sessionId !== this.sessionId) return
          if (String(this.bookId) !== String(bookId)) return
          if (fingerprint !== getTtsCacheFingerprint()) return

          let segs = []
          try {
            if (String(chapter.id) === String(this.chapterId) && this.segments.length) {
              segs = this.segments
            } else {
              segs = normalizeList(await booksApi.segments(bookId, chapter.id))
            }
          } catch {
            continue
          }

          for (let i = 0; i < segs.length; i += 1) {
            if (jobToken !== this.cacheJobToken || sessionId !== this.sessionId) return
            if (String(this.bookId) !== String(bookId)) return
            if (fingerprint !== getTtsCacheFingerprint()) return

            const key = `${fingerprint}|${bookId}:${chapter.id}:${i}`
            if (this.prefetching.has(key)) continue
            this.prefetching.add(key)
            try {
              // Silent on failure (e.g. missing API) — play path will surface errors.
              const blob = await this.fetchSegmentBlob(i, {
                bookId,
                chapterId: chapter.id,
                segments: segs,
                sessionId,
                requireSession: true,
                forPrefetch: true,
                allowOtherChapter: true,
                text: segs[i]?.text,
              })
              if (
                blob &&
                sessionId === this.sessionId &&
                String(chapter.id) === String(this.chapterId)
              ) {
                await this.rememberSegmentDuration(i, blob, { sessionId })
              }
            } catch {
              // silent for prefetch
            } finally {
              this.prefetching.delete(key)
            }
          }
        }
      } finally {
        if (jobToken === this.cacheJobToken) this.chapterCacheRunning = false
      }
    },

    async loadSegment(index, autoplay = false) {
      if (index < 0 || index >= this.segments.length) return

      const sessionId = this.sessionId
      const token = ++this.loadToken

      // Stop previous source before any async work so rapid switches never overlap.
      // stopHard() also bumps mediaGeneration so stale ended cannot double-advance.
      this.stopHard()
      const mediaGen = this.mediaGeneration
      this.segmentIndex = index
      this.loading = true
      this.audioLoading = true
      this.error = ''

      try {
        let blob = await this.fetchSegmentBlob(index, { sessionId, requireSession: true })
        if (token !== this.loadToken || sessionId !== this.sessionId) return
        if (mediaGen !== this.mediaGeneration) return
        if (!blob) throw new Error('音频为空')
        blob = asPlayableAudioBlob(blob, loadTtsSettings().audio_format)

        const audio = this.ensureAudio()
        configureSafariAudioElement(audio)
        // Extra guard before attaching new source (another load may have raced).
        if (this.objectUrl) {
          try {
            URL.revokeObjectURL(this.objectUrl)
          } catch {
            // ignore
          }
          this.objectUrl = ''
        }
        try {
          audio.pause()
        } catch {
          // ignore
        }

        if (token !== this.loadToken || sessionId !== this.sessionId) return
        if (mediaGen !== this.mediaGeneration) return

        // Attach new media under current generation only after previous is fully stopped.
        // Call load() to force browser to release old resource and load new blob.
        this.objectUrl = URL.createObjectURL(blob)
        audio.src = this.objectUrl
        this.applyPlaybackRate(audio)
        // Mark generation live only after src is attached.
        audio._mediaGeneration = mediaGen
        try {
          audio.load()
        } catch {
          // ignore
        }
        // Safari / WebKit often reset playbackRate after src/load changes.
        this.applyPlaybackRate(audio)
        const reinstateRate = () => this.applyPlaybackRate(audio)
        audio.addEventListener('loadedmetadata', reinstateRate, { once: true })
        audio.addEventListener('canplay', reinstateRate, { once: true })
        // Best-effort chapter timeline update from the attached blob.
        this.rememberSegmentDuration(index, blob, { sessionId })

        if (autoplay) {
          if (token !== this.loadToken || sessionId !== this.sessionId) return
          if (mediaGen !== this.mediaGeneration) return
          const playGen = ++this.playGeneration
          try {
            this.applyPlaybackRate(audio)
            await audio.play()
            this.applyPlaybackRate(audio)
            if (
              playGen !== this.playGeneration ||
              token !== this.loadToken ||
              sessionId !== this.sessionId ||
              mediaGen !== this.mediaGeneration
            ) {
              try {
                audio.pause()
              } catch {
                // ignore
              }
              return
            }
            this.userStartedPlayback = true
            this.autoplayContinuity = false
          } catch {
            if (
              token === this.loadToken &&
              sessionId === this.sessionId &&
              mediaGen === this.mediaGeneration
            ) {
              this.playing = false
              // Interruption / autoplay block — do not leave continuity stuck forever.
              // Keep userStartedPlayback true so user can retry with toggle.
            }
          }
        }

        if (token !== this.loadToken || sessionId !== this.sessionId) return
        if (mediaGen !== this.mediaGeneration) return
        if (this.userStartedPlayback) {
          // Lightweight same-chapter tail prefetch while chapter window runs.
          this.prefetchAhead()
          this.ensureChapterWindowCache()
        }
        this.saveProgress(true)
      } catch (e) {
        if (token !== this.loadToken || sessionId !== this.sessionId) return
        if (mediaGen !== this.mediaGeneration) return
        this.error = e.message || '合成语音失败，请检查 API 设置'
        this.playing = false
        this.autoplayContinuity = false
      } finally {
        if (token === this.loadToken && sessionId === this.sessionId) {
          this.loading = false
          this.audioLoading = false
        }
      }
    },

    prefetchAhead() {
      const fingerprint = getTtsCacheFingerprint()
      const bookId = this.bookId
      const chapterId = this.chapterId
      const sessionId = this.sessionId
      const targets = [1, 2]
        .map((d) => this.segmentIndex + d)
        .filter((i) => i < this.segments.length)
      targets.forEach((i) => {
        const key = `${fingerprint}|${bookId}:${chapterId}:${i}`
        if (this.prefetching.has(key)) return
        this.prefetching.add(key)
        this.fetchSegmentBlob(i, { sessionId, requireSession: true, forPrefetch: true })
          .then((blob) => this.rememberSegmentDuration(i, blob, { sessionId }))
          .catch(() => {})
          .finally(() => this.prefetching.delete(key))
      })
    },

    async toggle() {
      const audio = this.ensureAudio()
      // HTMLAudioElement.src returns document URL when attribute is empty — use objectUrl/currentSrc.
      if (!this.objectUrl || !audio.currentSrc) {
        this.userStartedPlayback = true
        await this.loadSegment(this.segmentIndex, true)
        return
      }
      if (audio.paused) {
        const mediaGen = this.mediaGeneration
        const playGen = ++this.playGeneration
        try {
          await audio.play()
          if (playGen !== this.playGeneration || mediaGen !== this.mediaGeneration) {
            try {
              audio.pause()
            } catch {
              // ignore
            }
            return
          }
          this.userStartedPlayback = true
          this.ensureChapterWindowCache()
        } catch (e) {
          if (playGen === this.playGeneration && mediaGen === this.mediaGeneration) {
            this.error = e.message || '播放失败'
          }
        }
      } else {
        this.playGeneration += 1
        audio.pause()
        this.saveProgress(true)
      }
    },

    async prev() {
      if (!this.canPrev) return
      this.resumeOffset = 0
      if (!this.userStartedPlayback && !this.objectUrl) {
        // Reading mode: only move text cursor until user presses play.
        this.segmentIndex -= 1
        this.saveProgress(true)
        return
      }
      await this.loadSegment(this.segmentIndex - 1, this.userStartedPlayback || this.playing)
    },

    /**
     * Open the next chapter (chapterOrderIndex + 1) from segment 0.
     * Used by auto-advance on segment end and manual "next" at chapter end.
     * Returns true if a next chapter was opened.
     */
    async playNextChapter({ autoplay = true } = {}) {
      if (!this.bookId) return false
      await this.ensureChapterList(this.bookId)
      const idx =
        this.chapterOrderIndex >= 0
          ? this.chapterOrderIndex
          : this.resolveChapterOrderIndex(this.chapterId)
      if (idx < 0) return false
      const nextChapter = this.chapterList[idx + 1]
      if (!nextChapter?.id) return false

      const shouldAutoplay = Boolean(autoplay)
      const bookId = this.bookId
      const bookTitle = this.bookTitle
      const chapterList = this.chapterList

      // Mark continuity BEFORE open/route replace so PlayerView bootstrap
      // early-returns even while segments are still loading.
      if (shouldAutoplay) {
        this.autoplayContinuity = true
        this.userStartedPlayback = true
      }

      let opening
      try {
        opening = this.open({
          bookId,
          chapterId: nextChapter.id,
          bookTitle,
          chapterTitle: nextChapter.title || '',
          segmentIndex: 0,
          offset: 0,
          autoplay: shouldAutoplay,
          chapterList,
        })
      } catch (e) {
        this.autoplayContinuity = false
        throw e
      }

      // Attach a rejection handler before routing. A route guard may take longer
      // than chapter loading, and the original open() rejection must never become
      // unhandled while navigation is in progress.
      const openingResult = Promise.resolve(opening).then(
        () => ({ ok: true }),
        (error) => ({ ok: false, error }),
      )

      // Sync route as soon as open() has initialized the new chapter state so
      // auto-advance also moves listeners who started from another page.
      // Only a missing router module is non-fatal outside the app; once obtained,
      // a rejected replacement must stop the new audio session and surface an error.
      let router = null
      try {
        ({ default: router } = await import('@/router'))
      } catch {
        // router may be unavailable in non-app contexts
      }

      let routeFailed = false
      let routeError = null
      if (router) {
        const target = `/player/${bookId}/${nextChapter.id}`
        // Silent sync: only update the URL when already on the player page so
        // auto-advance from other pages never hijacks navigation.
        const currentRoute = router.currentRoute?.value
        const isPlayerRoute = currentRoute?.name === 'player'
        if (isPlayerRoute && currentRoute?.fullPath !== target) {
          try {
            await router.replace(target)
          } catch (error) {
            routeFailed = true
            routeError = error
          }
        }
      }

      if (routeFailed) {
        // Invalidate the in-flight open() so its async work aborts early.
        this.sessionId += 1
        this.stopHard()
        this.autoplayContinuity = false
        this.userStartedPlayback = false
        this.error = routeError?.message || '切换章节失败'
        throw routeError
      }

      const result = await openingResult
      if (!result.ok) {
        this.autoplayContinuity = false
        throw result.error
      }
      return true
    },

    async next() {
      if (!this.canNext) {
        // Last segment of chapter: advance to next chapter when available.
        const autoplay = this.userStartedPlayback || this.playing
        const advanced = await this.playNextChapter({ autoplay })
        if (!advanced) this.pause()
        return
      }
      this.resumeOffset = 0
      if (!this.userStartedPlayback && !this.objectUrl) {
        this.segmentIndex += 1
        this.saveProgress(true)
        return
      }
      await this.loadSegment(this.segmentIndex + 1, this.userStartedPlayback || this.playing)
    },

    async onEnded(mediaGeneration = null) {
      // Ignore ended events from discarded / superseded media generations.
      if (mediaGeneration != null && mediaGeneration !== this.mediaGeneration) return
      if (this.loading) return
      if (!this.userStartedPlayback) return
      if (!this.objectUrl || !this.audio?.currentSrc) return
      if (this.audio && this.audio._mediaGeneration !== this.mediaGeneration) return
      // Re-entrancy: concurrent ended handlers must not double-advance.
      if (this.advanceLock) return
      this.advanceLock = true
      // Capture the segment that actually ended so we never reload the same one.
      const endedSegmentIndex = this.segmentIndex
      try {
        if (mediaGeneration != null && mediaGeneration !== this.mediaGeneration) return
        if (this.loading) return
        if (!this.userStartedPlayback) return
        if (this.audio && this.audio._mediaGeneration !== this.mediaGeneration) return
        // If another path already advanced past this segment, do nothing.
        if (this.segmentIndex !== endedSegmentIndex) return

        if (endedSegmentIndex < this.segments.length - 1) {
          this.resumeOffset = 0
          await this.loadSegment(endedSegmentIndex + 1, true)
          return
        }

        // Chapter finished while user was listening → autoplay next chapter from segment 0.
        const advanced = await this.playNextChapter({ autoplay: true })
        if (!advanced) {
          this.autoplayContinuity = false
          this.playing = false
        }
      } catch (err) {
        this.autoplayContinuity = false
        this.playing = false
        this.error = err.message || '播放失败'
      } finally {
        this.advanceLock = false
      }
    },

    pause() {
      this.audio?.pause()
      this.saveProgress(true)
    },

    async seek(ratio) {
      const total = Number(this.chapterDuration) || 0
      if (!(total > 0)) return

      const safeRatio = Math.max(0, Math.min(1, Number(ratio) || 0))
      const target = safeRatio * total
      const shouldPlay = this.userStartedPlayback || this.playing

      let acc = 0
      let targetIndex = null
      let targetOffset = 0
      let lastKnownIndex = -1
      let lastKnownDuration = 0

      for (let i = 0; i < this.segments.length; i += 1) {
        const d = Number(this.segmentDurations[i])
        if (!(d > 0) || !Number.isFinite(d)) break
        lastKnownIndex = i
        lastKnownDuration = d
        if (target <= acc + d + 1e-4) {
          targetIndex = i
          targetOffset = Math.max(0, Math.min(d, target - acc))
          break
        }
        acc += d
      }

      // Unknown tail: land on last known boundary instead of inventing NaN offsets.
      if (targetIndex == null) {
        if (lastKnownIndex >= 0) {
          targetIndex = lastKnownIndex
          targetOffset = lastKnownDuration
        } else {
          targetIndex = this.segmentIndex
          targetOffset = 0
        }
      }

      if (
        targetIndex === this.segmentIndex &&
        this.objectUrl &&
        this.audio?.currentSrc
      ) {
        const audio = this.audio
        const segDur =
          Number(this.segmentDurations[targetIndex]) ||
          Number(audio.duration) ||
          0
        const nextTime =
          segDur > 0
            ? Math.max(0, Math.min(segDur, targetOffset))
            : Math.max(0, targetOffset)
        try {
          audio.currentTime = nextTime
          this.currentTime = audio.currentTime || nextTime
        } catch {
          this.resumeOffset = nextTime
        }
        this.saveProgress(true)
        return
      }

      this.resumeOffset = targetOffset
      await this.loadSegment(targetIndex, shouldPlay)
    },

    setSpeed(speed) {
      this.speed = Number(speed) || 1
      this.applyPlaybackRate(this.audio)
    },

    cycleSpeed() {
      const idx = SPEEDS.indexOf(this.speed)
      const next = SPEEDS[(idx + 1) % SPEEDS.length]
      this.setSpeed(next)
    },

    startProgressSync() {
      this.stopProgressSync()
      this.progressTimer = setInterval(() => {
        if (this.playing) this.saveProgress(false)
      }, 8000)
    },

    stopProgressSync() {
      if (this.progressTimer) {
        clearInterval(this.progressTimer)
        this.progressTimer = null
      }
    },

    async saveProgress(force = false) {
      if (!this.bookId || !this.chapterId) return
      if (!force && !this.playing) return
      try {
        await playbackApi.putProgress({
          book_id: this.bookId,
          chapter_id: this.chapterId,
          segment_index: this.segmentIndex,
          position_seconds: this.currentTime || 0,
        })
      } catch (e) {
        const status = e?.status
        if (status === 401 || status === 403) {
          // client.js already clears token + redirects on 401; surface a light notice too
          this.error = status === 401 ? '登录已过期，请重新登录' : '无权限保存进度，请重新登录'
          return
        }
        // 网络/后端未就绪时静默
      }
    },

    /** After TTS settings change: drop current object URL; user must press play again. */
    async invalidateAfterSettingsChange() {
      const wasPlaying = this.playing
      this.cacheJobToken += 1
      this.stopHard()
      this.userStartedPlayback = false
      this.autoplayContinuity = false
      if (this.segments.length) {
        this.resetSegmentDurations(this.segments.length)
      } else {
        this.segmentDurations = []
      }
      if (wasPlaying && this.segments.length) {
        // Soft reload text position only; do not autoplay with new fingerprint.
        this.error = ''
      }
    },

    dispose() {
      this.sessionId += 1
      this.loadToken += 1
      this.cacheJobToken += 1
      this.playGeneration += 1
      this.advanceLock = false
      this.stopProgressSync()
      this.stopHard()
      this.prefetching = new Set()
      this.userStartedPlayback = false
      this.autoplayContinuity = false
      this.chapterCacheRunning = false
    },
  },
})
