"use client"

import * as React from "react"
import { ChevronDownIcon } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { apiFetch, normalizeFetchError } from "@/lib/api"
import { NumberInputField } from "@/components/settings/settings-shared"

type RuntimeConfig = {
  JOB_TIMEOUT_SECONDS: number
  OCR_PAGE_TIMEOUT_S: number
  OCR_TOTAL_TIMEOUT_S: number
  OCR_PADDLE_VL_PREDICT_TIMEOUT_S: number
  OCR_AI_RETRY_BACKOFF_BASE_S: number
  OCR_AI_RATE_LIMITED_MIN_DELAY_S: number
  SCANNED_RENDER_DPI: number
  OCR_AI_PAGE_CONCURRENCY_MAX: number
  OCR_AI_BLOCK_CONCURRENCY_MAX: number
  OCR_AI_RPM_MAX: number
  OCR_AI_TPM_MAX: number
  JWT_EXPIRATION_HOURS: number
}

const DEFAULT_RUNTIME_CONFIG: RuntimeConfig = {
  JOB_TIMEOUT_SECONDS: 1800,
  OCR_PAGE_TIMEOUT_S: 120,
  OCR_TOTAL_TIMEOUT_S: 3600,
  OCR_PADDLE_VL_PREDICT_TIMEOUT_S: 30,
  OCR_AI_RETRY_BACKOFF_BASE_S: 2,
  OCR_AI_RATE_LIMITED_MIN_DELAY_S: 5,
  SCANNED_RENDER_DPI: 150,
  OCR_AI_PAGE_CONCURRENCY_MAX: 100,
  OCR_AI_BLOCK_CONCURRENCY_MAX: 200,
  OCR_AI_RPM_MAX: 500,
  OCR_AI_TPM_MAX: 200000,
  JWT_EXPIRATION_HOURS: 168,
}

export function AdminSettings() {
  const [config, setConfig] = React.useState<RuntimeConfig>(DEFAULT_RUNTIME_CONFIG)
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [isOpen, setIsOpen] = React.useState(false)

  // Load current config on mount
  React.useEffect(() => {
    let mounted = true
    setLoading(true)
    setError(null)
    void apiFetch("/config/runtime")
      .then(async (res) => {
        if (!res.ok) throw new Error("Failed to load runtime config")
        const data = await res.json()
        if (mounted && data.config) {
          setConfig(data.config as RuntimeConfig)
        }
      })
      .catch((e) => {
        if (mounted) setError(normalizeFetchError(e, "加载运行时配置失败"))
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const handleSave = React.useCallback(async () => {
    setSaving(true)
    setError(null)
    try {
      const res = await apiFetch("/config/runtime", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => null)
        throw new Error(
          (errData && (errData as { detail?: string }).detail) ||
            `保存失败 (${res.status})`
        )
      }
      toast.success("运行时配置已保存。重启服务后生效。")
    } catch (e) {
      const msg = normalizeFetchError(e, "保存运行时配置失败")
      setError(msg)
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }, [config])

  const updateField = React.useCallback(
    (key: keyof RuntimeConfig, value: number | boolean) => {
      setConfig((prev) => ({ ...prev, [key]: value }))
      setError(null)
    },
    []
  )

  return (
    <div className="space-y-6">
      <div className="border border-border">
        <button
          type="button"
          className="flex w-full items-center justify-between px-4 py-3 text-left"
          onClick={() => setIsOpen((v) => !v)}
        >
          <div>
            <div className="flex items-center gap-2">
              <span className="font-sans text-sm font-semibold uppercase tracking-[0.14em]">
                运行时配置
              </span>
              <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
                服务端
              </Badge>
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              以下配置修改后需要重启服务生效
            </div>
          </div>
          <ChevronDownIcon
            className={cn(
              "size-4 text-muted-foreground transition-transform",
              isOpen && "rotate-180"
            )}
          />
        </button>
        {isOpen ? (
          <div className="grid gap-3 border-t border-border px-4 py-4">
            {loading ? (
              <div className="py-4 text-center text-xs text-muted-foreground">加载中...</div>
            ) : (
              <>
                {/* Timeouts */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <NumberInputField
                    id="runtime-job-timeout"
                    label="任务超时 (秒)"
                    hint="RQ / 内联线程作业超时时间"
                    value={config.JOB_TIMEOUT_SECONDS}
                    onChange={(v) => updateField("JOB_TIMEOUT_SECONDS", v)}
                  />
                  <NumberInputField
                    id="runtime-ocr-page-timeout"
                    label="OCR 单页超时 (秒)"
                    hint="单页 OCR 超时保护"
                    value={config.OCR_PAGE_TIMEOUT_S}
                    onChange={(v) => updateField("OCR_PAGE_TIMEOUT_S", v)}
                  />
                  <NumberInputField
                    id="runtime-ocr-total-timeout"
                    label="OCR 总超时 (秒)"
                    hint="整体 OCR 阶段超时"
                    value={config.OCR_TOTAL_TIMEOUT_S}
                    onChange={(v) => updateField("OCR_TOTAL_TIMEOUT_S", v)}
                  />
                  <NumberInputField
                    id="runtime-paddle-vl-timeout"
                    label="PaddleOCR-VL 预测超时 (秒)"
                    hint="AI OCR 单次预测超时"
                    value={config.OCR_PADDLE_VL_PREDICT_TIMEOUT_S}
                    onChange={(v) => updateField("OCR_PADDLE_VL_PREDICT_TIMEOUT_S", v)}
                    step="0.5"
                  />
                </div>

                {/* Backoff / Delay */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <NumberInputField
                    id="runtime-retry-backoff"
                    label="AI OCR 重试退避基数 (秒)"
                    hint="重试等待时间基数"
                    value={config.OCR_AI_RETRY_BACKOFF_BASE_S}
                    onChange={(v) => updateField("OCR_AI_RETRY_BACKOFF_BASE_S", v)}
                    step="0.5"
                  />
                  <NumberInputField
                    id="runtime-rate-limit-delay"
                    label="AI OCR 限流最小延迟 (秒)"
                    hint="收到限流后最小等待"
                    value={config.OCR_AI_RATE_LIMITED_MIN_DELAY_S}
                    onChange={(v) => updateField("OCR_AI_RATE_LIMITED_MIN_DELAY_S", v)}
                    step="0.5"
                  />
                </div>

                {/* Rendering DPI */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <NumberInputField
                    id="runtime-scanned-dpi"
                    label="PPTX 底图渲染 DPI"
                    hint="PPTX 背景图片质量"
                    value={config.SCANNED_RENDER_DPI}
                    onChange={(v) => updateField("SCANNED_RENDER_DPI", v)}
                  />
                </div>

                {/* Concurrency Caps */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <NumberInputField
                    id="runtime-page-concurrency-max"
                    label="AI OCR 最大页面并发"
                    hint="同时处理的页面数上限"
                    value={config.OCR_AI_PAGE_CONCURRENCY_MAX}
                    onChange={(v) => updateField("OCR_AI_PAGE_CONCURRENCY_MAX", v)}
                  />
                  <NumberInputField
                    id="runtime-block-concurrency-max"
                    label="AI OCR 最大块并发"
                    hint="同时处理的文字块数上限"
                    value={config.OCR_AI_BLOCK_CONCURRENCY_MAX}
                    onChange={(v) => updateField("OCR_AI_BLOCK_CONCURRENCY_MAX", v)}
                  />
                  <NumberInputField
                    id="runtime-rpm-max"
                    label="AI OCR 最大请求频率(RPM)"
                    hint="每分钟最大请求数"
                    value={config.OCR_AI_RPM_MAX}
                    onChange={(v) => updateField("OCR_AI_RPM_MAX", v)}
                  />
                  <NumberInputField
                    id="runtime-tpm-max"
                    label="AI OCR 最大 Token 频率(TPM)"
                    hint="每分钟最大 Token 数"
                    value={config.OCR_AI_TPM_MAX}
                    onChange={(v) => updateField("OCR_AI_TPM_MAX", v)}
                  />
                </div>

                {/* JWT Expiration */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <NumberInputField
                    id="runtime-jwt-expiration"
                    label="JWT 过期时间 (小时)"
                    hint="用户登录 Token 有效期"
                    value={config.JWT_EXPIRATION_HOURS}
                    onChange={(v) => updateField("JWT_EXPIRATION_HOURS", v)}
                  />
                </div>

                {/* Error Display */}
                {error ? (
                  <div className="rounded border border-destructive bg-destructive/10 px-3 py-2 text-xs text-destructive">
                    {error}
                  </div>
                ) : null}

                {/* Save Button */}
                <div className="flex justify-end">
                  <Button onClick={handleSave} disabled={saving || loading}>
                    {saving ? "保存中..." : "保存运行时配置"}
                  </Button>
                </div>
              </>
            )}
          </div>
        ) : null}
      </div>

      <div className="rounded border border-amber-500/40 bg-amber-50 px-4 py-3 text-xs text-amber-900">
        <div className="font-medium">管理员专用区域</div>
        <div className="mt-1">
          此区域的配置项会直接修改服务器端的环境变量，需要重启服务后生效。请谨慎操作。
        </div>
      </div>
    </div>
  )
}
