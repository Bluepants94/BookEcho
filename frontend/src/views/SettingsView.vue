<script setup>
import { computed, reactive, ref, watch } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import { useSettingsStore } from '@/stores/settings'
import { usePlayerStore } from '@/stores/player'
import { isMimoProvider } from '@/utils/ttsSettings'

const settings = useSettingsStore()
const player = usePlayerStore()
const form = reactive({ ...settings.tts })
const cacheForm = reactive({ ...settings.cache })
const saved = ref(false)
const savedMsg = ref('')

const showMimoStyle = computed(() => isMimoProvider(form))

watch(
  () => [form.provider, form.base_url, form.model],
  () => {
    // no-op: computed reacts automatically
  },
)

async function save() {
  settings.updateCache({
    cache_chapters: cacheForm.cache_chapters,
  })
  const { fingerprintChanged } = settings.updateTts(form)
  // Keep reactive forms in sync with normalized values.
  Object.assign(form, settings.tts)
  Object.assign(cacheForm, settings.cache)

  if (fingerprintChanged) {
    await player.invalidateAfterSettingsChange()
    savedMsg.value = '已保存：TTS 变更后需重新合成，请手动点击播放'
  } else {
    savedMsg.value = '已保存：点击播放后按窗口预缓存音频'
  }
  saved.value = true
  setTimeout(() => {
    saved.value = false
  }, 2200)
}
</script>

<template>
  <div class="page">
    <PageHeader title="API 设置" back />
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
      <p class="muted settings-hint">API Key 仅保存在本机浏览器本地存储，请勿在公共设备填写；清除站点数据会一并删除。</p>
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
        点击播放后按章节窗口预缓存音频；修改 TTS 后旧缓存失效，需重新合成。
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

      <button class="btn primary block" type="submit">保存</button>
      <p v-if="saved" class="form-ok">{{ savedMsg || '已保存' }}</p>
    </form>
  </div>
</template>
