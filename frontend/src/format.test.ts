import { describe, expect, it } from "vitest"
import { JOB_STATUS, STEP_NAME, VISIBLE_STEPS } from "./constants/status"
import { artwork, clock, megabytes, remain } from "./utils/format"

describe("format", () => {
  it("fills artwork template", () => {
    expect(artwork("https://example/{w}x{h}.{f}", 300)).toBe("https://example/300x300.jpg")
    expect(artwork("")).toBe("")
  })

  it("formats clocks and remaining time", () => {
    expect(clock(354.4)).toBe("5:54")
    expect(remain(90)).toBe("1 分 30 秒")
    expect(remain(3700)).toBe("1 小时 1 分")
    expect(remain(null)).toBe("计算中")
    expect(megabytes(2 * 1024 * 1024)).toBe("2 MB")
  })
})

describe("status copy", () => {
  it("covers the queue states the interface shows", () => {
    expect(JOB_STATUS.partial).toBe("部分完成")
    expect(STEP_NAME.pass2).toBe("分离 pass2")
    expect(VISIBLE_STEPS).toEqual(["download", "cover", "lyrics", "pass1", "pass2"])
  })
})
