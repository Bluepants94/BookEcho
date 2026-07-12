const STORAGE_KEY = 'bookecho_tts_settings'
const CACHE_STORAGE_KEY = 'bookecho_cache_settings'
/** Increment when decoded audio bytes or cache interpretation changes. */
const AUDIO_CACHE_FORMAT_VERSION = 'v2'
const SYNTHESIS_SPEED = 1

/** Hardcoded IndexedDB eviction bound — not user-facing. */
const INTERNAL_MAX_CACHED_SEGMENTS = 240

const DEFAULTS = {
  base_url: '',
  api_key: '',
  model: '',
  voice: '',
  provider: 'auto',
  style: '',
  audio_format: 'pcm16',
}

const CACHE_DEFAULTS = {
  /** Prefetch: current chapter + next N chapters. */
  cache_chapters: 3,
  /** Soft upper bound on total cached segments across chapters (internal). */
  max_cached_segments: INTERNAL_MAX_CACHED_SEGMENTS,
}

export function loadTtsSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULTS }
    const parsed = JSON.parse(raw)
    const { speed: _legacySpeed, ...saved } =
      parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
    // Merge saved values over empty defaults (no vendor defaults).
    return { ...DEFAULTS, ...saved }
  } catch {
    return { ...DEFAULTS }
  }
}

export function saveTtsSettings(settings) {
  const next = {
    base_url: settings.base_url || '',
    api_key: settings.api_key || '',
    model: settings.model || '',
    voice: settings.voice || '',
    provider: settings.provider || 'auto',
    style: settings.style || '',
    audio_format: settings.audio_format || 'pcm16',
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  return next
}

export function loadCacheSettings() {
  try {
    const raw = localStorage.getItem(CACHE_STORAGE_KEY)
    if (!raw) return { ...CACHE_DEFAULTS }
    const parsed = JSON.parse(raw)
    return normalizeCacheSettings(parsed)
  } catch {
    return { ...CACHE_DEFAULTS }
  }
}

export function saveCacheSettings(settings = {}) {
  const next = normalizeCacheSettings(settings)
  // Persist only the user-facing key; max_cached_segments stays internal.
  localStorage.setItem(
    CACHE_STORAGE_KEY,
    JSON.stringify({ cache_chapters: next.cache_chapters }),
  )
  return next
}

export function normalizeCacheSettings(settings = {}) {
  // Prefer new key; fall back from old cache_next_chapters; else default 3.
  const rawChapters =
    settings.cache_chapters != null
      ? settings.cache_chapters
      : settings.cache_next_chapters != null
        ? settings.cache_next_chapters
        : CACHE_DEFAULTS.cache_chapters
  const chapters = clampInt(rawChapters, 0, 10, CACHE_DEFAULTS.cache_chapters)
  return {
    cache_chapters: chapters,
    max_cached_segments: INTERNAL_MAX_CACHED_SEGMENTS,
  }
}

function clampInt(value, min, max, fallback) {
  const n = Number(value)
  if (!Number.isFinite(n)) return fallback
  return Math.min(max, Math.max(min, Math.round(n)))
}

export function isMimoProvider(settings = {}) {
  const provider = String(settings.provider || 'auto').toLowerCase()
  if (provider === 'mimo' || provider === 'xiaomi' || provider === 'xiaomimimo') return true
  if (provider === 'openai') return false
  const base = String(settings.base_url || '').toLowerCase()
  const model = String(settings.model || '').toLowerCase()
  return base.includes('xiaomimimo') || base.includes('mimo') || model.includes('mimo')
}

/**
 * Stable fingerprint of TTS settings that affect synthesis output.
 * Used as a cache namespace so changing API/model/voice invalidates old audio.
 * Full api_key is never stored; only length + irreversible hash.
 */
export function getTtsCacheFingerprint(settings = loadTtsSettings()) {
  const provider = String(settings.provider || 'auto')
  const baseUrl = String(settings.base_url || '')
  const model = String(settings.model || '')
  const voice = String(settings.voice || '')
  const style = String(settings.style || '')
  const audioFormat = String(settings.audio_format || 'pcm16')
  const keyToken = hashApiKey(settings.api_key || '')

  return [
    `audio-cache-format:${AUDIO_CACHE_FORMAT_VERSION}`,
    provider,
    baseUrl,
    model,
    voice,
    style,
    audioFormat,
    String(SYNTHESIS_SPEED),
    keyToken,
  ].join('|')
}

function hashApiKey(apiKey) {
  const key = String(apiKey || '')
  if (!key) return '0:0'
  // djb2-ish 32-bit hash + length only — never embed raw key prefix/suffix.
  let hash = 5381
  for (let i = 0; i < key.length; i += 1) {
    hash = ((hash << 5) + hash + key.charCodeAt(i)) >>> 0
  }
  return `${key.length}:${hash.toString(16)}`
}

export { DEFAULTS, CACHE_DEFAULTS, STORAGE_KEY, CACHE_STORAGE_KEY }
