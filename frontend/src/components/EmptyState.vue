<script setup>
defineProps({
  message: { type: String, default: '暂无内容' },
})
</script>

<template>
  <div class="state-box empty">
    <div class="empty-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none">
        <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v15.5H7.5A2.5 2.5 0 0 0 5 21V5.5Z" stroke="currentColor" stroke-width="1.8"/>
        <path d="M5 18.5h12.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
      </svg>
    </div>
    <p>{{ message }}</p>
    <slot />
  </div>
</template>
