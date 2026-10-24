import { createRouter, createWebHistory } from "vue-router"
import BatchView from "./views/BatchView.vue"
import JobView from "./views/JobView.vue"
import QueueView from "./views/QueueView.vue"
import SearchView from "./views/SearchView.vue"
import SettingsView from "./views/SettingsView.vue"

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "search", component: SearchView },
    { path: "/batch", name: "batch", component: BatchView },
    { path: "/queue", name: "queue", component: QueueView },
    { path: "/jobs/:id", name: "job", component: JobView },
    { path: "/settings", name: "settings", component: SettingsView },
  ],
})
