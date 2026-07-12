import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { hideChrome: true, public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { hideChrome: true, public: true },
  },
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
  },
  {
    path: '/books/:id',
    name: 'book',
    component: () => import('@/views/BookDetailView.vue'),
  },
  {
    path: '/player/:bookId/:chapterId',
    name: 'player',
    component: () => import('@/views/PlayerView.vue'),
    meta: { hideChrome: true },
  },
  {
    path: '/upload',
    name: 'upload',
    component: () => import('@/views/UploadView.vue'),
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
  },
  {
    path: '/me',
    name: 'me',
    component: () => import('@/views/MeView.vue'),
  },
  {
    path: '/password',
    name: 'password',
    component: () => import('@/views/PasswordView.vue'),
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/views/admin/AdminLayout.vue'),
    meta: { requiresAdmin: true },
    children: [
      { path: '', redirect: { name: 'admin-users' } },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/admin/AdminUsersView.vue'),
      },
      {
        path: 'books',
        name: 'admin-books',
        component: () => import('@/views/admin/AdminBooksView.vue'),
      },
      {
        path: 'settings',
        name: 'admin-settings',
        component: () => import('@/views/admin/AdminSettingsView.vue'),
      },
      {
        path: 'jobs',
        name: 'admin-jobs',
        component: () => import('@/views/admin/AdminJobsView.vue'),
      },
      {
        path: 'system',
        name: 'admin-system',
        component: () => import('@/views/admin/AdminSystemView.vue'),
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.bootstrapped) {
    await auth.bootstrap()
  }

  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if ((to.name === 'login' || to.name === 'register') && auth.isAuthenticated) {
    return { name: 'home' }
  }

  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'home' }
  }

  return true
})

export default router
