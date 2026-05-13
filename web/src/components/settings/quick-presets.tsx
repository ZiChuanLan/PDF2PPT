"use client"

import * as React from "react"
import { FileTextIcon, ScanIcon, SparklesIcon } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

import type { Settings } from "@/lib/settings"

type PresetConfig = {
  id: string
  icon: React.ReactNode
  label: string
  description: string
  config: Partial<Settings>
}

const PRESETS: PresetConfig[] = [
  {
    id: "normal",
    icon: <FileTextIcon className="h-5 w-5" />,
    label: "普通文档",
    description: "适合原生PDF，快速提取文字",
    config: {
      parseEngineMode: "local_ocr",
      ocrProvider: "machine",
    },
  },
  {
    id: "scanned",
    icon: <ScanIcon className="h-5 w-5" />,
    label: "扫描件",
    description: "图片或扫描PDF，使用OCR识别",
    config: {
      parseEngineMode: "local_ocr",
      ocrProvider: "paddleocr",
    },
  },
  {
    id: "high_quality",
    icon: <SparklesIcon className="h-5 w-5" />,
    label: "高精度",
    description: "云端AI识别，精度最高",
    config: {
      parseEngineMode: "remote_ocr",
      ocrAiChainMode: "layout_block",
    },
  },
]

type QuickPresetsProps = {
  onApplyPreset: (config: Partial<Settings>) => void
  /** Render as compact horizontal button group (no card, no collapse) */
  compact?: boolean
}

export function QuickPresets({ onApplyPreset, compact = false }: QuickPresetsProps) {
  const [isCollapsed, setIsCollapsed] = React.useState(false)

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-xs font-medium text-muted-foreground">
          快速配置:
        </span>
        <div className="flex gap-1.5">
          {PRESETS.map((preset) => (
            <Button
              key={preset.id}
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2.5 text-xs"
              onClick={() => onApplyPreset(preset.config)}
            >
              {React.isValidElement(preset.icon)
                ? React.cloneElement(
                    preset.icon as React.ReactElement<{ className?: string }>,
                    { className: "h-3.5 w-3.5" }
                  )
                : preset.icon}
              {preset.label}
            </Button>
          ))}
        </div>
      </div>
    )
  }

  if (isCollapsed) {
    return (
      <div className="flex items-center justify-between rounded-lg border bg-muted/50 px-4 py-2">
        <span className="text-sm text-muted-foreground">快速配置</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsCollapsed(false)}
          className="h-7 text-xs"
        >
          展开
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">快速配置</h3>
          <p className="text-xs text-muted-foreground">选择预设快速开始，或在下方自定义配置</p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsCollapsed(true)}
          className="h-7 text-xs"
        >
          收起
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {PRESETS.map((preset) => (
          <Card
            key={preset.id}
            className="cursor-pointer transition-all hover:border-primary hover:shadow-sm"
            onClick={() => onApplyPreset(preset.config)}
          >
            <div className="flex flex-col items-center gap-2 p-4 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
                {preset.icon}
              </div>
              <div>
                <div className="font-medium">{preset.label}</div>
                <div className="text-xs text-muted-foreground">{preset.description}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
