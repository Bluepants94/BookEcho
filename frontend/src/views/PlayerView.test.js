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
    chapterOpening: false,
    audioLoading: false,
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
    seek: vi.fn().mockResolvedValue(),
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
    // jsdom does not implement Element.scrollIntoView; stub it so watcher-driven
    // scroll-follow does not throw during component tests.
    if (typeof window.Element.prototype.scrollIntoView !== 'function') {
      window.Element.prototype.scrollIntoView = function scrollIntoView() {}
    }
    resetPlayer()
  })

  it('uses and consumes the one-time autoplay query intent', async () => {
    route.query = { autoplay: '1' }
    // Fresh route with no continuity yet — bootstrap must start resume with autoplay.
    resetPlayer({
      bookId: null,
      chapterId: null,
      loading: false,
      chapterOpening: false,
      audioLoading: false,
      userStartedPlayback: false,
      autoplayContinuity: false,
    })

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

  it('does not re-open the same chapter when autoplay intent arrives after a gesture open', async () => {
    route.query = { autoplay: '1' }
    resetPlayer({
      loading: true,
      chapterOpening: true,
      audioLoading: true,
      userStartedPlayback: true,
      autoplayContinuity: true,
      segments: [],
    })

    const wrapper = mount(PlayerView)
    await flushPromises()

    expect(player.resumeFromServer).not.toHaveBeenCalled()
    expect(router.replace).toHaveBeenCalledWith({ query: {} })
    wrapper.unmount()
  })

  it('consumes the one-time autoplay intent after resume failure and preserves the error', async () => {
    route.query = { autoplay: '1' }
    const resumeError = new Error('自动播放初始化失败')
    resetPlayer({
      bookId: null,
      chapterId: null,
      resumeFromServer: vi.fn().mockRejectedValue(resumeError),
    })

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
    resetPlayer({ audioLoading: true })

    const wrapper = mount(PlayerView)
    await flushPromises()

    const control = wrapper.get('.ctrl.main')
    expect(control.attributes('aria-label')).toBe('音频加载中')
    expect(control.attributes('aria-busy')).toBe('true')
    expect(control.attributes()).toHaveProperty('disabled')
    expect(control.find('.player-loading-spinner').exists()).toBe(true)

    player.audioLoading = false
    player.objectUrl = 'blob:recovered'
    await nextTick()

    expect(control.attributes('aria-label')).toBe('播放')
    expect(control.attributes('aria-busy')).toBe('false')
    expect(control.attributes()).not.toHaveProperty('disabled')
    expect(control.find('.player-loading-spinner').exists()).toBe(false)
    expect(control.find('svg').exists()).toBe(true)
    wrapper.unmount()
  })

  it('renders chapter text as soon as segments arrive, before audio is ready', async () => {
    resetPlayer({ chapterOpening: true, segments: [] })

    const wrapper = mount(PlayerView)
    await flushPromises()

    // Loading text shows while chapter body is still being fetched.
    expect(wrapper.find('.reader-status').text()).toContain('加载中')

    // Segments arrive — chapter body renders even though audio is still loading.
    player.chapterOpening = false
    player.segments = [{ id: 'segment-1', text: '第一段正文' }]
    player.audioLoading = true
    await nextTick()

    expect(wrapper.find('.reader-status').exists()).toBe(false)
    expect(wrapper.findAll('.reader-seg').length).toBe(1)

    // Play button still shows spinner because audio is still loading.
    const control = wrapper.get('.ctrl.main')
    expect(control.find('.player-loading-spinner').exists()).toBe(true)

    player.audioLoading = false
    player.objectUrl = 'blob:ready'
    await nextTick()
    expect(control.find('.player-loading-spinner').exists()).toBe(false)
    wrapper.unmount()
  })

  function dispatchPointer(el, type, { clientX = 0, pointerId = 1, pointerType = 'mouse', buttons = 1 } = {}) {
    const event = new Event(type, { bubbles: true, cancelable: true })
    Object.defineProperties(event, {
      clientX: { value: clientX },
      pointerId: { value: pointerId },
      pointerType: { value: pointerType },
      button: { value: 0 },
      buttons: { value: buttons },
    })
    el.dispatchEvent(event)
    return event
  }

  it('supports dragging the seekbar to a new position', async () => {
    resetPlayer({
      chapterDuration: 100,
      chapterElapsed: 10,
      progressPercent: 10,
      segments: [{ id: 's1', text: 'hello' }],
      segmentDurations: [100],
    })
    const wrapper = mount(PlayerView)
    await flushPromises()
    await nextTick()

    const track = wrapper.get('.seekbar-track')
    const el = track.element
    el.getBoundingClientRect = () => ({
      left: 0,
      width: 200,
      top: 0,
      right: 200,
      bottom: 28,
      height: 28,
      x: 0,
      y: 0,
      toJSON() {},
    })
    el.setPointerCapture = vi.fn()
    el.releasePointerCapture = vi.fn()

    dispatchPointer(el, 'pointerdown', { clientX: 40 })
    await nextTick()
    expect(track.classes()).toContain('is-scrubbing')
    expect(wrapper.get('.seekbar-fill').attributes('style') || '').toContain('20%')

    dispatchPointer(el, 'pointermove', { clientX: 100 })
    await nextTick()
    expect(wrapper.get('.seekbar-fill').attributes('style') || '').toContain('50%')

    dispatchPointer(el, 'pointerup', { clientX: 150, buttons: 0 })
    await flushPromises()
    await nextTick()

    expect(player.seek).toHaveBeenCalledWith(0.75)
    expect(track.classes()).not.toContain('is-scrubbing')
    wrapper.unmount()
  })

  it('does not seek while duration is still unknown', async () => {
    resetPlayer({
      chapterDuration: 0,
      progressPercent: 0,
      segments: [{ id: 's1', text: 'hello' }],
    })
    const wrapper = mount(PlayerView)
    await flushPromises()
    await nextTick()

    const track = wrapper.get('.seekbar-track')
    const el = track.element
    el.getBoundingClientRect = () => ({
      left: 0,
      width: 200,
      top: 0,
      right: 200,
      bottom: 28,
      height: 28,
      x: 0,
      y: 0,
      toJSON() {},
    })
    dispatchPointer(el, 'pointerdown', { clientX: 80 })
    dispatchPointer(el, 'pointerup', { clientX: 80, buttons: 0 })
    await flushPromises()

    expect(player.seek).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
