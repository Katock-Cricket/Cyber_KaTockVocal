<script setup lang="ts">
import { NButton, NCard, NCheckbox, NSpace, useMessage } from "naive-ui"
import { computed, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { api } from "../api/client"
import { useAppStore } from "../stores/app"
import { clock, megabytes } from "../utils/format"

const store = useAppStore()
const router = useRouter()
const message = useMessage()
const selected = ref<string[]>([])

watch(
  () => store.batch.map((item) => item.trackId).join(","),
  () => {
    selected.value = store.batch.filter((item) => !item.prepared).map((item) => item.trackId)
  },
  { immediate: true },
)

const chosen = computed(() => store.batch.filter((item) => selected.value.includes(item.trackId)))
const volume = computed(() => chosen.value.reduce((sum, item) => sum + (item.estimatedBytes || 0), 0))

function toggle(trackId: string, checked: boolean) {
  if (checked) {
    if (!selected.value.includes(trackId)) selected.value.push(trackId)
    return
  }
  selected.value = selected.value.filter((item) => item !== trackId)
}

async function start() {
  if (!chosen.value.length) {
    message.warning("先勾选曲目")
    return
  }
  if (chosen.value.length > 50) {
    message.warning("单次最多 50 首，请分批")
    return
  }
  try {
    await api.createJobs(chosen.value)
    message.success(`已加入 ${chosen.value.length} 首`)
    await store.refreshJobs()
    await router.push("/queue")
  } catch (error) {
    message.error(error instanceof Error ? error.message : "提交失败")
  }
}
</script>

<template>
  <div class="page">
    <n-space justify="space-between" align="center">
      <div>
        <strong>曲目清单</strong>
        <div class="muted">默认勾选未备料曲目。预计体积 {{ megabytes(volume) }}。</div>
      </div>
      <n-button type="primary" @click="start">开始准备</n-button>
    </n-space>
    <n-card v-for="note in store.batchNotes" :key="note" size="small">{{ note }}</n-card>
    <div v-if="!store.batch.length" class="empty">还没有解析出的曲目。回到搜歌页粘贴专辑或歌单链接。</div>
    <n-card v-for="(track, index) in store.batch" :key="track.trackId" embedded>
      <div class="row-card" style="grid-template-columns: 28px 1fr auto">
        <n-checkbox
          :checked="selected.includes(track.trackId)"
          @update:checked="(value: boolean) => toggle(track.trackId, value)"
        />
        <div>
          <strong>{{ index + 1 }}. {{ track.title }}</strong>
          <div class="muted">
            {{ track.artist }} · {{ clock(track.durationS) }} · {{ megabytes(track.estimatedBytes || 0) }}
            <span v-if="track.prepared"> · 已备料</span>
          </div>
        </div>
      </div>
    </n-card>
  </div>
</template>
