<script setup>
defineProps({
  eyebrow: { type: String, required: true },
  title: { type: String, required: true },
  subtitle: { type: String, required: true },
})
</script>

<template>
  <main class="auth-page">
    <section class="auth-story">
      <router-link to="/" class="brand brand--light" aria-label="知屿首页">
        <span class="brand__mark">知</span>
        <span>知屿</span>
      </router-link>
      <div class="story-copy">
        <p class="eyebrow">你的知识，只回答你的问题</p>
        <h1>让散落的文档，<br />成为可靠的答案。</h1>
        <p>千问依据你的资料回答。文档文本与问题会发送至千问服务处理。</p>
      </div>
      <div class="story-proof">
        <span class="pulse-dot"></span>
        <span>千问 · 文档问答</span>
      </div>
    </section>

    <section class="auth-panel">
      <div class="auth-card">
        <p class="eyebrow eyebrow--ink">{{ eyebrow }}</p>
        <h2>{{ title }}</h2>
        <p class="auth-subtitle">{{ subtitle }}</p>
        <slot />
      </div>
    </section>
  </main>
</template>
