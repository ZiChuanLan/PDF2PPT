"use client"

import * as React from "react"
import { createPortal } from "react-dom"
import { RefreshCwIcon, SettingsIcon, Loader2Icon, Trash2Icon } from "lucide-react"
import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { ModelProviderStatus, ModelStatusResponse } from "@/hooks/use-model-status"
import { LAYOUT_MODELS } from "@/lib/layout-models"
import { useModelDownload, type DownloadStatusItem } from "@/hooks/use-model-download"
import { DownloadProgressButton } from "@/components/download-progress-button"
import { apiFetch, normalizeFetchError } from "@/lib/api"
import type { OcrAiChainMode, OcrAiLayoutModel, OcrProvider } from "@/lib/settings"
import { toast } from "sonner"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ProviderKind = "local" | "remote"
export type ParseEngineMode = "local_ocr" | "remote_ocr" | "baidu_doc" | "mineru_cloud"

interface ProviderDisplay {
  key: string
  kind: ProviderKind
  label: string
}

// All provider definitions — determines display order and labels.
const PROVIDER_DISPLAY: ProviderDisplay[] = [
  { key: "tesseract", kind: "local", label: "Tesseract" },
  { key: "paddleocr", kind: "local", label: "PaddleOCR" },
  { key: "sam", kind: "local" as const, label: "SAM" },
  // Layout models are now shown as a group
  ...Object.values(LAYOUT_MODELS).map((m) => ({
    key: m.modelId,
    kind: "local" as ProviderKind,
    label: m.displayName,
  })),
  { key: "aiocr", kind: "remote", label: "AIOCR" },
  { key: "baidu_doc", kind: "remote", label: "百度文档解析" },
  { key: "mineru", kind: "remote", label: "MinerU" },
]

// Map parse engine mode → relevant provider keys.
const ENGINE_PROVIDER_MAP: Record<ParseEngineMode, string[]> = {
  local_ocr: ["tesseract", "paddleocr"],
  // For remote_ocr, show all layout models + aiocr
  remote_ocr: [...Object.keys(LAYOUT_MODELS), "aiocr"],
  baidu_doc: ["baidu_doc"],
  mineru_cloud: ["mineru"],
}

function normalizeLayoutModelKey(model?: OcrAiLayoutModel): string {
  return model && LAYOUT_MODELS[model] ? model : "pp_doclayout_v3"
}

function getProvidersForEngine(
  mode?: ParseEngineMode,
  ocrAiChainMode?: OcrAiChainMode,
  ocrAiLayoutModel?: OcrAiLayoutModel,
  ocrProvider?: OcrProvider,
  enableSam?: boolean,
): ProviderDisplay[] {
  if (!mode) return PROVIDER_DISPLAY
  let keys = ENGINE_PROVIDER_MAP[mode]
  const selectedLayoutModel = normalizeLayoutModelKey(ocrAiLayoutModel)
  if (mode === "local_ocr") {
    keys =
      ocrProvider === "tesseract"
        ? ["tesseract"]
        : ["paddleocr", selectedLayoutModel]
    if (enableSam && ocrProvider !== "tesseract") {
      keys = [...keys, "sam"]
    }
  } else if (mode === "remote_ocr") {
    keys =
      ocrAiChainMode === "direct"
        ? ["aiocr"]
        : [selectedLayoutModel, "aiocr"]
  }
  if (!keys) return PROVIDER_DISPLAY
  return PROVIDER_DISPLAY.filter((p) => keys.includes(p.key))
}

// Downloadable local models.
const DOWNLOADABLE_MODELS = new Set([
  ...Object.keys(LAYOUT_MODELS),
  "paddleocr",
  "sam",
])

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getProviderStatus(
  status: ModelStatusResponse | null,
  key: string,
  kind: ProviderKind
): ModelProviderStatus | null {
  if (!status) return null
  const bucket = kind === "local" ? status.local : status.remote
  return bucket[key] ?? null
}

function getOverallStatus(
  status: ModelStatusResponse | null,
  providers: ProviderDisplay[]
): "ready" | "partial" | "none" | "unknown" {
  if (!status) return "unknown"
  const all = providers.map((p) =>
    getProviderStatus(status, p.key, p.kind)
  ).filter(Boolean) as ModelProviderStatus[]
  if (all.length === 0) return "unknown"
  const readyCount = all.filter((s) => s.ready).length
  if (readyCount === all.length) return "ready"
  if (readyCount === 0) return "none"
  return "partial"
}

function getDotColor(
  provStatus: ModelProviderStatus | null
): string {
  if (!provStatus) return "bg-muted-foreground/40"
  if (provStatus.ready) return "bg-emerald-500"
  if (provStatus.configured === false) return "bg-amber-500"
  return "bg-red-500"
}

function getOverallDotColor(
  status: ModelStatusResponse | null,
  providers: ProviderDisplay[]
): string {
  const overall = getOverallStatus(status, providers)
  if (overall === "ready") return "bg-emerald-500"
  if (overall === "partial") return "bg-amber-500"
  if (overall === "none") return "bg-red-500"
  return "bg-muted-foreground/40"
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusDot({ colorClass }: { colorClass: string }) {
  return (
    <span
      className={cn(
        "inline-block size-2 rounded-full shrink-0",
        colorClass
      )}
    />
  )
}

function IssueTag({ issue }: { issue: string }) {
  const label = issue
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
  return (
    <span className="inline-block rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
      {label}
    </span>
  )
}

function ProviderRow({
  display,
  provStatus,
  onDownload,
  onCancel,
  downloadState,
  onStatusChange,
}: {
  display: ProviderDisplay
  provStatus: ModelProviderStatus | null
  onDownload: (model: string) => void
  onCancel: (model: string) => void
  downloadState: DownloadStatusItem | null
  onStatusChange?: () => void
}) {
  const isDownloadable = display.kind === "local" && DOWNLOADABLE_MODELS.has(display.key)
  const needsConfig = display.kind === "remote" && provStatus && !provStatus.configured
  const layoutModelInfo = LAYOUT_MODELS[display.key]
  const isDownloading = downloadState?.status === "downloading"
  const isDownloaded = provStatus?.ready && display.kind === "local"
  const [deleting, setDeleting] = React.useState(false)

  const handleDelete = React.useCallback(async () => {
    const label = display.label
    if (!window.confirm(`确认删除 ${label} 模型缓存？\n删除后可重新下载。`)) {
      return
    }
    setDeleting(true)
    try {
      const res = await apiFetch("/models/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: display.key }),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => null)
        throw new Error(
          (errData && (errData as { detail?: string }).detail) || `删除失败 (${res.status})`
        )
      }
      const data = await res.json()
      toast.success((data as { message?: string }).message || "已删除模型缓存")
      onStatusChange?.()
    } catch (e) {
      toast.error(normalizeFetchError(e, "删除模型失败"))
    } finally {
      setDeleting(false)
    }
  }, [display.key, display.label, onStatusChange])

  return (
    <div className="flex items-start justify-between gap-2 py-1.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <StatusDot colorClass={getDotColor(provStatus)} />
          <span className="font-mono text-[11px] text-foreground">
            {display.label}
          </span>
          {layoutModelInfo ? (
            <span className="text-[10px] text-muted-foreground">
              {layoutModelInfo.sizeMb} MB
            </span>
          ) : null}
          <Badge variant="outline" className="px-1 py-0 text-[9px]">
            {display.kind === "local" ? "本地" : "远程"}
          </Badge>
        </div>
        {layoutModelInfo && (
          <div className="mt-0.5 pl-3.5 text-[10px] text-muted-foreground">
            {layoutModelInfo.description}
          </div>
        )}
        {provStatus && provStatus.issues.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1 pl-3.5">
            {provStatus.issues.slice(0, 3).map((issue) => (
              <IssueTag key={issue} issue={issue} />
            ))}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {needsConfig && (
          <Link href="/settings">
            <Button variant="ghost" size="sm" className="h-6 px-1.5 text-[10px]">
              <SettingsIcon className="size-3" />
              配置
            </Button>
          </Link>
        )}
        {isDownloadable && provStatus && !provStatus.ready && !isDownloading && (
          <DownloadProgressButton
            modelId={display.key}
            downloadState={downloadState}
            isReady={provStatus.ready}
            onDownload={onDownload}
            onCancel={onCancel}
            onRefreshStatus={onStatusChange}
            variant="ghost"
            size="xs"
            className="h-6 px-1.5 text-[10px]"
          />
        )}
        {isDownloading && (
          <DownloadProgressButton
            modelId={display.key}
            downloadState={downloadState}
            isReady={provStatus?.ready ?? false}
            onDownload={onDownload}
            onCancel={onCancel}
            onRefreshStatus={onStatusChange}
            variant="ghost"
            size="xs"
            className="h-6 px-1.5 text-[10px]"
          />
        )}
        {isDownloaded && !isDownloading && isDownloadable && (
          <Button
            type="button"
            variant="ghost"
            size="xs"
            className="h-6 px-1.5 text-[10px] text-muted-foreground hover:text-destructive"
            disabled={deleting}
            onClick={handleDelete}
          >
            <Trash2Icon className="size-3" />
            {deleting ? "" : "删除"}
          </Button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Portal-based details panel
// ---------------------------------------------------------------------------

function DetailsPanel({
  status,
  providers,
  onDownload,
  onCancel,
  downloadStateMap,
  triggerRect,
  onClose,
  onStatusChange,
}: {
  status: ModelStatusResponse | null
  providers: ProviderDisplay[]
  onDownload: (model: string) => void
  onCancel: (model: string) => void
  downloadStateMap: Record<string, DownloadStatusItem>
  triggerRect: DOMRect
  onClose: () => void
  onStatusChange?: () => void
}) {
  const panelRef = React.useRef<HTMLDivElement>(null)

  // Close on click outside
  React.useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    // Delay to avoid the opening click from immediately closing the panel
    const id = setTimeout(() => {
      document.addEventListener("mousedown", handleClick)
    }, 0)
    return () => {
      clearTimeout(id)
      document.removeEventListener("mousedown", handleClick)
    }
  }, [onClose])

  // Close on Escape
  React.useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [onClose])

  // Position: below the trigger, left-aligned, clamped to viewport
  const style: React.CSSProperties = {
    position: "fixed",
    top: triggerRect.bottom + 4,
    left: Math.max(8, Math.min(triggerRect.left, window.innerWidth - 272)),
    zIndex: 9999,
  }

  // Separate layout models from other providers
  const layoutModelKeys = new Set(Object.keys(LAYOUT_MODELS))
  const nonLayoutLocal = providers.filter(
    (p) => p.kind === "local" && !layoutModelKeys.has(p.key)
  )
  const layoutModels = providers.filter(
    (p) => p.kind === "local" && layoutModelKeys.has(p.key)
  )
  const remoteProviders = providers.filter((p) => p.kind === "remote")

  return createPortal(
    <div
      ref={panelRef}
      className="w-72 rounded border border-border bg-background p-2.5 shadow-md"
      style={style}
    >
      {nonLayoutLocal.length > 0 && (
        <>
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            本地模型
          </div>
          {nonLayoutLocal.map((display) => (
            <ProviderRow
              key={display.key}
              display={display}
              provStatus={getProviderStatus(status, display.key, display.kind)}
              onDownload={onDownload}
              onCancel={onCancel}
              downloadState={downloadStateMap[display.key] ?? null}
              onStatusChange={onStatusChange}
            />
          ))}
        </>
      )}

      {layoutModels.length > 0 && (
        <>
          {nonLayoutLocal.length > 0 && <div className="my-1.5 border-t border-border" />}
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            版面分析模型
          </div>
          {layoutModels.map((display) => (
            <ProviderRow
              key={display.key}
              display={display}
              provStatus={getProviderStatus(status, display.key, display.kind)}
              onDownload={onDownload}
              onCancel={onCancel}
              downloadState={downloadStateMap[display.key] ?? null}
              onStatusChange={onStatusChange}
            />
          ))}
        </>
      )}

      {remoteProviders.length > 0 && (
        <>
          {(nonLayoutLocal.length > 0 || layoutModels.length > 0) && (
            <div className="my-1.5 border-t border-border" />
          )}
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            远程 API
          </div>
          {remoteProviders.map((display) => (
            <ProviderRow
              key={display.key}
              display={display}
              provStatus={getProviderStatus(status, display.key, display.kind)}
              onDownload={onDownload}
              onCancel={onCancel}
              downloadState={downloadStateMap[display.key] ?? null}
              onStatusChange={onStatusChange}
            />
          ))}
        </>
      )}

      <div className="mt-2 border-t border-border pt-1.5">
        <Link href="/settings">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-full justify-center text-[10px]"
          >
            <SettingsIcon className="size-3" />
            打开设置页
          </Button>
        </Link>
      </div>
    </div>,
    document.body
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface ModelStatusBadgeProps {
  /** Model status data from useModelStatus hook. */
  status: ModelStatusResponse | null
  /** Whether status is currently loading. */
  isLoading?: boolean
  /** Error message from last failed status fetch (shown when status is null and not loading). */
  error?: string | null
  /** Current parse engine mode — filters displayed providers. */
  parseEngineMode?: ParseEngineMode
  /** Current AI OCR chain mode — controls whether remote OCR needs layout models. */
  ocrAiChainMode?: OcrAiChainMode
  /** Current selected layout model — only this local layout dependency is required. */
  ocrAiLayoutModel?: OcrAiLayoutModel
  /** Current OCR provider — controls which local OCR dependency is required. */
  ocrProvider?: OcrProvider
  /** Whether SAM polygon refinement is enabled for local layout detection. */
  enableSam?: boolean
  /** Called after a successful download to refresh status. */
  onStatusChange?: () => void
  /** Additional CSS class. */
  className?: string
}

/**
 * Model status indicator with expandable details panel.
 *
 * Shows a colored dot (green/yellow/gray) that expands on click to reveal
 * per-provider readiness, issue details, and action buttons (configure/download).
 *
 * Uses a React Portal to render the expanded panel outside any overflow:hidden
 * ancestor containers.
 */
export function ModelStatusBadge({
  status,
  isLoading = false,
  error,
  parseEngineMode,
  ocrAiChainMode,
  ocrAiLayoutModel,
  ocrProvider,
  enableSam,
  onStatusChange,
  className,
}: ModelStatusBadgeProps) {
  const providers = React.useMemo(
    () => getProvidersForEngine(
      parseEngineMode,
      ocrAiChainMode,
      ocrAiLayoutModel,
      ocrProvider,
      enableSam,
    ),
    [parseEngineMode, ocrAiChainMode, ocrAiLayoutModel, ocrProvider, enableSam]
  )
  const [expanded, setExpanded] = React.useState(false)
  const [triggerRect, setTriggerRect] = React.useState<DOMRect | null>(null)
  const triggerRef = React.useRef<HTMLButtonElement>(null)
  const { startDownload, cancelDownload, downloads } = useModelDownload({
    onDownloadComplete: () => onStatusChange?.(),
  })

  const handleToggle = React.useCallback(() => {
    if (!expanded && triggerRef.current) {
      setTriggerRect(triggerRef.current.getBoundingClientRect())
    }
    setExpanded((v) => !v)
  }, [expanded])

  const handleClose = React.useCallback(() => {
    setExpanded(false)
  }, [])

  const handleDownload = React.useCallback(
    async (model: string) => {
      const modelInfo = LAYOUT_MODELS[model]
      const label = modelInfo?.displayName ?? model
      const sizeMb = modelInfo?.sizeMb
      const confirmMsg = sizeMb
        ? `下载 ${label}（${sizeMb}MB）？\n下载完成后可在设置中切换使用。`
        : `下载 ${label}？\n下载完成后可在设置中切换使用。`
      if (!window.confirm(confirmMsg)) {
        return
      }
      await startDownload(model)
    },
    [startDownload]
  )

  const overallColor = getOverallDotColor(status, providers)
  const overall = getOverallStatus(status, providers)
  const showError = !isLoading && status === null && !!error

  return (
    <span className={cn("relative inline-flex items-center gap-1", className)}>
      {/* Trigger — colored dot + label */}
      <button
        ref={triggerRef}
        type="button"
        disabled={showError}
        className={cn(
          "flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[11px] transition-colors",
          showError
            ? "text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
            : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
        )}
        onClick={handleToggle}
      >
        {isLoading ? (
          <Loader2Icon className="size-3 animate-spin" />
        ) : (
          <StatusDot colorClass={showError ? "bg-red-500" : overallColor} />
        )}
        <span className="font-mono uppercase tracking-widest">
          {showError
            ? "状态获取失败"
            : overall === "ready"
              ? "模型就绪"
              : overall === "partial"
                ? "部分就绪"
                : overall === "none"
                  ? "未就绪"
                  : "检查中"}
        </span>
      </button>

      {/* Retry button when status fetch failed */}
      {showError && (
        <button
          type="button"
          className="inline-flex items-center justify-center rounded p-1 text-red-600 transition-colors hover:bg-red-50 dark:hover:bg-red-950/30"
          onClick={onStatusChange}
          aria-label="重试获取状态"
        >
          <RefreshCwIcon className="size-3" />
        </button>
      )}

      {/* Expanded details — rendered via portal to bypass overflow:hidden ancestors */}
      {expanded && triggerRect && (
        <DetailsPanel
          status={status}
          providers={providers}
          onDownload={handleDownload}
          onCancel={cancelDownload}
          downloadStateMap={downloads}
          triggerRect={triggerRect}
          onClose={handleClose}
          onStatusChange={onStatusChange}
        />
      )}
    </span>
  )
}
