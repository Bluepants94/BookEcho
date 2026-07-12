import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  player: {},
  route: {
    params: { bookId: 'book-1', chapterId: 'chapter-1' },
    query: {},
    fullPath: '/player/book-1/chapter-1',
  },
  router: {
    replace: vi.fn().mockResolvedValue(),
    back: vi.fn(),
    push: vi.fn(),
  },
}))
const player = reactive(mocks.player)
mocks.player = player
const { route, router } = mocks

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => router,
}))
vi.mock('@/stores/player', () => ({
  SPEEDS: [1, 1.25, 1.5, 2],
  usePlayerStore: () => mocks.player,
}))
vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({ ttsUpdatedNotice: '', clearTtsNotice: vi.fn() }),
}))
vi.mock('@/api/client', () => ({
  booksApi: {
    get: vi.fn(),
    chapters: vi.fn(),
  },
}))
vi.mock('@/utils/format', () => ({
  formatTime: vi.fn((seconds) => String(seconds ?? 0)),
}))

let PlayerView

beforeAll(async () => {
  PlayerView = (await import('./PlayerView.vue')).default
})

function resetPlayer(overrides = {}) {
  Object.assign(player, {
    bookId: 'book-1',
    chapterId: 'chapter-1',
    bookTitle: 'Example book',
    chapterTitle: 'Chapter one',
    chapterList: [{ id: 'chapter-1', title: 'Chapter one', index: 0 }],
    chapterOrderIndex: 0,
    segments: [],
    segmentIndex: 0,
    segmentDurations: [],
    progressPercent: 0,
    chapterDuration: 0,
    chapterElapsed: 0,
    currentTime: 0,
    speed: 1,
    loading: false,
    playing: false,
    objectUrl: '',
    userStartedPlayback: false,
    autoplayContinuity: false,
    error: '',
    canPrev: false,
    canAdvance: false,
    audio: null,
    toggle: vi.fn(),
    prev: vi.fn(),
    next: vi.fn(),
    setSpeed: vi.fn(),
    resumeFromServer: vi.fn().mockResolvedValue(),
    loadSegment: vi.fn().mockResolvedValue(),
    ensureChapterWindowCache: vi.fn(),
    ...overrides,
  })
}

describe('PlayerView', () => {
  beforeEach(() => {
    route.params = { bookId: 'book-1', chapterId: 'chapter-1' }
    route.query = {}
    route.fullPath = '/player/book-1/chapter-1'
    router.replace.mockReset()
    router.replace.mockResolvedValue()
    resetPlayer()
  })

  it('uses and consumes the one-time autoplay query intent', async () => {
    route.query = { autoplay: '1' }
    resetPlayer({ loading: true })

    const wrapper = mount(PlayerView)
    await flushPromises()

    expect(player.resumeFromServer).toHaveBeenCalledWith(
      'book-1',
      'chapter-1',
      expect.objectContaining({ autoplay: true }),
    )
    expect(router.replace).toHaveBeenCalledWith({ query: {} })
    wrapper.unmount()
  })

  it('consumes the one-time autoplay intent after resume failure and preserves the error', async () => {
    route.query = { autoplay: '1' }
    const resumeError = new Error('自动播放初始化失败')
    resetPlayer({ resumeFromServer: vi.fn().mockRejectedValue(resumeError) })

    const wrapper = mount(PlayerView)
    await flushPromises()

    expect(router.replace).toHaveBeenCalledWith({ query: {} })
    expect(wrapper.text()).toContain('自动播放初始化失败')
    wrapper.unmount()
  })

  it('keeps ordinary player routes in reading mode', async () => {
    const wrapper = mount(PlayerView)
    await flushPromises()

    expect(player.resumeFromServer).toHaveBeenCalledWith(
      'book-1',
      'chapter-1',
      expect.objectContaining({ autoplay: false }),
    )
    wrapper.unmount()
  })

  it('does not resume again when auto-advance has already opened the same chapter', async () => {
    resetPlayer({
      loading: true,
      segments: [{ id: 'segment-1', text: 'Already opening' }],
      userStartedPlayback: true,
      autoplayContinuity: true,
    })

    const wrapper = mount(PlayerView)
    await flushPromises()

    expect(player.resumeFromServer).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('updates the same control from busy loading to normal playback state', async () => {
    resetPlayer({ loading: true })

    const wrapper = mount(PlayerView)
    await flushPromises()

    const control = wrapper.get('.ctrl.main')
    expect(control.attributes('aria-label')).toBe('音频加载中')
    expect(control.attributes('aria-busy')).toBe('true')
    expect(control.attributes()).toHaveProperty('disabled')
    expect(control.find('.player-loading-spinner').exists()).toBe(true)

    player.loading = false
    player.objectUrl = 'blob:recovered'
    await nextTick()

    expect(control.attributes('aria-label')).toBe('播放')
    expect(control.attributes('aria-busy')).toBe('false')
    expect(control.attributes()).not.toHaveProperty('disabled')
    expect(control.find('.player-loading-spinner').exists()).toBe(false)
    expect(control.find('svg').exists()).toBe(true)
    wrapper.unmount()
  })
})
