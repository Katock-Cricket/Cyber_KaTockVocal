<script setup lang="ts">
import { VISIBLE_STEPS, STEP_NAME, STEP_STATUS } from "../constants/status"
import type { StepView } from "../api/client"

const props = defineProps<{ steps: StepView[] }>()

function stepOf(name: string): StepView | undefined {
  return props.steps.find((item) => item.name === name)
}
</script>

<template>
  <div>
    <div class="stage-bar">
      <div
        v-for="name in VISIBLE_STEPS"
        :key="name"
        class="stage"
        :class="[stepOf(name)?.status, stepOf(name)?.estimated ? 'estimated' : '']"
        :title="`${STEP_NAME[name]} ${STEP_STATUS[stepOf(name)?.status || 'pending']}`"
      >
        <span :style="{ width: `${stepOf(name)?.status === 'done' || stepOf(name)?.status === 'skipped' ? 100 : stepOf(name)?.progress || 0}%` }" />
      </div>
    </div>
    <div v-if="steps.some((item) => item.estimated && item.status === 'running')" class="muted" style="margin-top: 6px">
      估算进度
    </div>
  </div>
</template>
