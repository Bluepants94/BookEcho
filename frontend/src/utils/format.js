export function formatTime(sec) {
  if (!Number.isFinite(sec) || sec < 0) return '00:00'
  const s = Math.floor(sec % 60)
  const m = Math.floor(sec / 60) % 60
  const h = Math.floor(sec / 3600)
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function coverColor(seed = '') {
  const palette = [
    'linear-gradient(145deg, #ffb347, #ff6a00)',
    'linear-gradient(145deg, #ff8a3d, #e85d04)',
    'linear-gradient(145deg, #f4a261, #d9480f)',
    'linear-gradient(145deg, #ffd08a, #ff6a00)',
    'linear-gradient(145deg, #ff9f68, #c2410c)',
    'linear-gradient(145deg, #ffc078, #e8590c)',
  ]
  let hash = 0
  for (let i = 0; i < String(seed).length; i += 1) {
    hash = (hash * 31 + String(seed).charCodeAt(i)) >>> 0
  }
  return palette[hash % palette.length]
}

export function normalizeList(payload) {
  if (Array.isArray(payload)) return payload
  if (payload?.items && Array.isArray(payload.items)) return payload.items
  if (payload?.data && Array.isArray(payload.data)) return payload.data
  if (payload?.results && Array.isArray(payload.results)) return payload.results
  if (payload?.books && Array.isArray(payload.books)) return payload.books
  return []
}

export function normalizeBook(book = {}) {
  return {
    ...book,
    visibility: 'private',
    is_public: false,
  }
}

export function normalizeBooks(payload) {
  return normalizeList(payload).map(normalizeBook)
}
