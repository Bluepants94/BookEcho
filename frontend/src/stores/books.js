import { defineStore } from 'pinia'
import { booksApi } from '@/api/client'
import { normalizeBook, normalizeList } from '@/utils/format'

export const useBooksStore = defineStore('books', {
  state: () => ({
    myBooks: [],
    currentBook: null,
    chapters: [],
    loading: false,
    error: '',
  }),
  actions: {
    async fetchHome() {
      this.loading = true
      this.error = ''
      try {
        const mine = await booksApi.mine()
        this.myBooks = normalizeList(mine).map(normalizeBook)
      } catch (e) {
        this.error = e.message || '加载书架失败'
      } finally {
        this.loading = false
      }
    },
    async fetchBook(id) {
      this.loading = true
      this.error = ''
      try {
        const [book, chapters] = await Promise.all([
          booksApi.get(id),
          booksApi.chapters(id),
        ])
        this.currentBook = normalizeBook(book)
        this.chapters = Array.isArray(chapters)
          ? chapters
          : chapters?.items || chapters?.data || chapters?.results || []
        return this.currentBook
      } catch (e) {
        this.error = e.message || '加载书籍失败'
        throw e
      } finally {
        this.loading = false
      }
    },
  },
})
