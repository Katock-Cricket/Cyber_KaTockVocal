<script setup lang="ts">
import { NButton, NPopover, NSpace, NTag } from "naive-ui"
import { computed } from "vue"
import { useRouter } from "vue-router"
import { api } from "../api/client"
import { HEALTH_LABEL } from "../constants/status"
import { useAppStore } from "../stores/app"

const store = useAppStore()
const router = useRouter()
const summary = computed(() => {
  const items = store.health?.items || []
  const bad = items.filter((item) => !item.ok)
  const waiting = items.filter((item) => item.level === "wait")
  if (!items.length) return "正在体检"
  if (waiting.length) return waiting[0]?.detail || "正在等待环境"
  if (!bad.length) return "环境就绪"
  return `${bad.length} 项需要处理`
})

async function recheck() {
  await api.recheck()
  await store.refreshHealth()
}

function openLogin() {
  void router.push("/settings")
}
</script>

<template>
  <div class="bar">
    <n-popover trigger="click" placement="bottom-start" style="max-width: 560px">
      <template #trigger>
        <n-button quaternary>{{ summary }}</n-button>
      </template>
      <n-space vertical>
        <div v-for="item in store.health?.items || []" :key="item.item" class="health-item">
          <n-tag :type="item.ok ? (item.level === 'warn' ? 'warning' : 'success') : item.level === 'wait' ? 'info' : 'error'" size="small">
            {{ HEALTH_LABEL[item.item] || item.item }}
          </n-tag>
          <span>{{ item.detail }}</span>
        </div>
        <n-space>
          <n-button size="small" @click="recheck">重新检查</n-button>
          <n-button size="small" @click="api.startDocker()">重新拉起 Docker</n-button>
          <n-button size="small" @click="openLogin">登录 / 设置</n-button>
        </n-space>
      </n-space>
    </n-popover>
    <n-button quaternary @click="store.setTheme(store.theme === 'dark' ? 'light' : 'dark')">
      {{ store.theme === "dark" ? "浅色" : "深色" }}
    </n-button>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 18px 0;
}
.health-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  line-height: 1.5;
}
</style>
