"use client"

import * as React from "react"
import Link from "next/link"
import { ArrowRightIcon, UploadCloudIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { useAuth } from "@/components/auth-provider"
import {
  type Settings,
} from "@/lib/settings"
import { SegmentedControl } from "@/components/ui/segmented-control"
import {
  getAllPresets,
  getDefaultPreset,
  applyPresetToSettings,
  type JobPreset,
} from "@/lib/settings"
import {
  HOME_PARSE_MODE_OPTIONS,
  applyHomeParseMode,
  resolveHomeParseMode,
  type HomeParseMode,
} from "@/lib/run-config"

interface UploadStageProps {
  getRootProps: () => React.HTMLAttributes<HTMLElement>
  getInputProps: () => React.InputHTMLAttributes<HTMLInputElement>
  isDragActive: boolean
  isDragReject: boolean
  settingsSnapshot: Settings
  updateSettingsSnapshot: (updater: (prev: Settings) => Settings) => void
}

const PPT_MODE_OPTIONS = [
  { id: "turbo", label: "极速" },
  { id: "fast", label: "快速" },
  { id: "standard", label: "精准" },
]

export function UploadStage({
  getRootProps,
  getInputProps,
  isDragActive,
  isDragReject,
  settingsSnapshot,
  updateSettingsSnapshot,
}: UploadStageProps) {
  const { user, isLoading: isAuthLoading } = useAuth()

  const activeParseMode = React.useMemo(
    () => resolveHomeParseMode(settingsSnapshot),
    [settingsSnapshot],
  )

  const handleParsingChange = React.useCallback(
    (mode: HomeParseMode) => {
      if (mode === activeParseMode) return
      updateSettingsSnapshot((prev) => applyHomeParseMode(prev, mode))
    },
    [activeParseMode, updateSettingsSnapshot],
  )

  // Preset state
  const [allPresets, setAllPresets] = React.useState<JobPreset[]>([])
  const [selectedPresetId, setSelectedPresetId] = React.useState<string | null>(null)

  React.useEffect(() => {
    const presets = getAllPresets()
    const defaultP = getDefaultPreset()
    setAllPresets(presets)
    setSelectedPresetId(defaultP?.id ?? null)
  }, [])

  const handleApplyPreset = React.useCallback(
    (preset: JobPreset) => {
      const newSettings = applyPresetToSettings(preset, settingsSnapshot)
      updateSettingsSnapshot(() => newSettings)
      setSelectedPresetId(preset.id)
    },
    [settingsSnapshot, updateSettingsSnapshot],
  )

  return (
    <div>
      {/* Hero */}
      <div className="mx-auto max-w-2xl py-8 text-center md:py-12">
        <h1 className="font-serif text-3xl font-semibold tracking-tight md:text-4xl">
          PDF2PPT
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          上传 PDF 或图片，自动生成演示文稿
        </p>
      </div>

      {/* Unified glass panel */}
      <div className="mx-auto max-w-2xl">
        <div className="home-inline-panel">
          {/* Dropzone */}
          <div
            {...getRootProps()}
            role="region"
            aria-label="上传文件区域"
            className={cn(
              "group flex cursor-pointer flex-col items-center justify-center px-8 py-14 text-center transition-all",
              isDragActive && !isDragReject && "!bg-destructive/5",
              isDragReject && "!bg-destructive/10",
              (!user && !isAuthLoading) && "pointer-events-none opacity-60",
            )}
          >
            <input {...getInputProps()} />
            <div className="mb-4 flex size-16 items-center justify-center bg-destructive/10 transition-transform group-hover:scale-110">
              <UploadCloudIcon className="size-8 text-destructive" />
            </div>
            <p className="text-base font-medium">
              {isDragActive ? "松开以上传文件" : "拖拽文件到这里"}
            </p>
            <p className="mt-1.5 text-xs text-muted-foreground">
              支持同时上传多个文件 · PDF / PNG / JPG / WebP
            </p>
            {!user && !isAuthLoading ? (
              <p className="mt-3 text-xs text-destructive">请先登录后再上传文件</p>
            ) : null}
          </div>

          {/* Divider */}
          <div className="border-t border-border/30" />

          {/* Presets — compact row */}
          {allPresets.length > 0 && (
            <>
              <div className="px-5 py-3">
                <div className="flex items-center gap-3">
                  <span className="home-stat-label shrink-0">预设</span>
                  <div className="flex flex-1 gap-2">
                    {allPresets.map((preset) => {
                      const isActive = selectedPresetId === preset.id
                      return (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => handleApplyPreset(preset)}
                          className={cn(
                            "relative flex flex-1 items-center justify-center gap-1.5 border px-3 py-2 text-[11px] font-medium transition-all",
                            isActive
                              ? "border-foreground bg-foreground text-primary-foreground"
                              : "border-border/60 text-muted-foreground hover:border-foreground/40 hover:text-foreground",
                          )}
                        >
                          {preset.icon && (
                            <span className="text-xs leading-none" aria-hidden="true">
                              {preset.icon}
                            </span>
                          )}
                          {preset.name}
                        </button>
                      )
                    })}
                  </div>
                </div>
              </div>
              <div className="border-t border-border/30" />
            </>
          )}

          {/* Config — segmented controls */}
          <div className="grid gap-4 px-5 py-4">
            {/* PPT Mode */}
            <div className="grid gap-1.5">
              <span className="home-stat-label">PPT 模式</span>
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

            {/* Parsing Mode */}
            <div className="grid gap-1.5">
              <span className="home-stat-label">解析模式</span>
              <SegmentedControl
                options={HOME_PARSE_MODE_OPTIONS}
                value={activeParseMode}
                onChange={handleParsingChange}
              />
            </div>

            {/* MinerU token hint */}
            {activeParseMode === "mineru_cloud" && !settingsSnapshot.mineruApiToken && (
              <div className="flex items-center gap-1.5 text-[11px] text-amber-600">
                <span>云端 MinerU 需要配置 Token</span>
                <Link href="/settings" className="underline font-medium">去设置</Link>
              </div>
            )}
          </div>

          {/* Divider */}
          <div className="border-t border-border/30" />

          {/* Bottom link */}
          <Link
            href="/settings"
            className="group/link flex items-center justify-between px-5 py-3 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <span className="home-stat-label">高级设置</span>
            <ArrowRightIcon className="size-3 transition-transform group-hover/link:translate-x-0.5" />
          </Link>
        </div>
      </div>
    </div>
  )
}
