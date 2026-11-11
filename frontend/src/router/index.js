import { createRouter, createWebHistory } from 'vue-router'

import { auth } from '../stores/auth'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import WorkspaceView from '../views/WorkspaceView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/workspace' },
    { path: '/login', component: LoginView, meta: { guestOnly: true } },
    { path: '/register', component: RegisterView, meta: { guestOnly: true } },
    { path: '/workspace', component: WorkspaceView, meta: { requiresAuth: true } },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !auth.isAuthenticated) return '/login'
  if (to.meta.guestOnly && auth.isAuthenticated) return '/workspace'
})

window.addEventListener('auth-expired', () => router.push('/login'))

export default router

