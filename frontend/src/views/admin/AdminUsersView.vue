<script setup>
import { onMounted, ref } from 'vue'
import { adminApi } from '@/api/client'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import { normalizeList } from '@/utils/format'

const users = ref([])
const loading = ref(true)
const error = ref('')
const form = ref({ username: '', password: '', role: 'user' })
const creating = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    users.value = normalizeList(await adminApi.users())
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function createUser() {
  if (!form.value.username || !form.value.password) {
    error.value = '请填写用户名和密码'
    return
  }
  creating.value = true
  error.value = ''
  try {
    await adminApi.createUser({
      username: form.value.username,
      password: form.value.password,
      role: form.value.role,
    })
    form.value = { username: '', password: '', role: 'user' }
    await load()
  } catch (e) {
    error.value = e.message || '创建失败'
  } finally {
    creating.value = false
  }
}

async function promote(user) {
  if (!confirm(`确认将 ${user.username} 升为管理员？此操作不可降级。`)) return
  try {
    await adminApi.updateUser(user.id, { role: 'admin' })
    await load()
  } catch (e) {
    error.value = e.message || '更新失败'
  }
}

async function resetPassword(user) {
  const password = prompt(`为 ${user.username} 设置新密码（至少6位）`)
  if (!password) return
  try {
    await adminApi.updateUser(user.id, { password })
    alert('密码已重置')
  } catch (e) {
    error.value = e.message || '重置失败'
  }
}

async function removeUser(user) {
  if (user.role === 'admin') {
    alert('不能删除管理员账号')
    return
  }
  if (!confirm(`确认删除用户 ${user.username}？`)) return
  try {
    await adminApi.deleteUser(user.id)
    await load()
  } catch (e) {
    error.value = e.message || '删除失败'
  }
}

onMounted(load)
</script>

<template>
  <section class="section">
    <div class="section-head">
      <h2>用户管理</h2>
      <button class="link-btn" type="button" @click="load">刷新</button>
    </div>

    <form class="card form-card" style="margin-bottom: 16px" @submit.prevent="createUser">
      <h3 style="margin:0 0 10px">手动创建账号</h3>
      <label class="field"><span>用户名</span><input v-model.trim="form.username" /></label>
      <label class="field"><span>密码</span><input v-model="form.password" type="password" /></label>
      <label class="field">
        <span>角色</span>
        <select v-model="form.role">
          <option value="user">user</option>
          <option value="admin">admin</option>
        </select>
      </label>
      <button class="btn primary" type="submit" :disabled="creating">创建</button>
    </form>

    <LoadingState v-if="loading" />
    <p v-else-if="error" class="form-error">{{ error }}</p>
    <EmptyState v-else-if="!users.length" message="暂无用户" />
    <div v-else class="admin-table card">
      <div v-for="user in users" :key="user.id" class="admin-row">
        <div>
          <strong>{{ user.username }}</strong>
          <p class="muted">#{{ user.id }} · {{ user.role }} · {{ user.is_active === false ? '禁用' : '启用' }}</p>
        </div>
        <div class="admin-actions">
          <button
            v-if="user.role !== 'admin'"
            class="btn sm"
            type="button"
            @click="promote(user)"
          >升为管理员</button>
          <button
            v-else
            class="btn sm"
            type="button"
            disabled
            title="管理员不可降级"
          >管理员（不可降级）</button>
          <button class="btn sm" type="button" @click="resetPassword(user)">重置密码</button>
          <button
            class="btn sm danger-outline"
            type="button"
            :disabled="user.role === 'admin'"
            @click="removeUser(user)"
          >删除</button>
        </div>
      </div>
    </div>
  </section>
</template>
