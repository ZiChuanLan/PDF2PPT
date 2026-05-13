"use client"

import * as React from "react"
import { KeyRoundIcon } from "lucide-react"

import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { HoverHint } from "@/components/ui/hover-hint"
import { Checkbox } from "@/components/ui/checkbox"

import type { Settings, Provider, MainProvider, PptGenerationMode } from "@/lib/settings"
import { PPT_GENERATION_MODE_LABELS } from "@/lib/settings"
import {
  FieldLabel,
  SensitiveInput,
  CollapsibleSection,
} from "@/components/settings/settings-shared"
import { toast } from "sonner"

const PROVIDER_OPTIONS: Array<{ id: Provider; label: string }> = [
  { id: "openai", label: "OpenAI" },
  { id: "claude", label: "Claude" },
]

const PPT_MODE_OPTIONS = Object.entries(PPT_GENERATION_MODE_LABELS).map(([id, label]) => ({
  id: id as PptGenerationMode,
  label,
}))

type OutputQualitySectionProps = {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}

export function OutputQualitySection({
  settings,
  onSettingsChange,
}: OutputQualitySectionProps) {
  const [showOpenAIKey, setShowOpenAIKey] = React.useState(false)
  const [showClaudeKey, setShowClaudeKey] = React.useState(false)

  const validateApiKey = (key: string, provider: string): boolean => {
    if (!key.trim()) return true

    if (provider === "openai" && !key.startsWith("sk-")) {
      toast.error("OpenAI API Key 格式错误（应以 sk- 开头）")
      return false
    }
    if (provider === "claude" && !key.startsWith("sk-ant-")) {
      toast.error("Claude API Key 格式错误（应以 sk-ant- 开头）")
      return false
    }

    return true
  }

  // MinerU handles PPT generation internally
  const isMineruMode = settings.parseEngineMode === "mineru_cloud"

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">3. 输出质量</h3>
        <p className="text-sm text-muted-foreground">配置PPT生成和优化选项</p>
      </div>

      {/* Content Generation AI */}
      {!isMineruMode && (
        <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
          <div className="text-sm text-muted-foreground mb-2">
            内容生成AI（用于布局辅助和PPT生成）
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="provider">
              内容生成AI 提供方
              <HoverHint text="OpenAI 或 Claude（用于布局辅助和PPT生成）" />
            </FieldLabel>
            <Select
              id="provider"
              value={settings.provider}
              onChange={(e) => {
                const newProvider = e.target.value as Provider
                const updates: Partial<Settings> = { provider: newProvider }
                if (newProvider !== "mineru") {
                  updates.preferredMainProvider = newProvider as MainProvider
                }
                onSettingsChange(updates)
              }}
              options={PROVIDER_OPTIONS}
            />
          </div>

          {/* OpenAI API Key */}
          {(settings.provider === "openai" ||
            settings.parseEngineMode === "remote_ocr") && (
            <>
              <div className="grid gap-2">
                <FieldLabel htmlFor="openaiApiKey" required>
                  <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
                  OpenAI API Key
                </FieldLabel>
                <SensitiveInput
                  id="openaiApiKey"
                  value={settings.openaiApiKey}
                  onChange={(e) => onSettingsChange({ openaiApiKey: e.target.value })}
                  onBlur={(e) => validateApiKey(e.target.value, "openai")}
                  placeholder="sk-..."
                  show={showOpenAIKey}
                  onToggleShow={() => setShowOpenAIKey(!showOpenAIKey)}
                />
              </div>

              <div className="grid gap-2">
                <FieldLabel htmlFor="openaiBaseUrl">
                  Base URL
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
                  模型名称
                  <HoverHint text="留空使用默认模型" />
                </FieldLabel>
                <Input
                  id="openaiModel"
                  value={settings.openaiModel}
                  onChange={(e) => onSettingsChange({ openaiModel: e.target.value })}
                  placeholder="留空使用默认"
                />
              </div>

              <p className="text-xs text-muted-foreground">
                填写自定义 Base URL 即可接入任何 OpenAI 兼容服务（硅基流动、DeepSeek 等）
              </p>
            </>
          )}

          {/* Claude API Key */}
          {settings.provider === "claude" && (
            <div className="grid gap-2">
              <FieldLabel htmlFor="claudeApiKey" required>
                <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
                Claude API Key
              </FieldLabel>
              <SensitiveInput
                id="claudeApiKey"
                value={settings.claudeApiKey}
                onChange={(e) => onSettingsChange({ claudeApiKey: e.target.value })}
                onBlur={(e) => validateApiKey(e.target.value, "claude")}
                placeholder="sk-ant-..."
                show={showClaudeKey}
                onToggleShow={() => setShowClaudeKey(!showClaudeKey)}
              />
            </div>
          )}
        </div>
      )}

      {/* PPT Generation Mode */}
      <div className="grid gap-2">
        <FieldLabel htmlFor="pptGenerationMode">
          PPT 生成模式
          <HoverHint text="精准模式保留最多细节，快速模式平衡质量与速度，极速模式最快" />
        </FieldLabel>
        <Select
          id="pptGenerationMode"
          value={settings.pptGenerationMode}
          onChange={(e) =>
            onSettingsChange({
              pptGenerationMode: e.target.value as Settings["pptGenerationMode"],
            })
          }
          options={PPT_MODE_OPTIONS}
        />
      </div>

      {/* Layout Assist */}
      <div className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center space-x-2">
          <Checkbox
            id="enableLayoutAssist"
            checked={settings.enableLayoutAssist}
            onCheckedChange={(checked) =>
              onSettingsChange({ enableLayoutAssist: checked as boolean })
            }
          />
          <FieldLabel htmlFor="enableLayoutAssist" className="mb-0">
            启用布局辅助
            <HoverHint text="使用 AI 辅助版面分析（实验性功能）" />
          </FieldLabel>
        </div>

        {settings.enableLayoutAssist && (
          <div className="ml-6 space-y-4 border-l-2 pl-4">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="layoutAssistApplyImageRegions"
                checked={settings.layoutAssistApplyImageRegions}
                onCheckedChange={(checked) =>
                  onSettingsChange({ layoutAssistApplyImageRegions: checked as boolean })
                }
              />
              <FieldLabel htmlFor="layoutAssistApplyImageRegions" className="mb-0">
                应用图片区域识别
                <HoverHint text="可能会隐藏装饰性图片" />
              </FieldLabel>
            </div>
          </div>
        )}
      </div>

      {/* Advanced Output Settings */}
      <CollapsibleSection title="输出高级选项" defaultOpen={false}>
        <div className="space-y-4">
          <div className="grid gap-2">
            <FieldLabel htmlFor="textEraseMode">
              文字擦除模式
              <HoverHint text="智能擦除更精确，快速填充更快" />
            </FieldLabel>
            <Select
              id="textEraseMode"
              value={settings.textEraseMode}
              onChange={(e) =>
                onSettingsChange({ textEraseMode: e.target.value as Settings["textEraseMode"] })
              }
              options={[
                { id: "fill", label: "快速填充" },
                { id: "smart", label: "智能擦除" },
              ]}
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="scannedPageMode">
              扫描页模式
              <HoverHint text="分段模式图片可编辑，整页模式图片作为背景" />
            </FieldLabel>
            <Select
              id="scannedPageMode"
              value={settings.scannedPageMode}
              onChange={(e) =>
                onSettingsChange({
                  scannedPageMode: e.target.value as Settings["scannedPageMode"],
                })
              }
              options={[
                { id: "segmented", label: "分段模式（图片可编辑）" },
                { id: "fullpage", label: "整页模式（图片作为背景）" },
              ]}
            />
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="removeFooterNotebooklm"
              checked={settings.removeFooterNotebooklm}
              onCheckedChange={(checked) =>
                onSettingsChange({ removeFooterNotebooklm: checked as boolean })
              }
            />
            <FieldLabel htmlFor="removeFooterNotebooklm" className="mb-0">
              移除 NotebookLM 页脚
              <HoverHint text="移除 NotebookLM 导出的页脚品牌标识" />
            </FieldLabel>
          </div>
        </div>
      </CollapsibleSection>

      {/* Image Processing Parameters */}
      <CollapsibleSection title="图片处理参数" defaultOpen={false}>
        <div className="space-y-4">
          <div className="grid gap-2">
            <FieldLabel htmlFor="imageBgClearExpandMinPt">背景清除最小扩展（pt）</FieldLabel>
            <Input
              id="imageBgClearExpandMinPt"
              type="number"
              step="0.01"
              value={settings.imageBgClearExpandMinPt}
              onChange={(e) => onSettingsChange({ imageBgClearExpandMinPt: e.target.value })}
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="imageBgClearExpandMaxPt">背景清除最大扩展（pt）</FieldLabel>
            <Input
              id="imageBgClearExpandMaxPt"
              type="number"
              step="0.01"
              value={settings.imageBgClearExpandMaxPt}
              onChange={(e) => onSettingsChange({ imageBgClearExpandMaxPt: e.target.value })}
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="imageBgClearExpandRatio">背景清除扩展比例</FieldLabel>
            <Input
              id="imageBgClearExpandRatio"
              type="number"
              step="0.001"
              value={settings.imageBgClearExpandRatio}
              onChange={(e) => onSettingsChange({ imageBgClearExpandRatio: e.target.value })}
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="scannedImageRegionMinAreaRatio">图片区域最小面积比</FieldLabel>
            <Input
              id="scannedImageRegionMinAreaRatio"
              type="number"
              step="0.0001"
              value={settings.scannedImageRegionMinAreaRatio}
              onChange={(e) =>
                onSettingsChange({ scannedImageRegionMinAreaRatio: e.target.value })
              }
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="scannedImageRegionMaxAreaRatio">图片区域最大面积比</FieldLabel>
            <Input
              id="scannedImageRegionMaxAreaRatio"
              type="number"
              step="0.01"
              value={settings.scannedImageRegionMaxAreaRatio}
              onChange={(e) =>
                onSettingsChange({ scannedImageRegionMaxAreaRatio: e.target.value })
              }
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="scannedImageRegionMaxAspectRatio">
              图片区域最大宽高比
            </FieldLabel>
            <Input
              id="scannedImageRegionMaxAspectRatio"
              type="number"
              step="0.1"
              value={settings.scannedImageRegionMaxAspectRatio}
              onChange={(e) =>
                onSettingsChange({ scannedImageRegionMaxAspectRatio: e.target.value })
              }
            />
          </div>
        </div>
      </CollapsibleSection>
    </div>
  )
}
