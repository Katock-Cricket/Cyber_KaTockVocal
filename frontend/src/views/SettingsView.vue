<script setup lang="ts">
import {
  NButton,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSpace,
  useDialog,
  useMessage,
} from "naive-ui"
import { onMounted, reactive, ref } from "vue"
import { api } from "../api/client"
import { FAILED_AT } from "../constants/status"
import { useAppStore } from "../stores/app"

const message = useMessage()
const dialog = useDialog()
const store = useAppStore()
const flags = reactive({
  appleIdSet: false,
  applePasswordSet: false,
  mediaUserTokenSet: false,
  translatorKeySet: false,
})
const form = reactive({
  outputRoot: "",
  dockerDesktop: "",
  wrapperDir: "",
  gpacDir: "",
  ffmpegDir: "",
  uvrDir: "",
  downloaderSrc: "",
  storefront: "cn",
  separationConcurrency: 2,
  translateConcurrency: 1,
  pass1Model: "",
  pass2Model: "",
  translatorBaseUrl: "",
  translatorModel: "",
  appleId: "",
  applePassword: "",
  mediaUserToken: "",
  translatorApiKey: "",
})
const testing = ref(false)

onMounted(async () => {
  const settings = await api.settings()
  form.outputRoot = settings.outputRoot
  form.dockerDesktop = settings.dockerDesktop
  form.wrapperDir = settings.wrapperDir
  form.gpacDir = settings.gpacDir
  form.ffmpegDir = settings.ffmpegDir
  form.uvrDir = settings.uvrDir
  form.downloaderSrc = settings.downloaderSrc
  form.storefront = settings.storefront
  form.separationConcurrency = settings.separationConcurrency
  form.translateConcurrency = settings.translateConcurrency
  form.pass1Model = settings.pass1Model
  form.pass2Model = settings.pass2Model
  form.translatorBaseUrl = settings.translatorBaseUrl
  form.translatorModel = settings.translatorModel
  flags.appleIdSet = settings.appleIdSet
  flags.applePasswordSet = settings.applePasswordSet
  flags.mediaUserTokenSet = settings.mediaUserTokenSet
  flags.translatorKeySet = settings.translatorKeySet
})

function secret(value: string): string | undefined {
  return value === "" ? undefined : value
}

async function save() {
  try {
    await api.saveSettings({
      outputRoot: form.outputRoot,
      dockerDesktop: form.dockerDesktop,
      wrapperDir: form.wrapperDir,
      gpacDir: form.gpacDir,
      ffmpegDir: form.ffmpegDir,
      uvrDir: form.uvrDir,
      downloaderSrc: form.downloaderSrc,
      storefront: form.storefront,
      separationConcurrency: form.separationConcurrency,
      translateConcurrency: form.translateConcurrency,
      pass1Model: form.pass1Model,
      pass2Model: form.pass2Model,
      translatorBaseUrl: form.translatorBaseUrl,
      translatorModel: form.translatorModel,
      appleId: secret(form.appleId),
      applePassword: secret(form.applePassword),
      mediaUserToken: secret(form.mediaUserToken),
      translatorApiKey: secret(form.translatorApiKey),
    })
    message.success("已保存")
    await store.refreshHealth()
  } catch (error) {
    message.error(error instanceof Error ? error.message : "保存失败")
  }
}

async function testConnection() {
  testing.value = true
  try {
    const result = await api.testTranslator({
      baseUrl: form.translatorBaseUrl,
      model: form.translatorModel,
      apiKey: form.translatorApiKey || undefined,
    })
    if (result.ok) message.success(result.detail)
    else message.error(`${FAILED_AT[result.failedAt] || "连接"}：${result.detail}`)
  } catch (error) {
    message.error(error instanceof Error ? error.message : "测试失败")
  } finally {
    testing.value = false
  }
}

function clearHistory() {
  dialog.warning({
    title: "清理历史记录",
    content: "会清除任务和已备料记录，磁盘上的歌曲文件会保留。",
    positiveText: "清理",
    negativeText: "取消",
    onPositiveClick: async () => {
      await api.clearHistory()
      await store.refreshJobs()
      message.success("历史记录已清理")
    },
  })
}

function showLogin() {
  store.askLogin()
}
</script>

<template>
  <div class="page">
    <n-form label-placement="top">
      <n-form-item label="输出根目录">
        <n-input v-model:value="form.outputRoot" />
      </n-form-item>
      <n-form-item label="Docker Desktop">
        <n-input v-model:value="form.dockerDesktop" />
      </n-form-item>
      <n-form-item label="Wrapper 目录">
        <n-input v-model:value="form.wrapperDir" />
      </n-form-item>
      <n-form-item label="GPAC 目录">
        <n-input v-model:value="form.gpacDir" />
      </n-form-item>
      <n-form-item label="ffmpeg 目录">
        <n-input v-model:value="form.ffmpegDir" />
      </n-form-item>
      <n-form-item label="UVR 目录">
        <n-input v-model:value="form.uvrDir" />
      </n-form-item>
      <n-form-item label="下载器源码目录">
        <n-input v-model:value="form.downloaderSrc" />
      </n-form-item>
      <n-form-item label="店面 storefront">
        <n-input v-model:value="form.storefront" />
      </n-form-item>
      <n-space>
        <n-form-item label="分离并发（1-2）">
          <n-input-number v-model:value="form.separationConcurrency" :min="1" :max="2" />
        </n-form-item>
        <n-form-item label="翻译并发（1-3）">
          <n-input-number v-model:value="form.translateConcurrency" :min="1" :max="3" />
        </n-form-item>
      </n-space>
      <n-form-item label="pass1 模型">
        <n-input v-model:value="form.pass1Model" />
      </n-form-item>
      <n-form-item label="pass2 模型">
        <n-input v-model:value="form.pass2Model" />
      </n-form-item>
      <n-form-item label="翻译接口地址">
        <n-input v-model:value="form.translatorBaseUrl" />
      </n-form-item>
      <n-form-item label="翻译模型">
        <n-input v-model:value="form.translatorModel" />
      </n-form-item>
      <n-form-item :label="`翻译密钥${flags.translatorKeySet ? '（已设置，留空不修改）' : ''}`">
        <n-input v-model:value="form.translatorApiKey" type="password" show-password-on="click" />
      </n-form-item>
      <n-form-item :label="`Apple ID${flags.appleIdSet ? '（已设置）' : ''}`">
        <n-input v-model:value="form.appleId" />
      </n-form-item>
      <n-form-item :label="`Apple 密码${flags.applePasswordSet ? '（已设置）' : ''}`">
        <n-input v-model:value="form.applePassword" type="password" show-password-on="click" />
      </n-form-item>
      <n-form-item :label="`media-user-token${flags.mediaUserTokenSet ? '（已设置）' : ''}`">
        <n-input v-model:value="form.mediaUserToken" type="password" show-password-on="click" />
      </n-form-item>
      <n-space>
        <n-button type="primary" @click="save">保存</n-button>
        <n-button :loading="testing" @click="testConnection">测试连接</n-button>
        <n-button @click="showLogin">登录 Apple</n-button>
        <n-button type="error" secondary @click="clearHistory">清理历史记录（保留文件）</n-button>
      </n-space>
    </n-form>
    <p class="muted">密钥只以本机 DPAPI 密文保存。若还没保存翻译密钥，启动时会读取环境变量 OPENAI_API_KEY。</p>
  </div>
</template>
