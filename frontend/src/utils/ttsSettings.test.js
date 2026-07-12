import assert from 'node:assert/strict'
import test from 'node:test'

import { getTtsCacheFingerprint } from './ttsSettings.js'

test('TTS cache fingerprint includes an explicit audio cache format version', () => {
  const fingerprint = getTtsCacheFingerprint({
    provider: 'mimo',
    base_url: 'https://api.example.test',
    model: 'mimo-tts',
    voice: 'reader',
    style: '',
    audio_format: 'pcm16',
    speed: 1,
    api_key: 'test-key',
  })

  assert.ok(
    fingerprint.split('|').includes('audio-cache-format:v2'),
    'cache fingerprints must include the audio cache format/parser version',
  )
})
