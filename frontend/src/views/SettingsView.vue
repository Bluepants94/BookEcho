<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import { useSettingsStore } from '@/stores/settings'
import { usePlayerStore } from '@/stores/player'
import { isMimoProvider } from '@/utils/ttsSettings'

const settings = useSettingsStore()
const player = usePlayerStore()
const form = reactive({ ...settings.tts })
const cacheForm = reactive({ ...settings.cache })
const saving = ref(false)
const toastVisible = ref(false)
let toastTimer = null

const showMimoStyle = computed(() => isMimoProvider(form))

watch(
  () => [form.provider, form.base_url, form.model],
  () => {
    // no-op: computed reacts automatically
  },
)

function showToast() {
  toastVisible.value = true
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastVisible.value = false
    toastTimer = null
  }, 1600)
}

async function save() {
  if (saving.value) return
  saving.value = true
  try {
    // Cache window changes never invalidate audio.
    settings.updateCache({
      cache_chapters: cacheForm.cache_chapters,
    })
    // Only TTS parameter changes can invalidate the audio cache fingerprint.
    const { fingerprintChanged } = settings.updateTts(form)
    Object.assign(form, settings.tts)
    Object.assign(cacheForm, settings.cache)

    // Persist to server so rebuilds / browser clears do not drop settings.
    await settings.persistToServer()

    if (fingerprintChanged) {
      await player.invalidateAfterSettingsChange()
    }
    // Never surface long instructional copy — just a brief "已保存" toast.
    showToast()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await settings.hydrateFromServer()
  Object.assign(form, settings.tts)
  Object.assign(cacheForm, settings.cache)
})

onUnmounted(() => {
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <div class="page">
    <PageHeader title="API 设置" back />
    <div v-if="toastVisible" class="settings-toast" role="status" aria-live="polite">已保存</div>
    <form class="card form-card" @submit.prevent="save">
      <label class="field">
        <span>Provider</span>
        <select v-model="form.provider">
          <option value="auto">自动识别</option>
          <option value="mimo">Mimo兼容 (/chat/completions)</option>
          <option value="openai">OpenAI兼容 (/v1/audio/speech)</option>
        </select>
      </label>
      <label class="field">
        <span>Base URL</span>
        <input v-model.trim="form.base_url" placeholder="https://api.example.com/v1" />
      </label>
      <label class="field">
        <span>API Key</span>
        <input v-model.trim="form.api_key" type="password" placeholder="请输入 API Key" />
      </label>
      <p class="muted settings-hint">API 设置会同步到服务器，登录后可跨设备恢复；请勿在公共设备填写密钥。</p>
      <label class="field">
        <span>Model</span>
        <input v-model.trim="form.model" placeholder="请输入模型名" />
      </label>
      <label class="field">
        <span>Voice</span>
        <input v-model.trim="form.voice" placeholder="请输入音色" />
      </label>
      <label v-if="showMimoStyle" class="field">
        <span>朗读风格（Mimo user prompt）</span>
        <textarea
          v-model.trim="form.style"
          rows="3"
          placeholder="可选：描述朗读风格"
        />
      </label>
      <label v-if="showMimoStyle" class="field">
        <span>Audio Format</span>
        <select v-model="form.audio_format">
          <option value="pcm16">pcm16</option>
          <option value="mp3">mp3</option>
          <option value="wav">wav</option>
        </select>
      </label>
      <div class="settings-divider" role="separator" />
      <h3 class="settings-subhead">音频缓存窗口</h3>
      <p class="muted settings-hint">
        点击播放后按章节窗口预缓存音频；仅修改 TTS 参数并保存时才会使旧音频缓存失效。
      </p>
      <label class="field">
        <span>缓存章数</span>
        <input
          v-model.number="cacheForm.cache_chapters"
          type="number"
          min="0"
          max="10"
          step="1"
        />
      </label>

      <button class="btn primary block" type="submit" :disabled="saving">
        {{ saving ? '保存中…' : '保存' }}
      </button>
    </form>
  </div>
</template>
