import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, reactive } from 'vue'

const auth = { bootstrap: vi.fn() }
const player = reactive({ hasTrack: true })
const route = reactive({ name: 'home', meta: {} })

vi.mock('vue-router', () => ({ useRoute: () => route }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/stores/player', () => ({ usePlayerStore: () => player }))

import App from '../App.vue'

function mountApp() {
  return mount(App, {
    global: {
      stubs: {
        RouterView: true,
        AppTabBar: true,
        MiniPlayer: { template: '<div data-test="mini-player" />' },
      },
    },
  })
}

describe('App mini player visibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    route.name = 'home'
    route.meta = {}
    player.hasTrack = true
  })

  it('updates visibility as the route and track change without remounting', async () => {
    const wrapper = mountApp()

    expect(wrapper.find('[data-test="mini-player"]').exists()).toBe(true)

    route.name = 'book'
    await nextTick()
    expect(wrapper.find('[data-test="mini-player"]').exists()).toBe(true)

    player.hasTrack = false
    await nextTick()
    expect(wrapper.find('[data-test="mini-player"]').exists()).toBe(false)

    player.hasTrack = true
    route.name = 'player'
    route.meta = { hideChrome: true }
    await nextTick()
    expect(wrapper.find('[data-test="mini-player"]').exists()).toBe(false)

    wrapper.unmount()
  })
})
