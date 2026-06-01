"use client"

import * as React from "react"
import Link from "next/link"
import {
  AlertCircleIcon,
  ArrowRightIcon,
  InfoIcon,
} from "lucide-react"

import { HoverHint } from "@/components/ui/hover-hint"
import { SegmentedControl } from "@/components/ui/segmented-control"
import { Toggle } from "@/components/ui/toggle"
import { Callout } from "@/components/ui/callout"
import { ModelStatusBadge } from "@/components/model-status-badge"
import {
  type Settings,
} from "@/lib/settings"
import type { ModelStatusResponse } from "@/hooks/use-model-status"
import { cn } from "@/lib/utils"
import {
  HOME_PARSE_MODE_DESCRIPTIONS,
  HOME_PARSE_MODE_OPTIONS,
  applyHomeParseMode,
  resolveHomeParseMode,
  type HomeParseMode,
} from "@/lib/run-config"

type QuickConfigPanelProps = {
  settingsSnapshot: Settings
  updateSettingsSnapshot: (updater: (prev: Settings) => Settings) => void
  modelStatus: ModelStatusResponse | null
  modelStatusError: string | null
  isModelStatusLoading: boolean
  refetchModelStatus: () => void
  retainProcessArtifacts: boolean
  setRetainProcessArtifacts: (value: boolean) => void
}

const PPT_MODE_OPTIONS = [
  { id: "turbo", label: "极速" },
  { id: "fast", label: "快速" },
  { id: "standard", label: "精准" },
]

function hasAiOcrConfig(settings: Settings): boolean {
  return Boolean(settings.ocrAiApiKey.trim() && settings.ocrAiModel.trim())
}

function hasBaiduDocConfig(settings: Settings): boolean {
  return Boolean(settings.ocrBaiduApiKey.trim() && settings.ocrBaiduSecretKey.trim())
}

function ParseModeGrid({
  value,
  onChange,
}: {
  value: HomeParseMode
  onChange: (mode: HomeParseMode) => void
}) {
  return (
    <div className="grid grid-cols-4 gap-1">
      {HOME_PARSE_MODE_OPTIONS.map((option) => {
        const active = option.id === value
        return (
          <button
            key={option.id}
            type="button"
            title={HOME_PARSE_MODE_DESCRIPTIONS[option.id]}
            aria-pressed={active}
            onClick={() => onChange(option.id)}
            className={cn(
              "h-8 min-w-0 border border-border/60 px-1 text-[11px] font-medium leading-none transition-colors",
              "whitespace-nowrap hover:border-foreground/40 hover:text-foreground",
              active
                ? "border-foreground bg-foreground text-primary-foreground"
                : "bg-muted/20 text-muted-foreground",
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export function QuickConfigPanel({
  settingsSnapshot,
  updateSettingsSnapshot,
  modelStatus,
  modelStatusError,
  isModelStatusLoading,
  refetchModelStatus,
  retainProcessArtifacts,
  setRetainProcessArtifacts,
}: QuickConfigPanelProps) {
  const activeParseMode = React.useMemo(
    () => resolveHomeParseMode(settingsSnapshot),
    [settingsSnapshot],
  )

  const handleParseModeChange = React.useCallback(
    (mode: HomeParseMode) => {
      if (mode === activeParseMode) return
      updateSettingsSnapshot((prev) => applyHomeParseMode(prev, mode))
    },
    [activeParseMode, updateSettingsSnapshot],
  )

  const selectedLayoutModel = settingsSnapshot.ocrAiLayoutModel || "pp_doclayout_v3"
  const selectedLayoutReady = modelStatus?.local?.[selectedLayoutModel]?.ready ?? false
  const selectedLocalOcrKey =
    settingsSnapshot.ocrProvider === "tesseract" ? "tesseract" : "paddleocr"
  const selectedLocalOcrReady = modelStatus?.local?.[selectedLocalOcrKey]?.ready ?? false
  const isAiBlockRecognition =
    settingsSnapshot.parseEngineMode === "remote_ocr" &&
    settingsSnapshot.ocrAiChainMode === "layout_block"

  const showAiConfigWarning =
    (activeParseMode === "ai_direct" || isAiBlockRecognition) &&
    !hasAiOcrConfig(settingsSnapshot)
  const showBaiduWarning =
    activeParseMode === "baidu_doc" && !hasBaiduDocConfig(settingsSnapshot)
  const showMineruWarning =
    activeParseMode === "mineru_cloud" && !settingsSnapshot.mineruApiToken.trim()
  const showLocalModelWarning =
    activeParseMode === "local_chunk" &&
    !isAiBlockRecognition &&
    modelStatus !== null &&
    (!selectedLocalOcrReady || !selectedLayoutReady)
  const showAiChunkModelWarning =
    isAiBlockRecognition &&
    modelStatus !== null &&
    !selectedLayoutReady

  return (
    <div className="home-inline-panel px-4 py-3">
      <div className="grid gap-3">
        <div className="grid gap-1.5">
          <div className="flex items-center gap-1.5">
            <span className="home-stat-label">PPT 模式</span>
            <HoverHint text="极速优先抢时间；快速适合日常转换；精准适合效果优先。" />
          </div>
          <SegmentedControl
            options={PPT_MODE_OPTIONS}
            value={settingsSnapshot.pptGenerationMode}
            onChange={(v) =>
              updateSettingsSnapshot((prev) => ({
                ...prev,
                pptGenerationMode: v as Settings["pptGenerationMode"],
              }))
            }
          />
        </div>

        <div className="grid gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <span className="home-stat-label">解析模式</span>
              <HoverHint text="这里只保留运行前最常用的模式切换；模型、密钥、SAM 和并发等细项在设置页调整。" />
            </div>
            <ModelStatusBadge
              status={modelStatus}
              isLoading={isModelStatusLoading}
              error={modelStatusError}
              parseEngineMode={settingsSnapshot.parseEngineMode}
              ocrAiChainMode={settingsSnapshot.ocrAiChainMode}
              ocrAiLayoutModel={settingsSnapshot.ocrAiLayoutModel}
              ocrProvider={settingsSnapshot.ocrProvider}
              enableSam={settingsSnapshot.enableSam}
              onStatusChange={() => void refetchModelStatus()}
            />
          </div>
          <ParseModeGrid
            value={activeParseMode}
            onChange={handleParseModeChange}
          />
          <p className="text-xs leading-snug text-muted-foreground">
            {HOME_PARSE_MODE_DESCRIPTIONS[activeParseMode]}
          </p>
        </div>

        {showAiConfigWarning && (
          <Callout variant="warning" icon={<AlertCircleIcon />}>
            AI OCR 需要在设置页填写 API Key 并选择模型
            <Link href="/settings" className="ml-1 font-medium underline">
              去设置
            </Link>
          </Callout>
        )}

        {showAiChunkModelWarning && (
          <Callout variant="warning" icon={<AlertCircleIcon />}>
            本地切块 + AI 识别需要可用的本地版面模型，模型下载和识别引擎在设置页管理
            <Link href="/settings" className="ml-1 font-medium underline">
              去设置
            </Link>
          </Callout>
        )}

        {showLocalModelWarning && (
          <Callout variant="warning" icon={<AlertCircleIcon />}>
            本地切块需要本地 OCR 和版面模型就绪，下载与切换在设置页完成
            <Link href="/settings" className="ml-1 font-medium underline">
              去设置
            </Link>
          </Callout>
        )}

        {showBaiduWarning && (
          <Callout variant="warning" icon={<AlertCircleIcon />}>
            百度解析需要补全百度 API Key 和 Secret Key
            <Link href="/settings" className="ml-1 font-medium underline">
              去设置
            </Link>
          </Callout>
        )}

        {showMineruWarning && (
          <Callout variant="warning" icon={<AlertCircleIcon />}>
            MinerU 解析需要配置 API Token
            <Link href="/settings" className="ml-1 font-medium underline">
              去设置
            </Link>
          </Callout>
        )}

        {activeParseMode === "ai_direct" && (
          <Callout variant="info" icon={<InfoIcon />}>
            AI 直出会整页识别，不使用本地版面切块和 SAM。
          </Callout>
        )}

        <div className="border-t border-border/30" />

        <Toggle
          checked={retainProcessArtifacts}
          onChange={setRetainProcessArtifacts}
          label="保留过程图"
          hint="保留每页处理过程图，便于核对中间效果或排查问题。"
        />

        <Link
          href="/settings"
          className="group flex items-center justify-between pt-0.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <span className="home-stat-label">高级设置</span>
          <ArrowRightIcon className="size-3 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
    </div>
  )
}
