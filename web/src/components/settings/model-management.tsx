"use client"

import * as React from "react"
import { CheckIcon, Trash2Icon } from "lucide-react"
import { toast } from "sonner"

import { cn } from "@/lib/utils"
import { apiFetch } from "@/lib/api"
import { useModelDownload } from "@/hooks/use-model-download"
import { useModelStatus } from "@/hooks/use-model-status"
import { DownloadProgressButton } from "@/components/download-progress-button"
import { LAYOUT_MODELS } from "@/lib/layout-models"

export function ModelManagement() {
  const { data: modelStatus, refetch: refetchModelStatus } = useModelStatus()
  const { startDownload, cancelDownload, getDownloadState } = useModelDownload({
    onDownloadComplete: () => void refetchModelStatus(),
  })
  const [deleting, setDeleting] = React.useState<string | null>(null)

  const handleDelete = React.useCallback(
    async (modelId: string) => {
      const label =
        modelId === "paddleocr"
          ? "PaddleOCR"
          : modelId === "sam"
            ? "MobileSAM"
            : LAYOUT_MODELS[modelId]?.displayName ?? modelId
      if (!window.confirm(`确定删除 ${label} 的缓存文件？`)) return

      setDeleting(modelId)
      try {
        const res = await apiFetch("/models/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model: modelId }),
        })
        if (!res.ok) {
          const body = await res.json().catch(() => null)
          throw new Error(body?.message || "删除失败")
        }
        toast.success(`${label} 缓存已删除`)
        await refetchModelStatus()
      } catch (e) {
        toast.error(String(e))
      } finally {
        setDeleting(null)
      }
    },
    [refetchModelStatus]
  )

  const localStatus = modelStatus?.local

  return (
    <div className="space-y-4">
      {/* OCR Models */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">OCR Models</h4>
        <ModelRow
          modelId="paddleocr"
          label="PaddleOCR"
          description="百度开源 OCR 引擎，本地运行"
          isReady={localStatus?.paddleocr?.ready ?? false}
          downloadState={getDownloadState("paddleocr")}
          deleting={deleting === "paddleocr"}
          onDownload={() => startDownload("paddleocr")}
          onCancel={() => cancelDownload("paddleocr")}
          onDelete={() => handleDelete("paddleocr")}
          onRefreshStatus={() => void refetchModelStatus()}
        />
      </div>

      {/* Layout Analysis Models */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Layout Analysis Models</h4>
        {Object.values(LAYOUT_MODELS).map((model) => (
          <ModelRow
            key={model.modelId}
            modelId={model.modelId}
            label={model.displayName}
            description={`${model.description} · ${model.speedLabel} · ${model.accuracy}`}
            sizeMb={model.sizeMb}
            recommended={model.recommended}
            isReady={localStatus?.[model.modelId]?.ready ?? false}
            downloadState={getDownloadState(model.modelId)}
            deleting={deleting === model.modelId}
            onDownload={() => startDownload(model.modelId)}
            onCancel={() => cancelDownload(model.modelId)}
            onDelete={() => handleDelete(model.modelId)}
            onRefreshStatus={() => void refetchModelStatus()}
          />
        ))}
      </div>

      {/* SAM Models */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">SAM Models</h4>
        <ModelRow
          modelId="sam"
          label="MobileSAM"
          description="多边形细化 (35MB)"
          isReady={localStatus?.sam?.ready ?? false}
          downloadState={getDownloadState("sam")}
          deleting={deleting === "sam"}
          onDownload={() => startDownload("sam")}
          onCancel={() => cancelDownload("sam")}
          onDelete={() => handleDelete("sam")}
          onRefreshStatus={() => void refetchModelStatus()}
        />
      </div>
    </div>
  )
}

function ModelRow({
  modelId,
  label,
  description,
  sizeMb,
  recommended,
  isReady,
  downloadState,
  deleting,
  onDownload,
  onCancel,
  onDelete,
  onRefreshStatus,
}: {
  modelId: string
  label: string
  description: string
  sizeMb?: number
  recommended?: boolean
  isReady: boolean
  downloadState: ReturnType<ReturnType<typeof useModelDownload>["getDownloadState"]>
  deleting: boolean
  onDownload: () => void
  onCancel: () => void
  onDelete: () => void
  onRefreshStatus: () => void
}) {
  return (
    <div className="flex items-center justify-between rounded border border-border px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-block size-2 rounded-full",
              isReady ? "bg-emerald-500" : "bg-muted-foreground/40"
            )}
          />
          <span className="text-sm font-medium">{label}</span>
          {sizeMb != null && (
            <span className="text-[11px] text-muted-foreground">{sizeMb} MB</span>
          )}
          {recommended && (
            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
              推荐
            </span>
          )}
        </div>
        <div className="mt-0.5 pl-4 text-[11px] text-muted-foreground">{description}</div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {isReady ? (
          <>
            <span className="flex items-center gap-1 text-xs text-emerald-600">
              <CheckIcon className="size-3" />
              已下载
            </span>
            <button
              type="button"
              onClick={onDelete}
              disabled={deleting}
              className="ml-1 rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors disabled:opacity-50"
              title="删除缓存"
            >
              <Trash2Icon className="size-3.5" />
            </button>
          </>
        ) : (
          <DownloadProgressButton
            modelId={modelId}
            downloadState={downloadState}
            isReady={isReady}
            onDownload={onDownload}
            onCancel={onCancel}
            onRefreshStatus={onRefreshStatus}
          />
        )}
      </div>
    </div>
  )
}
