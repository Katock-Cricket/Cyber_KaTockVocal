<script setup lang="ts">
import { MusicalNotes, List, Settings } from "@vicons/ionicons5"
import {
  NConfigProvider,
  NDialogProvider,
  NIcon,
  NLayout,
  NLayoutContent,
  NLayoutSider,
  NMessageProvider,
  darkTheme,
  dateZhCN,
  lightTheme,
  zhCN,
} from "naive-ui"
import { computed } from "vue"
import { RouterLink, RouterView } from "vue-router"
import HealthBar from "./components/HealthBar.vue"
import LoginDialog from "./components/LoginDialog.vue"
import { useEventStream } from "./composables/useEventStream"
import { useAppStore } from "./stores/app"

const store = useAppStore()
const theme = computed(() => (store.theme === "dark" ? darkTheme : lightTheme))
const overrides = {
  common: {
    primaryColor: "#C084FC",
    primaryColorHover: "#D8B4FE",
    primaryColorPressed: "#A855F7",
    primaryColorSuppl: "#67E8F9",
    borderRadius: "16px",
    fontFamily: '"Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  },
}

void store.boot()
useEventStream(() => {
  void store.refreshHealth()
  void store.refreshJobs()
})
</script>

<template>
  <n-config-provider :theme="theme" :theme-overrides="overrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <n-layout has-sider class="shell">
          <n-layout-sider bordered :width="220" content-style="padding: 18px 14px">
            <div class="brand">
              <strong>KaTock Vocal</strong>
              <span>物料准备</span>
            </div>
            <nav>
              <router-link class="nav-link" to="/">
                <n-icon :component="MusicalNotes" /> 搜歌
              </router-link>
              <router-link class="nav-link" to="/queue">
                <n-icon :component="List" /> 队列
              </router-link>
              <router-link class="nav-link" to="/settings">
                <n-icon :component="Settings" /> 设置
              </router-link>
            </nav>
          </n-layout-sider>
          <n-layout>
            <health-bar />
            <n-layout-content content-style="padding: 24px 28px 48px">
              <router-view />
            </n-layout-content>
          </n-layout>
        </n-layout>
        <login-dialog />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<style scoped>
.shell {
  min-height: 100vh;
}
</style>
