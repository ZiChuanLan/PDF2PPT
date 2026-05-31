"use client"

import * as React from "react"
import Link from "next/link"
import { CheckIcon, SettingsIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  getAllPresets,
  getDefaultPreset,
  applyPresetToSettings,
  type JobPreset,
  type Settings,
} from "@/lib/settings"

type PresetPickerProps = {
  currentSettings: Settings
  onApplyPreset: (settings: Settings) => void
  className?: string
}

export function PresetPicker({
  currentSettings,
  onApplyPreset,
  className,
}: PresetPickerProps) {
  const [allPresets, setAllPresets] = React.useState<JobPreset[]>([])
  const [defaultPreset, setDefaultPreset] = React.useState<JobPreset | null>(null)
  const [selectedPresetId, setSelectedPresetId] = React.useState<string | null>(null)

  React.useEffect(() => {
    const presets = getAllPresets()
    const defaultP = getDefaultPreset()
    setAllPresets(presets)
    setDefaultPreset(defaultP)
    setSelectedPresetId(defaultP?.id ?? null)
  }, [])

  const handleApplyPreset = React.useCallback(
    (preset: JobPreset) => {
      const newSettings = applyPresetToSettings(preset, currentSettings)
      onApplyPreset(newSettings)
      setSelectedPresetId(preset.id)
    },
    [currentSettings, onApplyPreset]
  )

  if (allPresets.length === 0) {
    return null
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="home-stat-label">快速预设</span>
        </div>
        <Link
          href="/presets"
          className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground"
        >
          <SettingsIcon className="size-3" />
          管理预设
        </Link>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {allPresets.map((preset) => {
          const isSelected = selectedPresetId === preset.id
          const isDefault = defaultPreset?.id === preset.id

          return (
            <button
              key={preset.id}
              type="button"
              onClick={() => handleApplyPreset(preset)}
              className={cn(
                "relative flex items-start gap-2.5 border p-3 text-left transition-all",
                isSelected
                  ? "border-foreground bg-muted/30"
                  : "border-border/60 hover:border-foreground/30 hover:bg-muted/20",
              )}
            >
              {/* Selection indicator */}
              {isSelected && (
                <span className="absolute right-1.5 top-1.5 flex size-3.5 items-center justify-center bg-foreground text-primary-foreground">
                  <CheckIcon className="size-2.5" />
                </span>
              )}
              {preset.icon && (
                <span className="mt-0.5 shrink-0 text-base leading-none" aria-hidden="true">
                  {preset.icon}
                </span>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className={cn(
                    "text-xs font-medium",
                    isSelected ? "text-foreground" : "text-muted-foreground",
                  )}>
                    {preset.name}
                  </span>
                  {isDefault && (
                    <span className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                      默认
                    </span>
                  )}
                </div>
                <span className="mt-0.5 block text-[10px] leading-snug text-muted-foreground">
                  {preset.description}
                </span>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
