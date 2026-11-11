<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import AuthShell from '../components/AuthShell.vue'
import { register } from '../stores/auth'

const router = useRouter()
const form = reactive({ username: '', email: '', password: '', password_confirm: '' })
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (form.password !== form.password_confirm) {
    error.value = '两次输入的密码不一致。'
    return
  }
  loading.value = true
  try {
    await register(form)
    await router.push('/workspace')
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthShell eyebrow="创建账户" title="建立你的知识领地" subtitle="注册后即可上传文档，资料在不同用户之间完全隔离。">
    <form class="auth-form" @submit.prevent="submit">
      <div class="field-row">
        <label>
          <span>用户名</span>
          <input v-model.trim="form.username" autocomplete="username" required placeholder="至少 3 个字符" minlength="3" />
        </label>
        <label>
          <span>邮箱 <i>选填</i></span>
          <input v-model.trim="form.email" type="email" autocomplete="email" placeholder="name@example.com" />
        </label>
      </div>
      <label>
        <span>密码</span>
        <input v-model="form.password" type="password" autocomplete="new-password" required minlength="8" placeholder="至少 8 个字符" />
      </label>
      <label>
        <span>确认密码</span>
        <input v-model="form.password_confirm" type="password" autocomplete="new-password" required placeholder="再次输入密码" />
      </label>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button class="primary-button" :disabled="loading">
        <span>{{ loading ? '正在创建…' : '创建账户' }}</span>
        <span aria-hidden="true">→</span>
      </button>
    </form>
    <p class="auth-switch">已有账号？<router-link to="/login">直接登录</router-link></p>
  </AuthShell>
</template>

