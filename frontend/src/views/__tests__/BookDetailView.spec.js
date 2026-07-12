import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { fetchBook, getProgress, listCachedChapterIds, routerPush } = vi.hoisted(() => ({
  fetchBook: vi.fn(),
  getProgress: vi.fn(),
  listCachedChapterIds: vi.fn(),
  routerPush: vi.fn(),
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

  it('clicking an uncached chapter immediately opens the player with autoplay intent', async () => {
    await flushPromises()

    await wrapper.get('[data-chapter-id="chapter-1"]').trigger('click')

    expect(routerPush).toHaveBeenCalledWith({
      name: 'player',
      params: { bookId: 'book-1', chapterId: 'chapter-1' },
      query: { autoplay: '1' },
    })
  })
})
