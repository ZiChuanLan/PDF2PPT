"use client"

import type * as React from "react"
import Link from "next/link"
import { UploadCloudIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { useAuth } from "@/components/auth-provider"
import {
  AIOCR_CHAIN_MODE_LABELS,
  PARSE_ENGINE_MODE_LABELS,
  PPT_GENERATION_MODE_LABELS,
  type ParseEngineMode,
  type Settings,
} from "@/lib/settings"
import { Select } from "@/components/ui/select"
import { PresetPicker } from "@/components/preset-picker"

interface UploadStageProps {
  getRootProps: () => React.HTMLAttributes<HTMLElement>
  getInputProps: () => React.InputHTMLAttributes<HTMLInputElement>
  isDragActive: boolean
  isDragReject: boolean
  settingsSnapshot: Settings
  updateSettingsSnapshot: (updater: (prev: Settings) => Settings) => void
}

export function UploadStage({
  getRootProps,
  getInputProps,
  isDragActive,
  isDragReject,
  settingsSnapshot,
  updateSettingsSnapshot,
}: UploadStageProps) {
  const { user, isLoading: isAuthLoading } = useAuth()

  return (
    <div>
      {/* Hero section */}
      <div className="relative mx-auto max-w-3xl py-8 md:py-14">
        {/* Subtle gradient backdrop */}
        <div className="pointer-events-none absolute inset-0 -z-10 rounded-2xl bg-gradient-to-b from-destructive/[0.03] to-transparent" />

        <div className="mb-6 text-center">
          <h1 className="font-serif text-3xl font-semibold tracking-tight md:text-4xl">
            PDF2PPT
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            上传 PDF 或图片，自动生成演示文稿
          </p>
        </div>

        <div
          {...getRootProps()}
          role="region"
          aria-label="上传文件区域"
          className={cn(
            "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition-all",
            "min-h-[240px]",
            isDragActive && !isDragReject && "border-destructive bg-destructive/5 scale-[1.01]",
            isDragReject && "border-destructive bg-destructive/10",
            !isDragActive && !isDragReject && "border-border hover:border-destructive/50 hover:bg-muted/30",
            (!user && !isAuthLoading) && "pointer-events-none opacity-60"
          )}
        >
          <input {...getInputProps()} />
          <div className="mb-4 flex size-14 items-center justify-center rounded-full bg-destructive/10 transition-transform group-hover:scale-110">
            <UploadCloudIcon className="size-7 text-destructive" />
          </div>
          <p className="text-lg font-medium">
            {isDragActive ? "松开以上传文件" : "拖拽文件到这里"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            支持同时上传多个文件 · PDF / PNG / JPG / WebP
          </p>
          {!user && !isAuthLoading ? (
            <p className="mt-3 text-xs text-destructive">请先登录后再上传文件</p>
          ) : null}
        </div>

        {/* Preset Picker */}
        <div className="mx-auto mt-8 max-w-3xl">
          <PresetPicker
            currentSettings={settingsSnapshot}
            onApplyPreset={(newSettings) => {
              updateSettingsSnapshot(() => newSettings)
            }}
          />
        </div>

        {/* Config selects below upload */}
        <div className="mx-auto mt-6 flex max-w-3xl flex-wrap items-center justify-center gap-x-4 gap-y-2 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">解析引擎</span>
            <Select
              value={settingsSnapshot.parseEngineMode}
              onChange={(e) => {
                const mode = e.target.value as ParseEngineMode
                updateSettingsSnapshot((prev) => ({
                  ...prev,
                  parseEngineMode: mode,
                  ocrProvider:
                    mode === "remote_ocr" ? "aiocr"
                    : mode === "baidu_doc" ? "baidu"
                    : mode === "mineru_cloud" ? "auto"
                    : "machine",
                }))
              }}
              className="h-7 w-28 py-1 text-xs"
              options={Object.entries(PARSE_ENGINE_MODE_LABELS).map(([value, label]) => ({
                id: value,
                label,
              }))}
            />
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">生成模式</span>
            <Select
              value={settingsSnapshot.pptGenerationMode}
              onChange={(e) =>
                updateSettingsSnapshot((prev) => ({
                  ...prev,
                  pptGenerationMode: e.target.value as Settings["pptGenerationMode"],
                }))
              }
              className="h-7 w-28 py-1 text-xs"
              options={[
                { id: "turbo", label: PPT_GENERATION_MODE_LABELS.turbo },
                { id: "fast", label: PPT_GENERATION_MODE_LABELS.fast },
                { id: "standard", label: PPT_GENERATION_MODE_LABELS.standard },
              ]}
            />
          </div>
          <Link
            href="/settings"
            className="text-muted-foreground hover:text-foreground"
          >
            高级设置
          </Link>
        </div>

        {/* MinerU token hint */}
        {settingsSnapshot.parseEngineMode === "mineru_cloud" && !settingsSnapshot.mineruApiToken && (
          <div className="mx-auto mt-2 max-w-3xl text-center text-xs text-amber-600">
            云端 MinerU 需要配置 Token，请前往
            <Link href="/settings" className="ml-1 text-destructive hover:underline">设置页面</Link>
            填写
          </div>
        )}

        {/* Config summary */}
        <div className="mx-auto mt-6 flex max-w-md items-center justify-center gap-2 text-xs text-muted-foreground">
          <span>{PARSE_ENGINE_MODE_LABELS[settingsSnapshot.parseEngineMode]}</span>
          {settingsSnapshot.parseEngineMode === "local_ocr" && (
            <>
              <span className="text-border">·</span>
              <span>{settingsSnapshot.ocrProvider === "paddleocr" ? "PaddleOCR" : "Tesseract"}</span>
            </>
          )}
          {settingsSnapshot.parseEngineMode === "remote_ocr" && (
            <>
              <span className="text-border">·</span>
              <span>{AIOCR_CHAIN_MODE_LABELS[settingsSnapshot.ocrAiChainMode]}</span>
            </>
          )}
          <span className="text-border">·</span>
          <span>{PPT_GENERATION_MODE_LABELS[settingsSnapshot.pptGenerationMode]}</span>
        </div>
      </div>
    </div>
  )
}
