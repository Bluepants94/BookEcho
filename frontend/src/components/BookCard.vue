<script setup>
defineProps({
  book: { type: Object, required: true },
})
</script>

<template>
  <RouterLink class="book-card" :to="`/books/${book.id}`">
    <div class="book-info">
      <h3 class="book-title">{{ book.title || '未命名书籍' }}</h3>
      <p class="book-desc">
        {{ book.author || book.owner_name || '未知作者' }}
        <template v-if="book.chapter_count != null"> · {{ book.chapter_count }} 章</template>
      </p>
    </div>
  </RouterLink>
</template>
