"use client"

import * as React from "react"

import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { HoverHint } from "@/components/ui/hover-hint"

import type { Settings, LayoutAssistMode, OcrAiPromptPreset } from "@/lib/settings"
import {
  FieldLabel,
  CollapsibleSection,
  PromptTextarea,
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
  const showAiOcrPrompts = settings.parseEngineMode === "remote_ocr"

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

      {/* AIOCR Prompt Overrides */}
      {showAiOcrPrompts && (
        <CollapsibleSection title="AIOCR 提示词覆盖" defaultOpen={false}>
          <div className="space-y-4">
            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiPromptPreset">
                提示词预设
                <HoverHint text="选择适合模型的提示词模板" />
              </FieldLabel>
              <Select
                id="ocrAiPromptPreset"
                value={settings.ocrAiPromptPreset}
                onChange={(e) =>
                  onSettingsChange({
                    ocrAiPromptPreset: e.target.value as OcrAiPromptPreset,
                  })
                }
                options={[
                  { id: "auto", label: "自动（按模型推断）" },
                  { id: "qwen_vl", label: "Qwen-VL" },
                  { id: "deepseek_ocr", label: "DeepSeek-OCR" },
                  { id: "openai_vision", label: "OpenAI / GPT 视觉" },
                  { id: "glm_v", label: "GLM-V" },
                  { id: "generic_vision", label: "通用视觉模型" },
                ]}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiDirectPromptOverride">直出模式提示词覆盖</FieldLabel>
              <PromptTextarea
                id="ocrAiDirectPromptOverride"
                value={settings.ocrAiDirectPromptOverride}
                onChange={(e) => onSettingsChange({ ocrAiDirectPromptOverride: e.target.value })}
                placeholder="留空使用默认提示词"
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiLayoutBlockPromptOverride">
                版面切块模式提示词覆盖
              </FieldLabel>
              <PromptTextarea
                id="ocrAiLayoutBlockPromptOverride"
                value={settings.ocrAiLayoutBlockPromptOverride}
                onChange={(e) =>
                  onSettingsChange({ ocrAiLayoutBlockPromptOverride: e.target.value })
                }
                placeholder="留空使用默认提示词"
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiImageRegionPromptOverride">
                图片区域提示词覆盖
              </FieldLabel>
              <PromptTextarea
                id="ocrAiImageRegionPromptOverride"
                value={settings.ocrAiImageRegionPromptOverride}
                onChange={(e) =>
                  onSettingsChange({ ocrAiImageRegionPromptOverride: e.target.value })
                }
                placeholder="留空使用默认提示词"
              />
            </div>
          </div>
        </CollapsibleSection>
      )}

      {/* API Configuration (for non-MinerU providers) */}
      {settings.parseEngineMode !== "mineru_cloud" && (
        <CollapsibleSection title="AI提供商API配置" defaultOpen={false}>
          <div className="space-y-4">
            {settings.provider === "openai" && (
              <>
                <div className="grid gap-2">
                  <FieldLabel htmlFor="openaiBaseUrl">
                    OpenAI Base URL
                    <HoverHint text="自定义 API 端点（可选）" />
                  </FieldLabel>
                  <Input
                    id="openaiBaseUrl"
                    value={settings.openaiBaseUrl}
                    onChange={(e) => onSettingsChange({ openaiBaseUrl: e.target.value })}
                    placeholder="https://api.openai.com/v1"
                  />
                </div>

                <div className="grid gap-2">
                  <FieldLabel htmlFor="openaiModel">
                    OpenAI 模型名称
                    <HoverHint text="留空使用默认模型" />
                  </FieldLabel>
                  <Input
                    id="openaiModel"
                    value={settings.openaiModel}
                    onChange={(e) => onSettingsChange({ openaiModel: e.target.value })}
                    placeholder="留空使用默认"
                  />
                </div>
              </>
            )}
          </div>
        </CollapsibleSection>
      )}
    </div>
  )
}
