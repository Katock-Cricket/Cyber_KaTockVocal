<script setup lang="ts">
import { NButton, NCard, NSpace, NTag, useMessage } from "naive-ui"
import { onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import { api, type JobView } from "../api/client"
import { JOB_STATUS, STEP_NAME, STEP_STATUS } from "../constants/status"
import { artwork, clock, remain } from "../utils/format"

const route = useRoute()
const message = useMessage()
const job = ref<JobView | null>(null)

async function load() {
  job.value = await api.job(String(route.params.id))
}

onMounted(load)

async function openFolder() {
  if (!job.value) return
  try {
    await api.openFolder(job.value.trackId)
  } catch (error) {
    message.error(error instanceof Error ? error.message : "打不开文件夹")
  }
}

async function copyPath() {
  if (!job.value?.dirPath) return
  await navigator.clipboard.writeText(job.value.dirPath)
  message.success("路径已复制")
}

async function copyLog() {
  if (!job.value?.log) {
    message.info("还没有日志")
    return
  }
  await navigator.clipboard.writeText(job.value.log)
  message.success("日志已复制")
}

async function rerun(step?: string, force = false) {
  if (!job.value) return
  try {
    await api.rerun(job.value.id, step, force)
    message.success("已重新排队")
    await load()
  } catch (error) {
    message.error(error instanceof Error ? error.message : "重跑失败")
  }
}

async function cancel() {
  if (!job.value) return
  await api.cancel(job.value.id)
  await load()
}
</script>

<template>
  <div v-if="job" class="page">
    <div class="row-card">
      <img v-if="job.artworkUrl" class="cover" :src="artwork(job.artworkUrl, 400)" alt="" />
      <div v-else class="cover" />
      <div>
        <n-space align="center">
          <strong>{{ job.title }}</strong>
          <n-tag>{{ JOB_STATUS[job.status] || job.status }}</n-tag>
        </n-space>
        <div class="muted">{{ job.artist }} · {{ job.album }} · {{ clock(job.durationS) }}</div>
        <div v-if="job.source?.sampleRate" class="muted">原曲 {{ job.source.sampleRate }} Hz / {{ job.source.bitDepth }} bit</div>
        <div v-if="job.missing.length" style="color: #f87171">缺：{{ job.missing.join("、") }}</div>
        <div v-if="job.lyrics && job.lyrics.timed === false" style="color: #fbbf24">无时间轴</div>
        <div v-if="job.bilingualFailed" style="color: #f87171">双语失败</div>
        <div v-if="job.tokenUsage" class="muted">翻译 {{ job.tokenUsage }} token</div>
        <div v-if="job.errorSummary" class="muted">{{ job.errorSummary }}</div>
      </div>
    </div>
    <n-space>
      <n-button type="primary" @click="openFolder">打开文件夹</n-button>
      <n-button @click="copyPath">复制路径</n-button>
      <n-button @click="copyLog">复制完整日志</n-button>
      <n-button @click="rerun()">整首重跑</n-button>
      <n-button @click="rerun(undefined, true)">强制重跑</n-button>
      <n-button @click="cancel">取消</n-button>
    </n-space>
    <n-card v-for="step in job.steps" :key="step.name" size="small" :title="STEP_NAME[step.name] || step.name">
      <div class="muted">
        {{ STEP_STATUS[step.status] || step.status }}
        <span v-if="step.elapsedS != null"> · 实际 {{ remain(step.elapsedS) }}</span>
        <span v-if="step.etaLabel"> · {{ step.etaLabel }}</span>
        <span v-if="step.estimated && step.status === 'running'"> · 估算进度</span>
      </div>
      <div v-if="step.note">{{ step.note }}</div>
      <div v-if="step.errorDetail" style="white-space: pre-wrap">{{ step.errorDetail }}</div>
      <n-button
        v-if="step.name !== 'finalize'"
        size="small"
        style="margin-top: 8px"
        @click="rerun(step.name)"
      >
        重跑此步
      </n-button>
    </n-card>
  </div>
</template>
