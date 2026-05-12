"use client"

import * as React from "react"
import Link from "next/link"
import { CheckIcon, SettingsIcon, SparklesIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
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
        <div className="flex items-center gap-2">
          <SparklesIcon className="size-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">快速预设</h3>
        </div>
        <Link
          href="/presets"
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <SettingsIcon className="size-3" />
          管理预设
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {allPresets.map((preset) => {
          const isSelected = selectedPresetId === preset.id
          const isDefault = defaultPreset?.id === preset.id

          return (
            <Card
              key={preset.id}
              className={cn(
                "relative cursor-pointer transition-all hover:border-foreground/50",
                isSelected && "border-foreground bg-muted/30"
              )}
              onClick={() => handleApplyPreset(preset)}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {preset.icon && (
                      <span className="text-lg leading-none" aria-hidden="true">
                        {preset.icon}
                      </span>
                    )}
                    <CardTitle className="text-base">{preset.name}</CardTitle>
                  </div>
                  {isSelected && (
                    <CheckIcon className="size-4 shrink-0 text-foreground" aria-label="已选择" />
                  )}
                </div>
                {isDefault && (
                  <Badge variant="outline" className="w-fit text-[10px]">
                    默认
                  </Badge>
                )}
              </CardHeader>
              <CardContent className="pb-4">
                <CardDescription className="text-xs leading-relaxed">
                  {preset.description}
                </CardDescription>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>点击预设卡片即可应用配置</span>
      </div>
    </div>
  )
}
