<script setup lang="ts">
import { NButton, NCard, NSpace, NTag, useMessage } from "naive-ui"
import { useRouter } from "vue-router"
import { api } from "../api/client"
import StageBar from "../components/StageBar.vue"
import { JOB_STATUS } from "../constants/status"
import { useAppStore } from "../stores/app"
import { artwork, remain } from "../utils/format"

const store = useAppStore()
const router = useRouter()
const message = useMessage()

function tagType(status: string): "success" | "warning" | "error" | "info" | "default" {
  if (status === "done") return "success"
  if (status === "partial") return "warning"
  if (status === "failed") return "error"
  if (status === "running") return "info"
  return "default"
}

async function pause() {
  await api.pause()
  message.info("队列已暂停，进行中的阶段会停在当前步骤")
  await store.refreshJobs()
}

async function resume() {
  await api.resume()
  await store.refreshJobs()
}
</script>

<template>
  <div class="page">
    <n-space justify="space-between" align="center">
      <div>
        <strong>队列</strong>
        <div class="muted">整体剩余 {{ remain(store.etaSeconds) }}</div>
      </div>
      <n-space>
        <n-button v-if="!store.queuePaused" @click="pause">全部暂停</n-button>
        <n-button v-else type="primary" @click="resume">全部继续</n-button>
      </n-space>
    </n-space>
    <div v-if="!store.jobs.length" class="empty">还没有任务。去搜歌页挑一首吧。</div>
    <n-card v-for="job in store.jobs" :key="job.id" embedded style="cursor: pointer" @click="router.push(`/jobs/${job.id}`)">
      <div class="row-card">
        <img v-if="job.artworkUrl" class="cover" :src="artwork(job.artworkUrl, 160)" alt="" />
        <div v-else class="cover" />
        <div>
          <n-space align="center">
            <strong>{{ job.title }}</strong>
            <n-tag size="small" :type="tagType(job.status)">{{ JOB_STATUS[job.status] || job.status }}</n-tag>
          </n-space>
          <div class="muted">{{ job.artist }}</div>
          <div style="margin-top: 10px">
            <stage-bar :steps="job.steps" />
          </div>
          <div v-if="job.missing.length" class="muted" style="margin-top: 8px; color: #f87171">缺：{{ job.missing.join("、") }}</div>
        </div>
      </div>
    </n-card>
  </div>
</template>
