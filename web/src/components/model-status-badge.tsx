"use client"

import * as React from "react"
import { SettingsIcon, DownloadIcon, Loader2Icon } from "lucide-react"
import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { apiFetch, normalizeFetchError } from "@/lib/api"
import { toast } from "sonner"
import type { ModelProviderStatus, ModelStatusResponse } from "@/hooks/use-model-status"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ProviderKind = "local" | "remote"

interface ProviderDisplay {
  key: string
  kind: ProviderKind
  label: string
}

// Provider definitions — determines display order and labels.
const PROVIDER_DISPLAY: ProviderDisplay[] = [
  { key: "tesseract", kind: "local", label: "Tesseract" },
  { key: "paddleocr", kind: "local", label: "PaddleOCR" },
  { key: "pp_doclayout", kind: "local", label: "PP-DocLayout" },
  { key: "aiocr", kind: "remote", label: "AIOCR" },
  { key: "baidu_doc", kind: "remote", label: "百度文档解析" },
  { key: "mineru", kind: "remote", label: "MinerU" },
]

// Downloadable local models.
const DOWNLOADABLE_MODELS: Record<string, string> = {
  pp_doclayout: "pp_doclayout",
  paddleocr: "paddleocr",
}

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
  status: ModelStatusResponse | null
): "ready" | "partial" | "unknown" {
  if (!status) return "unknown"
  const all = PROVIDER_DISPLAY.map((p) =>
    getProviderStatus(status, p.key, p.kind)
  ).filter(Boolean) as ModelProviderStatus[]
  if (all.length === 0) return "unknown"
  const readyCount = all.filter((s) => s.ready).length
  if (readyCount === all.length) return "ready"
  if (readyCount === 0) return "partial"
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
  status: ModelStatusResponse | null
): string {
  const overall = getOverallStatus(status)
  if (overall === "ready") return "bg-emerald-500"
  if (overall === "partial") return "bg-amber-500"
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
  downloading,
}: {
  display: ProviderDisplay
  provStatus: ModelProviderStatus | null
  onDownload: (model: string) => void
  downloading: boolean
}) {
  const isDownloadable = display.kind === "local" && DOWNLOADABLE_MODELS[display.key]
  const needsConfig = display.kind === "remote" && provStatus && !provStatus.configured

  return (
    <div className="flex items-start justify-between gap-2 py-1.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <StatusDot colorClass={getDotColor(provStatus)} />
          <span className="font-mono text-[11px] text-foreground">
            {display.label}
          </span>
          <Badge variant="outline" className="px-1 py-0 text-[9px]">
            {display.kind === "local" ? "本地" : "远程"}
          </Badge>
        </div>
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
        {isDownloadable && provStatus && !provStatus.ready && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-1.5 text-[10px]"
            onClick={() => onDownload(display.key)}
            disabled={downloading}
          >
            {downloading ? (
              <Loader2Icon className="size-3 animate-spin" />
            ) : (
              <DownloadIcon className="size-3" />
            )}
            下载
          </Button>
        )}
      </div>
    </div>
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
 */
export function ModelStatusBadge({
  status,
  isLoading = false,
  onStatusChange,
  className,
}: ModelStatusBadgeProps) {
  const [expanded, setExpanded] = React.useState(false)
  const [downloading, setDownloading] = React.useState<string | null>(null)

  const handleDownload = React.useCallback(
    async (model: string) => {
      setDownloading(model)
      try {
        const res = await apiFetch("/models/download", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model }),
        })
        if (!res.ok) {
          const body = await res.json().catch(() => null)
          throw new Error(body?.message || "下载失败")
        }
        toast.success("模型下载完成")
        onStatusChange?.()
      } catch (e) {
        toast.error(normalizeFetchError(e, "模型下载失败"))
      } finally {
        setDownloading(null)
      }
    },
    [onStatusChange]
  )

  const overallColor = getOverallDotColor(status)
  const overall = getOverallStatus(status)

  return (
    <div className={cn("inline-flex flex-col items-start", className)}>
      {/* Trigger — colored dot + label */}
      <button
        type="button"
        className="flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
        onClick={() => setExpanded((v) => !v)}
      >
        {isLoading ? (
          <Loader2Icon className="size-3 animate-spin" />
        ) : (
          <StatusDot colorClass={overallColor} />
        )}
        <span className="font-mono uppercase tracking-widest">
          {overall === "ready" ? "模型就绪" : overall === "partial" ? "部分就绪" : "检查中"}
        </span>
      </button>

      {/* Expanded details panel */}
      {expanded && (
        <div className="mt-1 w-64 rounded border border-border bg-background p-2.5 shadow-md">
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            本地模型
          </div>
          {PROVIDER_DISPLAY.filter((p) => p.kind === "local").map((display) => (
            <ProviderRow
              key={display.key}
              display={display}
              provStatus={getProviderStatus(status, display.key, display.kind)}
              onDownload={handleDownload}
              downloading={downloading === display.key}
            />
          ))}

          <div className="my-1.5 border-t border-border" />

          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            远程 API
          </div>
          {PROVIDER_DISPLAY.filter((p) => p.kind === "remote").map((display) => (
            <ProviderRow
              key={display.key}
              display={display}
              provStatus={getProviderStatus(status, display.key, display.kind)}
              onDownload={handleDownload}
              downloading={downloading === display.key}
            />
          ))}

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
        </div>
      )}
    </div>
  )
}
