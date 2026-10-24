"""失败分类与中文建议。"""

from __future__ import annotations

ENV_NOT_READY = "env_not_ready"
AUTH = "auth"
UNAVAILABLE = "unavailable"
DISK = "disk"
SEPARATION = "separation"
TRANSLATION = "translation"
COVER = "cover"
LYRICS = "lyrics"
UNKNOWN = "unknown"

SUGGESTIONS: dict[str, str] = {
    ENV_NOT_READY: "先确认 Docker 与 Wrapper 已就绪，可在顶部体检条点「重新拉起」或「重试」。",
    AUTH: "Apple 登录已失效。请在登录框重新输入 Apple ID，或到设置页更新 media-user-token。",
    UNAVAILABLE: "该曲目在当前店面不可获取。请确认 storefront 与账号地区一致，或更换版本。",
    DISK: "磁盘空间或写入权限不足。请清理磁盘，并确认输出目录可写。",
    SEPARATION: "分离进程中断。中间文件已保留，可在任务详情只重跑分离。",
    TRANSLATION: "翻译未成功，已保留单语歌词。请检查接口地址、密钥和模型名后重跑歌词。",
    COVER: "封面没有拿到，其他物料照常。可稍后单步重跑封面。",
    LYRICS: "歌词没有拿到。请确认 media-user-token 后单步重跑歌词。",
    UNKNOWN: "请打开任务日志查看原始错误，确认对应程序的路径后重试。",
}


def suggestion(kind: str) -> str:
    return SUGGESTIONS.get(kind, SUGGESTIONS[UNKNOWN])
