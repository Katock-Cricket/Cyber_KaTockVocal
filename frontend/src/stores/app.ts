import { defineStore } from "pinia"
import { api, type HealthPayload, type JobView, type Track } from "../api/client"

export const useAppStore = defineStore("app", {
  state: () => ({
    theme: (localStorage.getItem("katock-theme") as "dark" | "light" | null) || "dark",
    health: null as HealthPayload | null,
    jobs: [] as JobView[],
    etaSeconds: 0,
    queuePaused: false,
    tracks: [] as Track[],
    batch: [] as Track[],
    batchNotes: [] as string[],
    query: "",
    loading: false,
    loginTick: 0,
    error: "",
  }),
  actions: {
    setTheme(theme: "dark" | "light") {
      this.theme = theme
      localStorage.setItem("katock-theme", theme)
    },
    async refreshHealth() {
      this.health = await api.health()
      this.queuePaused = this.health.queuePaused
    },
    async refreshJobs() {
      const payload = await api.jobs()
      this.jobs = payload.jobs
      this.etaSeconds = payload.etaSeconds
      this.queuePaused = payload.queuePaused
    },
    askLogin() {
      this.loginTick += 1
    },
    async boot() {
      await Promise.all([this.refreshHealth(), this.refreshJobs()])
    },
  },
})
