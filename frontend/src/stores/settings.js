import { defineStore } from 'pinia'
import {
  loadTtsSettings,
  saveTtsSettings,
  loadCacheSettings,
  saveCacheSettings,
  getTtsCacheFingerprint,
} from '@/utils/ttsSettings'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    tts: loadTtsSettings(),
    cache: loadCacheSettings(),
    /** Soft notice after TTS settings change — next load uses new fingerprint. */
    ttsUpdatedNotice: '',
  }),
  actions: {
    updateTts(partial) {
      const prevFp = getTtsCacheFingerprint(this.tts)
      this.tts = saveTtsSettings({ ...this.tts, ...partial })
      const nextFp = getTtsCacheFingerprint(this.tts)
      if (prevFp !== nextFp) {
        this.ttsUpdatedNotice = '设置已更新，将按新配置重新合成'
      } else {
        this.ttsUpdatedNotice = '设置已保存'
      }
      return { fingerprintChanged: prevFp !== nextFp }
    },
    updateCache(partial) {
      this.cache = saveCacheSettings({ ...this.cache, ...partial })
      this.ttsUpdatedNotice = '缓存策略已更新，点击播放后按新窗口预缓存'
      return this.cache
    },
    clearTtsNotice() {
      this.ttsUpdatedNotice = ''
    },
    reload() {
      this.tts = loadTtsSettings()
      this.cache = loadCacheSettings()
    },
  },
})
