import { afterEach, describe, expect, it } from 'vitest'
import {
  DEFAULTS,
  getTtsCacheFingerprint,
  loadTtsSettings,
  saveTtsSettings,
  STORAGE_KEY,
} from './ttsSettings'

afterEach(() => {
  localStorage.clear()
})

describe('TTS settings', () => {
  it('ignores the legacy persisted synthesis speed', () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ base_url: 'https://tts.example.test', model: 'voice-1', speed: 1.5 }),
    )

    expect(loadTtsSettings()).toEqual({
      ...DEFAULTS,
      base_url: 'https://tts.example.test',
      model: 'voice-1',
    })
    expect(loadTtsSettings()).not.toHaveProperty('speed')
  })

  it('does not persist a user-configured synthesis speed', () => {
    const saved = saveTtsSettings({
      base_url: 'https://tts.example.test',
      api_key: 'secret',
      model: 'voice-1',
      voice: 'alloy',
      speed: 2,
    })

    expect(saved).not.toHaveProperty('speed')
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).not.toHaveProperty('speed')
  })

  it('uses fixed 1x synthesis in cache fingerprints', () => {
    const settings = {
      base_url: 'https://tts.example.test',
      model: 'voice-1',
      voice: 'alloy',
    }

    const slowFingerprint = getTtsCacheFingerprint({ ...settings, speed: 0.5 })
    const fastFingerprint = getTtsCacheFingerprint({ ...settings, speed: 2 })

    expect(slowFingerprint).toBe(fastFingerprint)
    expect(slowFingerprint.split('|')).toContain('audio-cache-format:v2')
    expect(slowFingerprint).toContain('|1|')
  })
})
