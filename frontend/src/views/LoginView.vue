<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import AuthShell from '../components/AuthShell.vue'
import { login } from '../stores/auth'

const router = useRouter()
const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await login(form)
    await router.push('/workspace')
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthShell eyebrow="欢迎回来" title="继续探索你的知识" subtitle="登录后访问你的文档与问答记录。">
    <form class="auth-form" @submit.prevent="submit">
      <label>
        <span>用户名</span>
        <input v-model.trim="form.username" autocomplete="username" required placeholder="输入用户名" />
      </label>
      <label>
        <span>密码</span>
        <input v-model="form.password" type="password" autocomplete="current-password" required placeholder="输入密码" />
      </label>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button class="primary-button" :disabled="loading">
        <span>{{ loading ? '正在登录…' : '登录' }}</span>
        <span aria-hidden="true">→</span>
      </button>
    </form>
    <p class="auth-switch">还没有账号？<router-link to="/register">立即创建</router-link></p>
  </AuthShell>
</template>

