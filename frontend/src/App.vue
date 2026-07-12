<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePlayerStore } from '@/stores/player'
import AppTabBar from '@/components/AppTabBar.vue'
import MiniPlayer from '@/components/MiniPlayer.vue'

const route = useRoute()
const auth = useAuthStore()
const player = usePlayerStore()

const hideChrome = computed(() => Boolean(route.meta?.hideChrome))
const showMini = computed(() => (route.name === 'home' || route.name === 'book') && player.hasTrack)

onMounted(() => {
  auth.bootstrap()
})
</script>

<template>
  <div class="app-shell" :class="{ 'no-tab': hideChrome, 'with-mini': showMini }">
    <main class="app-main">
      <RouterView />
    </main>
    <MiniPlayer v-if="showMini" />
    <AppTabBar v-if="!hideChrome" />
  </div>
</template>
