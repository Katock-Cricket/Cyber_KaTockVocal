export function artwork(url: string | null | undefined, size = 300): string {
  if (!url) return ""
  return url.replaceAll("{w}", String(size)).replaceAll("{h}", String(size)).replaceAll("{f}", "jpg")
}

export function clock(seconds: number | null | undefined): string {
  const total = Math.max(0, Math.round(seconds || 0))
  const minutes = Math.floor(total / 60)
  const remain = total % 60
  return `${minutes}:${String(remain).padStart(2, "0")}`
}

export function remain(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "计算中"
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  const hours = Math.floor(minutes / 60)
  if (hours) return `${hours} 小时 ${minutes % 60} 分`
  if (minutes) return `${minutes} 分 ${total % 60} 秒`
  return `${total} 秒`
}

export function megabytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(0)} MB`
}
