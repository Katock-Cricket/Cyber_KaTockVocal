<script setup lang="ts">
import { NButton, NCard, NInput, NSpace, NTag, useMessage } from "naive-ui"
import { ref } from "vue"
import { useRouter } from "vue-router"
import { api, type Track } from "../api/client"
import { useAppStore } from "../stores/app"
import { artwork, clock } from "../utils/format"

const store = useAppStore()
const router = useRouter()
const message = useMessage()
const text = ref("")
const offset = ref(0)
const hasMore = ref(false)

function looksLikeBatch(value: string): boolean {
  return value.includes("music.apple.com") || value.includes("\n")
}

async function submitOne(track: Track) {
  const created = await api.createJobs([track])
  const first = created.jobs[0]
  message.success(first?.reused ? "这首已经在队列里" : "已加入队列")
  await store.refreshJobs()
  await router.push("/queue")
}

async function run() {
  const query = text.value.trim()
  if (!query) return
  store.loading = true
  store.error = ""
  try {
    if (looksLikeBatch(query)) {
      const resolved = await api.resolve(query)
      store.batch = resolved.tracks
      store.batchNotes = resolved.notes
      if (resolved.direct && resolved.tracks[0]) {
        await submitOne(resolved.tracks[0])
        return
      }
      if (!resolved.tracks.length) {
        message.warning(resolved.notes[0] || "未找到，建议改用「歌手 + 歌名」或直接粘贴链接")
        return
      }
      await router.push("/batch")
      return
    }
    offset.value = 0
    const result = await api.search(query, 0)
    store.tracks = result.tracks
    store.query = query
    hasMore.value = result.hasMore
    if (!result.tracks.length) {
      message.warning("未找到，建议改用「歌手 + 歌名」重搜，或直接粘贴链接")
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : "搜索失败")
  } finally {
    store.loading = false
  }
}

async function more() {
  const result = await api.search(store.query, offset.value + 10)
  offset.value += 10
  const known = new Set(store.tracks.map((item) => item.trackId))
  store.tracks.push(...result.tracks.filter((item) => !known.has(item.trackId)))
  hasMore.value = result.hasMore
}

async function openPrepared(track: Track) {
  await api.openFolder(track.trackId)
}
</script>

<template>
  <div class="page">
    <n-space>
      <n-input
        v-model:value="text"
        size="large"
        placeholder="歌名，或粘贴 Apple Music 链接"
        style="width: min(640px, 70vw)"
        @keyup.enter="run"
      />
      <n-button type="primary" size="large" :loading="store.loading" @click="run">搜索</n-button>
    </n-space>
    <div v-if="!store.tracks.length" class="empty">输入歌名，或粘贴单曲、专辑、歌单链接。</div>
    <n-card v-for="track in store.tracks" :key="track.trackId" embedded>
      <div class="row-card">
        <img v-if="track.artworkUrl" class="cover" :src="artwork(track.artworkUrl)" alt="" />
        <div v-else class="cover" />
        <div>
          <strong>{{ track.title }}</strong>
          <div class="muted">{{ track.artist }} · {{ track.album }} · {{ track.year || "年份未知" }} · {{ clock(track.durationS) }}</div>
          <div class="tags" style="margin-top: 8px">
            <n-tag v-for="tag in track.versionTags" :key="tag" type="warning" size="small">{{ tag }}</n-tag>
            <n-tag v-if="track.prepared" type="success" size="small" style="cursor: pointer" @click="openPrepared(track)">已备料</n-tag>
          </div>
        </div>
        <n-button type="primary" secondary @click="submitOne(track)">准备</n-button>
      </div>
    </n-card>
    <n-button v-if="hasMore" @click="more">加载更多</n-button>
  </div>
</template>
