<script setup>
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

function logout() {
  auth.logout()
  router.replace('/login')
}
</script>

<template>
  <div class="page">
    <PageHeader title="账号与设置" />
    <div class="card profile-card">
      <div class="avatar">{{ auth.displayName.slice(0, 1).toUpperCase() }}</div>
      <div>
        <h2>{{ auth.displayName }}</h2>
        <p class="muted">角色：{{ auth.user?.role || 'user' }}</p>
      </div>
    </div>

    <div class="list-card">
      <RouterLink class="list-item" to="/password">修改密码</RouterLink>
      <RouterLink class="list-item" to="/settings">API 设置</RouterLink>
      <RouterLink v-if="auth.isAdmin" class="list-item" to="/admin">管理后台</RouterLink>
      <button class="list-item danger" type="button" @click="logout">退出登录</button>
    </div>
  </div>
</template>
