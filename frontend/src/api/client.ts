export interface Track {
  trackId: string
  title: string
  artist: string
  album: string
  albumArtist?: string
  year: number | null
  durationS: number
  trackNumber?: number
  discNumber?: number
  artworkUrl: string
  storefront: string
  url: string
  audioLocale?: string
  prepared?: boolean
  versionTags?: string[]
  estimatedBytes?: number
}

export interface StepView {
  name: string
  status: string
  progress: number
  estimated: boolean
  etaSeconds: number | null
  etaLabel: string
  elapsedS: number | null
  errorDetail: string | null
  errorKind: string | null
  note: string
  startedAt: string | null
  endedAt: string | null
}

export interface JobView {
  id: string
  trackId: string
  title: string
  artist: string
  album: string
  year: number | null
  durationS: number
  artworkUrl: string
  dirPath: string | null
  status: string
  errorSummary: string | null
  errorKind: string | null
  progress: number
  missing: string[]
  source: { sampleRate?: number | null; bitDepth?: number | null } | null
  lyrics: { language?: string | null; bilingual?: boolean; timed?: boolean; note?: string; tokenUsage?: number } | null
  steps: StepView[]
  log?: string
  tokenUsage?: number
  bilingualFailed?: boolean
  translateLyrics?: boolean | null
  translateEnabled?: boolean
  createdAt?: string
  updatedAt?: string
}

export interface HealthItem {
  item: string
  ok: boolean
  level: string
  detail: string
  checkedAt: string | null
}

export interface HealthPayload {
  items: HealthItem[]
  canStartJobs: boolean
  queuePaused: boolean
  auth: { phase: string; message: string; deadlineEpoch: number | null }
}

export interface SettingsPayload {
  outputRoot: string
  dockerDesktop: string
  wrapperDir: string
  gpacDir: string
  ffmpegDir: string
  uvrDir: string
  downloaderSrc: string
  storefront: string
  separationConcurrency: number
  translateConcurrency: number
  pass1Model: string
  pass2Model: string
  translatorBaseUrl: string
  translatorModel: string
  autoTranslateLyrics: boolean
  appleIdSet: boolean
  applePasswordSet: boolean
  mediaUserTokenSet: boolean
  translatorKeySet: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      detail = response.statusText
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export const api = {
  health: () => request<HealthPayload>("/api/health"),
  recheck: () => request<{ status: string }>("/api/health/recheck", { method: "POST" }),
  startDocker: () => request<{ status: string }>("/api/env/docker/start", { method: "POST" }),
  login: (appleId: string, password: string, restart: boolean) =>
    request<{ status: string }>("/api/auth/apple/login", {
      method: "POST",
      body: JSON.stringify({ appleId, password, restart }),
    }),
  twoFa: (code: string) =>
    request<{ status: string }>("/api/auth/apple/2fa", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  search: (q: string, offset = 0) =>
    request<{ tracks: Track[]; hasMore: boolean }>(`/api/search?q=${encodeURIComponent(q)}&offset=${offset}`),
  resolve: (text: string) =>
    request<{ tracks: Track[]; notes: string[]; direct: boolean }>("/api/resolve", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  createJobs: (tracks: Track[]) =>
    request<{ jobs: { jobId: string; trackId: string; reused: boolean }[] }>("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ tracks }),
    }),
  jobs: () => request<{ jobs: JobView[]; queuePaused: boolean; etaSeconds: number }>("/api/jobs"),
  job: (id: string) => request<JobView>(`/api/jobs/${id}`),
  cancel: (id: string) => request<{ status: string }>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  rerun: (id: string, step?: string, force = false) =>
    request<{ status: string }>(`/api/jobs/${id}/rerun`, {
      method: "POST",
      body: JSON.stringify({ step: step ?? null, force }),
    }),
  setTranslate: (id: string, enabled: boolean) =>
    request<{ status: string }>(`/api/jobs/${id}/translate`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  pause: () => request<{ status: string }>("/api/queue/pause", { method: "POST" }),
  resume: () => request<{ status: string }>("/api/queue/resume", { method: "POST" }),
  settings: () => request<SettingsPayload>("/api/settings"),
  saveSettings: (body: Record<string, unknown>) =>
    request<{ status: string }>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  testTranslator: (body: { baseUrl?: string; model?: string; apiKey?: string }) =>
    request<{ ok: boolean; failedAt: string; detail: string }>("/api/settings/translator/test", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  clearHistory: () => request<{ status: string }>("/api/settings/history/clear", { method: "POST" }),
  openFolder: (trackId: string) =>
    request<{ path: string }>(`/api/tracks/${trackId}/open-folder`, { method: "POST" }),
}
