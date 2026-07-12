<script setup>
defineProps({
  message: { type: String, default: '加载中…' },
})
</script>

<template>
  <div class="state-box">
    <div class="spinner" />
    <p>{{ message }}</p>
  </div>
</template>
