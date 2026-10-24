<script setup lang="ts">
import { NButton, NForm, NFormItem, NInput, NModal, useMessage } from "naive-ui"
import { computed, ref, watch } from "vue"
import { api } from "../api/client"
import { useAppStore } from "../stores/app"

const store = useAppStore()
const message = useMessage()
const appleId = ref("")
const password = ref("")
const code = ref("")
const open = ref(false)
const remain = ref(0)
let timer = 0

const phase = computed(() => store.health?.auth.phase || "idle")
const manual = ref(false)
const needCode = computed(
  () => !manual.value && (phase.value === "need_2fa" || phase.value === "checking" || phase.value === "expired"),
)

watch(phase, (value) => {
  if (value === "need_2fa" || value === "expired" || value === "error") open.value = true
  if (value === "ok") {
    open.value = false
    manual.value = false
    message.success("Apple 登录成功")
  }
})

watch(
  () => store.loginTick,
  () => {
    manual.value = true
    open.value = true
  },
)

watch(
  () => store.health?.auth.deadlineEpoch,
  (deadline) => {
    window.clearInterval(timer)
    if (!deadline) {
      remain.value = 0
      return
    }
    const tick = () => {
      remain.value = Math.max(0, Math.ceil(deadline - Date.now() / 1000))
    }
    tick()
    timer = window.setInterval(tick, 500)
  },
)

async function login(restart = false) {
  try {
    await api.login(appleId.value.trim(), password.value, restart)
    message.info("正在连接 Wrapper")
  } catch (error) {
    message.error(error instanceof Error ? error.message : "登录失败")
  }
}

async function submitCode() {
  try {
    await api.twoFa(code.value.trim())
  } catch (error) {
    message.error(error instanceof Error ? error.message : "验证码提交失败")
  }
}
</script>

<template>
  <n-modal v-model:show="open" preset="card" title="Apple 登录" style="width: 420px">
    <p class="muted">{{ store.health?.auth.message || "账号只保存在本机。" }}</p>
    <n-form v-if="!needCode">
      <n-form-item label="Apple ID">
        <n-input v-model:value="appleId" />
      </n-form-item>
      <n-form-item label="密码">
        <n-input v-model:value="password" type="password" show-password-on="click" />
      </n-form-item>
      <n-button type="primary" :disabled="!appleId || !password" @click="login(false)">登录</n-button>
    </n-form>
    <n-form v-else>
      <n-form-item :label="remain ? `验证码（${remain} 秒）` : '验证码'">
        <n-input v-model:value="code" maxlength="6" placeholder="6 位数字" />
      </n-form-item>
      <n-button type="primary" :disabled="code.length !== 6" @click="submitCode">提交验证码</n-button>
      <n-button style="margin-left: 8px" @click="login(true)">重新发起</n-button>
    </n-form>
  </n-modal>
</template>
