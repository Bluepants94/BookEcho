import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { router, synthesize, getCachedAudio, setCachedAudio } = vi.hoisted(() => ({
  router: {
    currentRoute: { value: { fullPath: '/' } },
    replace: vi.fn().mockResolvedValue(),
  },
  synthesize: vi.fn(),
  getCachedAudio: vi.fn(),
  setCachedAudio: vi.fn(),
}))

vi.mock('@/router', () => ({ default: router }))
vi.mock('@/api/client', () => ({
  booksApi: {
    chapters: vi.fn(),
    segments: vi.fn(),
  },
  playbackApi: {
    getProgress: vi.fn(),
    putProgress: vi.fn(),
  },
  ttsApi: {
    synthesize,
  },
}))
vi.mock('@/utils/audioCache', () => ({
  getCachedAudio,
  setCachedAudio,
  pruneChaptersOutsideWindow: vi.fn(),
  chapterCachePrefix: vi.fn(() => 'test-prefix'),
}))
vi.mock('@/utils/ttsSettings', () => ({
  getTtsCacheFingerprint: vi.fn(() => 'test-fingerprint'),
  loadCacheSettings: vi.fn(() => ({ cache_chapters: 0, max_cached_segments: 1 })),
  loadTtsSettings: vi.fn(() => ({
    base_url: 'https://tts.example.test',
    api_key: 'test-key',
    model: 'reader',
    voice: 'voice-1',
    speed: 1.75,
    provider: 'openai',
    style: '',
    audio_format: 'wav',
  })),
}))

import { usePlayerStore } from './player'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('player chapter auto-advance', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    router.currentRoute.value = { fullPath: '/' }
    router.replace.mockClear()
    synthesize.mockReset()
    getCachedAudio.mockReset()
    getCachedAudio.mockResolvedValue(null)
    setCachedAudio.mockReset()
    setCachedAudio.mockResolvedValue()
  })

  it('replaces the player route before the next chapter finishes opening', async () => {
    const player = usePlayerStore()
    const opening = deferred()
    player.bookId = 'book-1'
    player.bookTitle = 'Example book'
    player.chapterId = 'chapter-1'
    player.chapterOrderIndex = 0
    player.chapterList = [
      { id: 'chapter-1', title: 'One', index: 0 },
      { id: 'chapter-2', title: 'Two', index: 1 },
    ]
    player.open = vi.fn(() => opening.promise)

    const advancing = player.playNextChapter({ autoplay: true })

    try {
      await vi.waitFor(() => {
        expect(router.replace).toHaveBeenCalledWith('/player/book-1/chapter-2')
      })
      expect(player.open).toHaveBeenCalledWith(expect.objectContaining({
        chapterId: 'chapter-2',
        autoplay: true,
      }))
    } finally {
      opening.resolve()
    }

    await expect(advancing).resolves.toBe(true)
  })

  it('stops autoplay continuity and surfaces a route-replace failure after waiting for open', async () => {
    const player = usePlayerStore()
    const opening = deferred()
    const openError = new Error('章节加载失败')
    const routeError = new Error('无法进入下一章')
    player.bookId = 'book-1'
    player.bookTitle = 'Example book'
    player.chapterId = 'chapter-1'
    player.chapterOrderIndex = 0
    player.chapterList = [
      { id: 'chapter-1', title: 'One', index: 0 },
      { id: 'chapter-2', title: 'Two', index: 1 },
    ]
    player.open = vi.fn(() => opening.promise)
    router.replace.mockRejectedValue(routeError)

    const advancing = player.playNextChapter({ autoplay: true })
    await vi.waitFor(() => {
      expect(router.replace).toHaveBeenCalledWith('/player/book-1/chapter-2')
    })
    opening.reject(openError)

    await expect(advancing).rejects.toBe(routeError)
    expect(player.autoplayContinuity).toBe(false)
    expect(player.error).toBe('无法进入下一章')
  })

  it('always sends the fixed 1x synthesis speed', async () => {
    const player = usePlayerStore()
    const buildTtsBody = vi.spyOn(player, 'buildTtsBody')
    synthesize.mockResolvedValue({
      blob: vi.fn().mockResolvedValue(new Blob(['audio'], { type: 'audio/wav' })),
      headers: { get: vi.fn(() => 'audio/wav') },
    })

    await player.fetchSegmentBlob(0, {
      bookId: 'book-1',
      chapterId: 'chapter-1',
      segments: [{ id: 'segment-1', text: 'Hello' }],
    })

    expect(synthesize).toHaveBeenCalledWith(expect.objectContaining({
      speed: 1,
    }))
    expect(buildTtsBody).toHaveBeenCalledWith(0, expect.objectContaining({
      ttsSnapshot: expect.objectContaining({ speed: 1.75 }),
    }))
  })
})
