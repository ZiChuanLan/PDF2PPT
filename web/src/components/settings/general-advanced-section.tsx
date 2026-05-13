"use client"

import * as React from "react"

import { Select } from "@/components/ui/select"

import type { Settings, LayoutAssistMode } from "@/lib/settings"
import {
  FieldLabel,
  CollapsibleSection,
} from "@/components/settings/settings-shared"

const VISUAL_ASSIST_MODE_OPTIONS: Array<{ id: LayoutAssistMode; label: string }> = [
  { id: "off", label: "关闭" },
  { id: "on", label: "开启" },
  { id: "auto", label: "自动" },
]

type GeneralAdvancedSectionProps = {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}

export function GeneralAdvancedSection({
  settings,
  onSettingsChange,
}: GeneralAdvancedSectionProps) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">通用高级设置</h3>
        <p className="text-sm text-muted-foreground">专家选项和调优参数</p>
      </div>

      {/* Visual Assist Modes */}
      {settings.enableLayoutAssist && (
        <CollapsibleSection title="视觉辅助模式" defaultOpen={false}>
          <div className="space-y-4">
            <div className="grid gap-2">
              <FieldLabel htmlFor="visualAssistModeLocal">传统 OCR 视觉辅助</FieldLabel>
              <Select
                id="visualAssistModeLocal"
                value={settings.visualAssistModeLocal}
                onChange={(e) =>
                  onSettingsChange({
                    visualAssistModeLocal: e.target.value as LayoutAssistMode,
                  })
                }
                options={VISUAL_ASSIST_MODE_OPTIONS}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="visualAssistModeRemote">AIOCR 视觉辅助</FieldLabel>
              <Select
                id="visualAssistModeRemote"
                value={settings.visualAssistModeRemote}
                onChange={(e) =>
                  onSettingsChange({
                    visualAssistModeRemote: e.target.value as LayoutAssistMode,
                  })
                }
                options={VISUAL_ASSIST_MODE_OPTIONS}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="visualAssistModeBaiduDoc">百度解析视觉辅助</FieldLabel>
              <Select
                id="visualAssistModeBaiduDoc"
                value={settings.visualAssistModeBaiduDoc}
                onChange={(e) =>
                  onSettingsChange({
                    visualAssistModeBaiduDoc: e.target.value as LayoutAssistMode,
                  })
                }
                options={VISUAL_ASSIST_MODE_OPTIONS}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="visualAssistModeMineru">MinerU 视觉辅助</FieldLabel>
              <Select
                id="visualAssistModeMineru"
                value={settings.visualAssistModeMineru}
                onChange={(e) =>
                  onSettingsChange({
                    visualAssistModeMineru: e.target.value as LayoutAssistMode,
                  })
                }
                options={VISUAL_ASSIST_MODE_OPTIONS}
              />
            </div>
          </div>
        </CollapsibleSection>
      )}
    </div>
  )
}
