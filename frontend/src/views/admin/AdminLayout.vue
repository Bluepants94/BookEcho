<script setup>
import PageHeader from '@/components/PageHeader.vue'
</script>

<template>
  <div class="page admin-page">
    <PageHeader title="管理后台" subtitle="用户、注册策略与系统任务" back />
    <nav class="admin-tabs" aria-label="管理导航">
      <RouterLink to="/admin/users">用户</RouterLink>
      <RouterLink to="/admin/books">书籍</RouterLink>
      <RouterLink to="/admin/settings">注册设置</RouterLink>
      <RouterLink to="/admin/jobs">任务</RouterLink>
      <RouterLink to="/admin/system">系统</RouterLink>
    </nav>
    <RouterView />
  </div>
</template>
