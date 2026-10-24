export const JOB_STATUS: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  done: "完成",
  partial: "部分完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
}

export const STEP_STATUS: Record<string, string> = {
  pending: "待执行",
  waiting_env: "等待环境",
  running: "执行中",
  done: "完成",
  skipped: "已跳过",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
}

export const STEP_NAME: Record<string, string> = {
  download: "下载",
  cover: "封面",
  lyrics: "歌词",
  pass1: "分离 pass1",
  pass2: "分离 pass2",
  finalize: "校验落盘",
}

export const VISIBLE_STEPS = ["download", "cover", "lyrics", "pass1", "pass2"] as const

export const HEALTH_LABEL: Record<string, string> = {
  docker: "Docker",
  wrapper: "Wrapper 容器",
  wrapper_ports: "Wrapper 端口",
  wrapper_login: "Apple 登录",
  mp4box: "MP4Box",
  ffmpeg: "ffmpeg",
  separator: "分离工具",
  output_root: "输出目录",
  disk: "磁盘空间",
}

export const FAILED_AT: Record<string, string> = {
  base_url: "接口地址",
  api_key: "密钥",
  model: "模型名",
}
