import { onMounted, onUnmounted } from "vue"

export interface StreamEvent {
  id: number
  job_id: string | null
  kind: string
  payload: Record<string, unknown>
  created_at: string
}

export function useEventStream(onEvent: (event: StreamEvent) => void): void {
  let source: EventSource | null = null
  onMounted(() => {
    source = new EventSource("/api/events")
    source.onmessage = (message) => {
      onEvent(JSON.parse(message.data) as StreamEvent)
    }
  })
  onUnmounted(() => {
    source?.close()
  })
}
