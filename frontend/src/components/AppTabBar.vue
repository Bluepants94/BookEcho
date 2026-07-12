<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const tabs = computed(() => [
  { name: 'home', label: '首页', path: '/', icon: 'home' },
  { name: 'upload', label: '上传', path: '/upload', icon: 'upload' },
  { name: 'me', label: '我的', path: '/me', icon: 'me' },
])

function isActive(tab) {
  return route.path === tab.path || route.name === tab.name
}

function go(tab) {
  router.push(tab.path)
}
</script>

<template>
  <nav class="tabbar safe-bottom" aria-label="主导航">
    <button
      v-for="tab in tabs"
      :key="tab.name"
      class="tab-item"
      :class="{ active: isActive(tab) }"
      type="button"
      :aria-current="isActive(tab) ? 'page' : undefined"
      @click="go(tab)"
    >
      <span class="tab-icon" aria-hidden="true">
        <svg v-if="tab.icon === 'home'" viewBox="0 0 24 24" fill="none">
          <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
        </svg>
        <svg v-else-if="tab.icon === 'upload'" viewBox="0 0 24 24" fill="none">
          <path d="M12 16V5m0 0 4 4m-4-4-4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M5 19h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="8" r="3.5" stroke="currentColor" stroke-width="1.8"/>
          <path d="M5.5 19.5c1.4-3.2 3.8-4.8 6.5-4.8s5.1 1.6 6.5 4.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
      </span>
      <span class="tab-label">{{ tab.label }}</span>
    </button>
  </nav>
</template>
