import { defineStore } from 'pinia'
import { authApi } from '@/api/client'
import {
  loadTtsSettings,
  saveTtsSettings,
  loadCacheSettings,
  saveCacheSettings,
  getTtsCacheFingerprint,
} from '@/utils/ttsSettings'

function isMaskedSecret(value) {
  const key = String(value || '')
  if (!key) return false
  if (!key.includes('*')) return false
  return key.split('*').join('').length <= 8
}

function splitServerPayload(payload = {}) {
  const tts = {
    base_url: payload.base_url || '',
    api_key: payload.api_key || '',
    model: payload.model || '',
    voice: payload.voice || '',
    provider: payload.provider || 'auto',
    style: payload.style || '',
    audio_format: payload.audio_format || 'pcm16',
  }
  const cache = {
    cache_chapters: payload.cache_chapters,
  }
  return { tts, cache }
}

/**
 * Prefer a full local/client key over a masked server response value.
 */
function mergeTtsPreferringLocalKey(serverTts, localTts) {
  const next = { ...serverTts }
  if (isMaskedSecret(next.api_key) && localTts?.api_key && !isMaskedSecret(localTts.api_key)) {
    next.api_key = localTts.api_key
  }
  return next
}

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    tts: loadTtsSettings(),
    cache: loadCacheSettings(),
    /** Soft notice after TTS settings change — kept for compatibility, unused in UI. */
    ttsUpdatedNotice: '',
    hydrating: false,
    hydrated: false,
  }),
  actions: {
    /**
     * Load local settings first, then overlay server-persisted settings when logged in.
     * Server wins for TTS + cache_chapters so browser clears / rebuilds do not drop config.
     */
    async hydrateFromServer() {
      if (this.hydrating) return
      this.hydrating = true
      try {
        // Always refresh local snapshot first.
        this.tts = loadTtsSettings()
        this.cache = loadCacheSettings()
        const data = await authApi.getTtsSettings()
        if (data && typeof data === 'object') {
          const localTts = loadTtsSettings()
          const { tts, cache } = splitServerPayload(data)
          this.tts = saveTtsSettings(mergeTtsPreferringLocalKey(tts, localTts))
          this.cache = saveCacheSettings({ ...this.cache, ...cache })
        }
        this.hydrated = true
      } catch {
        // Offline / unauthenticated — keep local values.
        this.hydrated = false
      } finally {
        this.hydrating = false
      }
    },

    updateTts(partial) {
      const prevFp = getTtsCacheFingerprint(this.tts)
      this.tts = saveTtsSettings({ ...this.tts, ...partial })
      const nextFp = getTtsCacheFingerprint(this.tts)
      return { fingerprintChanged: prevFp !== nextFp }
    },

    updateCache(partial) {
      this.cache = saveCacheSettings({ ...this.cache, ...partial })
      return this.cache
    },

    /**
     * Persist current TTS + cache settings to the server.
     * Returns false when the request fails (local save still kept).
     */
    async persistToServer() {
      try {
        const localTts = { ...this.tts }
        const payload = {
          ...localTts,
          cache_chapters: this.cache.cache_chapters,
        }
        const data = await authApi.putTtsSettings(payload)
        if (data && typeof data === 'object') {
          const { tts, cache } = splitServerPayload(data)
          // Server masks api_key; keep the full key we just submitted/had locally.
          this.tts = saveTtsSettings(mergeTtsPreferringLocalKey(tts, localTts))
          this.cache = saveCacheSettings({ ...this.cache, ...cache })
        }
        return true
      } catch {
        return false
      }
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
