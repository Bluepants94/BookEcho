import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { fetchBook, getProgress, listCachedChapterIds, routerPush, resumeFromServer, unlockAutoplay } = vi.hoisted(() => ({
  fetchBook: vi.fn(),
  getProgress: vi.fn(),
  listCachedChapterIds: vi.fn(),
  routerPush: vi.fn(),
  resumeFromServer: vi.fn().mockResolvedValue(),
  unlockAutoplay: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'book-1' } }),
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('@/stores/books', () => ({
  useBooksStore: () => ({
    currentBook: { id: 'book-1', title: '测试书籍' },
    chapters: [{ id: 'chapter-1', title: '未缓存章节' }],
    fetchBook,
  }),
}))

vi.mock('@/stores/player', () => ({
  usePlayerStore: () => ({
    bookId: null,
    chapterId: null,
    bookTitle: '',
    chapterTitle: '',
    hasTrack: false,
    unlockAutoplay,
    resumeFromServer,
  }),
}))

vi.mock('@/api/client', () => ({
  booksApi: { remove: vi.fn() },
  playbackApi: { getProgress },
}))

vi.mock('@/utils/audioCache', () => ({ listCachedChapterIds }))
vi.mock('@/utils/ttsSettings', () => ({ getTtsCacheFingerprint: () => 'tts-fingerprint' }))

import BookDetailView from '../BookDetailView.vue'

describe('BookDetailView', () => {
  let wrapper

  beforeEach(() => {
    vi.clearAllMocks()
    fetchBook.mockResolvedValue()
    getProgress.mockResolvedValue(null)
    listCachedChapterIds.mockReturnValue([])
    resumeFromServer.mockResolvedValue()
    wrapper = mount(BookDetailView, {
      global: {
        stubs: {
          PageHeader: true,
          LoadingState: true,
          EmptyState: true,
        },
      },
    })
  })

  afterEach(() => {
    wrapper?.unmount()
  })

  it('clicking an uncached chapter navigates immediately and starts autoplay open in the background', async () => {
    let resolveResume
    resumeFromServer.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveResume = resolve
        }),
    )
    await flushPromises()

    await wrapper.get('[data-chapter-id="chapter-1"]').trigger('click')
    await flushPromises()

    // Route must not wait for TTS/audio readiness.
    expect(routerPush).toHaveBeenCalledWith({
      name: 'player',
      params: { bookId: 'book-1', chapterId: 'chapter-1' },
      query: { autoplay: '1' },
    })
    expect(unlockAutoplay).toHaveBeenCalledTimes(1)
    expect(resumeFromServer).toHaveBeenCalledWith(
      'book-1',
      'chapter-1',
      expect.objectContaining({
        bookTitle: '测试书籍',
        chapterTitle: '未缓存章节',
        autoplay: true,
      }),
    )
    // Gesture unlock must happen before any async resume work starts.
    expect(unlockAutoplay.mock.invocationCallOrder[0]).toBeLessThan(
      resumeFromServer.mock.invocationCallOrder[0],
    )

    resolveResume()
    await flushPromises()
  })
})
