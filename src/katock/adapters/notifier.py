"""队列结束时的桌面通知和提示音。"""

from __future__ import annotations

import winsound


def notify(title: str, body: str) -> None:
    try:
        from windows_toasts import Toast, WindowsToaster

        toaster = WindowsToaster("Cyber_KaTockVocal")
        toast = Toast()
        toast.text_fields = [title, body]
        toaster.show_toast(toast)
    except Exception:
        pass
    winsound.MessageBeep(winsound.MB_ICONASTERISK)
