<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '../api/http'
import { auth, logout } from '../stores/auth'

const router = useRouter()
const documents = ref([])
const loadingDocuments = ref(true)
const uploading = ref(false)
const uploadError = ref('')
const dragging = ref(false)
const asking = ref(false)
const question = ref('')
const sidebarOpen = ref(false)
const fileInput = ref(null)
const chatEnd = ref(null)
const messages = ref([
  {
    role: 'assistant',
    content: '你好，我会严格依据你上传的文档回答。先在左侧添加资料，然后向我提问。',
    sources: [],
    refused: false,
  },
])

const readyCount = computed(() => documents.value.filter((doc) => doc.status === 'ready').length)
const canAsk = computed(() => question.value.trim() && !asking.value && readyCount.value > 0)

onMounted(loadDocuments)

async function loadDocuments() {
  loadingDocuments.value = true
  try {
    documents.value = await api('/documents/')
  } catch (error) {
    uploadError.value = error.message
  } finally {
    loadingDocuments.value = false
  }
}

async function uploadFiles(files) {
  const file = files?.[0]
  if (!file || uploading.value) return
  uploadError.value = ''
  uploading.value = true
  const formData = new FormData()
  formData.append('file', file)
  try {
    const document = await api('/documents/', { method: 'POST', body: formData })
    documents.value.unshift(document)
  } catch (error) {
    uploadError.value = error.message
    await loadDocuments()
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

function onDrop(event) {
  dragging.value = false
  uploadFiles(event.dataTransfer.files)
}

async function removeDocument(document) {
  if (!window.confirm(`确定删除“${document.original_name}”及其全部向量数据吗？`)) return
  try {
    await api(`/documents/${document.id}/`, { method: 'DELETE' })
    documents.value = documents.value.filter((item) => item.id !== document.id)
  } catch (error) {
    uploadError.value = error.message
  }
}

async function ask() {
  const text = question.value.trim()
  if (!text || !canAsk.value) return
  messages.value.push({ role: 'user', content: text })
  question.value = ''
  asking.value = true
  await scrollToBottom()
  try {
    const response = await api('/ask/', {
      method: 'POST',
      body: JSON.stringify({ question: text }),
    })
    messages.value.push({ role: 'assistant', ...response })
  } catch (error) {
    messages.value.push({ role: 'error', content: error.message })
  } finally {
    asking.value = false
    await scrollToBottom()
  }
}

function onQuestionKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    ask()
  }
}

async function scrollToBottom() {
  await nextTick()
  chatEnd.value?.scrollIntoView({ behavior: 'smooth' })
}

async function signOut() {
  await logout()
  await router.push('/login')
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(value) {
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(value))
}
</script>

<template>
  <main class="workspace-shell">
    <div v-if="sidebarOpen" class="sidebar-scrim" @click="sidebarOpen = false"></div>
    <aside class="sidebar" :class="{ 'sidebar--open': sidebarOpen }">
      <div class="sidebar__top">
        <div class="brand">
          <span class="brand__mark">知</span>
          <span>知屿</span>
        </div>
        <button class="mobile-close" aria-label="关闭资料栏" @click="sidebarOpen = false">×</button>
      </div>

      <section class="library-heading">
        <div>
          <p class="eyebrow eyebrow--ink">我的资料</p>
          <h2>知识库</h2>
        </div>
        <span class="count-badge">{{ readyCount }}</span>
      </section>

      <label
        class="upload-zone"
        :class="{ 'upload-zone--active': dragging, 'upload-zone--busy': uploading }"
        @dragenter.prevent="dragging = true"
        @dragover.prevent
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <input ref="fileInput" type="file" accept=".txt,.md,.pdf,.docx" :disabled="uploading" @change="uploadFiles($event.target.files)" />
        <span class="upload-icon" aria-hidden="true">↥</span>
        <strong>{{ uploading ? '正在解析并建立索引…' : '添加一份文档' }}</strong>
        <small>{{ uploading ? '请勿关闭页面' : '拖放或点击 · 最大 20 MB' }}</small>
      </label>

      <p v-if="uploadError" class="sidebar-error" role="alert">{{ uploadError }}</p>

      <div class="document-list">
        <div v-if="loadingDocuments" class="document-skeleton" v-for="n in 3" :key="n"></div>
        <p v-else-if="!documents.length" class="empty-documents">尚未添加资料。<br />支持 PDF、DOCX、TXT 和 MD。</p>
        <article v-for="document in documents" v-else :key="document.id" class="document-item">
          <div class="file-glyph">{{ document.file_type.toUpperCase().slice(0, 4) }}</div>
          <div class="document-info">
            <strong :title="document.original_name">{{ document.original_name }}</strong>
            <span v-if="document.status === 'ready'">{{ document.chunks_count }} 个片段 · {{ formatBytes(document.file_size) }}</span>
            <span v-else-if="document.status === 'failed'" class="status-failed" :title="document.error_message">处理失败 · {{ document.error_message }}</span>
            <span v-else>正在处理…</span>
          </div>
          <button class="delete-button" :aria-label="`删除 ${document.original_name}`" @click="removeDocument(document)">×</button>
        </article>
      </div>

      <div class="sidebar__footer">
        <div class="privacy-note">
          <span aria-hidden="true">⌾</span>
          <p><strong>资料本地存储</strong><small>文档文本与问题由千问云端处理</small></p>
        </div>
        <button class="user-row" @click="signOut">
          <span class="avatar">{{ auth.user?.username?.slice(0, 1).toUpperCase() }}</span>
          <span><strong>{{ auth.user?.username }}</strong><small>退出登录</small></span>
          <i aria-hidden="true">↗</i>
        </button>
      </div>
    </aside>

    <section class="conversation">
      <header class="conversation-header">
        <button class="menu-button" aria-label="打开资料栏" @click="sidebarOpen = true">☰</button>
        <div>
          <p class="eyebrow eyebrow--ink">问答空间</p>
          <h1>从你的资料中寻找答案</h1>
        </div>
        <div class="model-chip">
          <span class="pulse-dot pulse-dot--green"></span>
          <span>千问 · 云端</span>
        </div>
      </header>

      <div class="chat-scroll">
        <div class="chat-content">
          <article v-for="(message, index) in messages" :key="index" class="message" :class="`message--${message.role}`">
            <div v-if="message.role !== 'user'" class="assistant-avatar">知</div>
            <div class="message-body">
              <span v-if="message.role === 'assistant'" class="message-label">知屿</span>
              <p>{{ message.content || message.answer }}</p>
              <div v-if="message.refused" class="refusal-note">
                <span>资料边界</span>
                <small>没有找到足够依据，因此未生成推测性回答。</small>
              </div>
              <div v-if="message.sources?.length" class="sources">
                <p>回答依据</p>
                <details v-for="source in message.sources" :key="source.index">
                  <summary>
                    <span>[资料{{ source.index }}] {{ source.document_name }}</span>
                    <small>排序分 {{ Math.round((source.rerank_score ?? source.similarity) * 100) }}%</small>
                  </summary>
                  <blockquote>{{ source.excerpt }}{{ source.excerpt.length >= 180 ? '…' : '' }}</blockquote>
                </details>
              </div>
            </div>
          </article>

          <article v-if="asking" class="message message--assistant">
            <div class="assistant-avatar">知</div>
            <div class="message-body">
              <span class="message-label">知屿</span>
              <div class="typing"><i></i><i></i><i></i></div>
            </div>
          </article>
          <div ref="chatEnd"></div>
        </div>
      </div>

      <footer class="composer-wrap">
        <form class="composer" @submit.prevent="ask">
          <textarea
            v-model="question"
            rows="1"
            maxlength="2000"
            :disabled="asking"
            :placeholder="readyCount ? '询问你的文档…' : '请先上传至少一份可用文档'"
            @keydown="onQuestionKeydown"
          ></textarea>
          <button :disabled="!canAsk" aria-label="发送问题">↑</button>
        </form>
        <p>仅根据 {{ readyCount }} 份可用文档回答 · Enter 发送，Shift + Enter 换行</p>
      </footer>
    </section>
  </main>
</template>
