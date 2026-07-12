import { getTtsCacheFingerprint } from '@/utils/ttsSettings'

const DB_NAME = 'bookecho-audio'
const STORE = 'segments'
const META_KEY = 'bookecho_audio_cache_meta'
const FP_KEY = 'bookecho_audio_cache_fp'
/** Soft fallback when no chapter-window policy is active. */
const MAX_SEGMENTS_FALLBACK = 240

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE)
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function cacheKey(fingerprint, bookId, chapterId, segmentIndex) {
  return `${fingerprint}|${bookId}:${chapterId}:${segmentIndex}`
}

function chapterPrefix(fingerprint, bookId, chapterId) {
  return `${fingerprint}|${bookId}:${chapterId}:`
}

function readMeta() {
  try {
    const raw = localStorage.getItem(META_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

function writeMeta(meta) {
  localStorage.setItem(META_KEY, JSON.stringify(meta))
}

async function idbGet(key) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly')
    const req = tx.objectStore(STORE).get(key)
    req.onsuccess = () => resolve(req.result || null)
    req.onerror = () => reject(req.error)
  })
}

async function idbSet(key, value) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).put(value, key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

async function idbDelete(key) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).delete(key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

/**
 * Prefer keeping keys whose chapter is inside the active window.
 * Outside-window keys are evicted first; then oldest remaining.
 */
async function enforceWindowAwareLru(nextKey, options = {}) {
  const maxSegments = Math.max(30, Number(options.maxSegments) || MAX_SEGMENTS_FALLBACK)
  const protectPrefixes = Array.isArray(options.protectPrefixes) ? options.protectPrefixes : []

  let meta = readMeta().filter((k) => k !== nextKey)
  meta.push(nextKey)

  const isProtected = (key) => protectPrefixes.some((p) => typeof key === 'string' && key.startsWith(p))

  while (meta.length > maxSegments) {
    let victimIdx = meta.findIndex((k) => !isProtected(k))
    if (victimIdx < 0) victimIdx = 0
    const old = meta.splice(victimIdx, 1)[0]
    try {
      await idbDelete(old)
    } catch {
      // ignore
    }
  }
  writeMeta(meta)
}

/**
 * Switch active cache namespace only when the caller fingerprint matches the
 * current TTS fingerprint. Stale in-flight callers must not rewrite FP_KEY
 * or delete the active namespace.
 */
export async function clearCacheIfFingerprintChanged(fingerprint) {
  const current = getTtsCacheFingerprint()
  if (fingerprint !== current) return { ok: false, reason: 'stale' }

  const prev = localStorage.getItem(FP_KEY)
  if (prev === fingerprint) return { ok: true, changed: false }

  localStorage.setItem(FP_KEY, fingerprint)

  const meta = readMeta()
  const keep = []
  for (const key of meta) {
    if (typeof key === 'string' && key.startsWith(`${fingerprint}|`)) {
      keep.push(key)
    } else {
      try {
        await idbDelete(key)
      } catch {
        // ignore
      }
    }
  }
  writeMeta(keep)
  return { ok: true, changed: true }
}

export async function getCachedAudio(fingerprint, bookId, chapterId, segmentIndex) {
  const gate = await clearCacheIfFingerprintChanged(fingerprint)
  if (!gate.ok) return null

  const key = cacheKey(fingerprint, bookId, chapterId, segmentIndex)
  const blob = await idbGet(key)
  if (blob) {
    const meta = readMeta().filter((k) => k !== key)
    meta.push(key)
    writeMeta(meta)
  }
  return blob
}

/**
 * Write segment audio. options:
 * - maxSegments: soft cap
 * - protectPrefixes: chapter key prefixes to prefer keeping
 * Rejects writes whose fingerprint is not the current TTS fingerprint.
 */
export async function setCachedAudio(fingerprint, bookId, chapterId, segmentIndex, blob, options = {}) {
  const gate = await clearCacheIfFingerprintChanged(fingerprint)
  if (!gate.ok) return false

  const key = cacheKey(fingerprint, bookId, chapterId, segmentIndex)
  await idbSet(key, blob)
  await enforceWindowAwareLru(key, {
    maxSegments: options.maxSegments,
    protectPrefixes: options.protectPrefixes,
  })
  return true
}

/** Delete all cached segments for chapters outside the protected set (same book + fingerprint). */
export async function pruneChaptersOutsideWindow(fingerprint, bookId, keepChapterIds = []) {
  const gate = await clearCacheIfFingerprintChanged(fingerprint)
  if (!gate.ok) return

  const keep = new Set((keepChapterIds || []).map(String))
  const prefixBook = `${fingerprint}|${bookId}:`
  const meta = readMeta()
  const next = []
  for (const key of meta) {
    if (typeof key !== 'string' || !key.startsWith(prefixBook)) {
      next.push(key)
      continue
    }
    // key: fp|bookId:chapterId:segmentIndex
    const rest = key.slice(prefixBook.length)
    const chapterId = rest.split(':')[0]
    if (keep.has(String(chapterId))) {
      next.push(key)
      continue
    }
    try {
      await idbDelete(key)
    } catch {
      // ignore
    }
  }
  writeMeta(next)
}

export function chapterCachePrefix(fingerprint, bookId, chapterId) {
  return chapterPrefix(fingerprint, bookId, chapterId)
}


/**
 * List chapter ids that have at least one cached segment for book + fingerprint.
 * Meta keys look like: fp|bookId:chapterId:seg
 */
export function listCachedChapterIds(fingerprint, bookId) {
  if (fingerprint == null || bookId == null) return []
  const prefix = `${fingerprint}|${bookId}:`
  const found = new Set()
  for (const key of readMeta()) {
    if (typeof key !== 'string' || !key.startsWith(prefix)) continue
    const rest = key.slice(prefix.length)
    const chapterId = rest.split(':')[0]
    if (chapterId) found.add(String(chapterId))
  }
  return Array.from(found)
}

export { cacheKey, MAX_SEGMENTS_FALLBACK as MAX_SEGMENTS }
