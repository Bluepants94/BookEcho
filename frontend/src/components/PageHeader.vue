<script setup>
defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  back: { type: Boolean, default: false },
})
</script>

<template>
  <header class="page-header">
    <button v-if="back" class="icon-btn" type="button" aria-label="返回" @click="$router.back()">
      <svg class="icon-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M15 6 9 12l6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>
    <div class="page-header-text">
      <h1>{{ title }}</h1>
      <p v-if="subtitle">{{ subtitle }}</p>
    </div>
    <div class="page-header-extra">
      <slot />
    </div>
  </header>
</template>
