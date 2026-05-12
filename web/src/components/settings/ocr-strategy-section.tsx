"use client"

import * as React from "react"
import { KeyRoundIcon } from "lucide-react"

import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { HoverHint } from "@/components/ui/hover-hint"

import type {
  Settings,
  OcrProvider,
  OcrAiProvider,
  OcrAiChainMode,
  BaiduDocParseType,
  Provider,
  MainProvider,
} from "@/lib/settings"
import { BAIDU_DOC_PARSE_TYPE_LABELS } from "@/lib/settings"
import { LAYOUT_MODELS } from "@/lib/layout-models"
import {
  FieldLabel,
  SensitiveInput,
  CollapsibleSection,
} from "@/components/settings/settings-shared"
import { useModelDownload } from "@/hooks/use-model-download"
import { DownloadProgressButton } from "@/components/download-progress-button"

const PROVIDER_OPTIONS: Array<{ id: Provider; label: string }> = [
  { id: "openai", label: "OpenAI" },
  { id: "claude", label: "Claude" },
]

const LOCAL_OCR_OPTIONS: Array<{ id: OcrProvider; label: string; description: string }> = [
  { id: "machine", label: "机器提取", description: "从PDF提取原生文字（最快）" },
  { id: "tesseract", label: "Tesseract OCR", description: "开源OCR引擎" },
  { id: "paddleocr", label: "PaddleOCR", description: "百度开源OCR（推荐）" },
  { id: "auto", label: "智能选择", description: "自动选择最佳方式" },
]

const REMOTE_OCR_OPTIONS: Array<{ id: OcrAiChainMode; label: string; description: string }> = [
  { id: "direct", label: "直接识别", description: "模型直接输出文字和位置" },
  { id: "doc_parser", label: "文档解析模式", description: "使用PaddleOCR-VL解析" },
  { id: "layout_block", label: "布局分块模式", description: "本地切块后识别（推荐）" },
]

const BAIDU_DOC_PARSE_TYPE_OPTIONS = Object.entries(BAIDU_DOC_PARSE_TYPE_LABELS).map(
  ([id, label]) => ({
    id: id as BaiduDocParseType,
    label,
  })
)

const OCR_AI_PROVIDER_OPTIONS: Array<{ id: OcrAiProvider; label: string }> = [
  { id: "auto", label: "自动识别（推荐）" },
  { id: "openai", label: "OpenAI" },
  { id: "siliconflow", label: "SiliconFlow" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "ppio", label: "PPIO" },
  { id: "novita", label: "Novita" },
]

const LAYOUT_MODEL_OPTIONS = Object.values(LAYOUT_MODELS).map((m) => ({
  id: m.modelId as Settings["ocrAiLayoutModel"],
  label: m.displayName,
  sizeMb: m.sizeMb,
}))

type OcrStrategySectionProps = {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}

export function OcrStrategySection({ settings, onSettingsChange }: OcrStrategySectionProps) {
  const [showOcrAiKey, setShowOcrAiKey] = React.useState(false)
  const [showBaiduKeys, setShowBaiduKeys] = React.useState(false)
  const [showOpenAIKey, setShowOpenAIKey] = React.useState(false)
  const [showClaudeKey, setShowClaudeKey] = React.useState(false)

  const { startDownload, cancelDownload, getDownloadState } = useModelDownload()

  const parseMode = settings.parseEngineMode

  // Don't show this section for MinerU (it handles OCR internally)
  if (parseMode === "mineru_cloud") {
    return null
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">2. 文字识别策略</h3>
        <p className="text-sm text-muted-foreground">
          {parseMode === "local_ocr" && "选择本地OCR引擎"}
          {parseMode === "remote_ocr" && "选择云端AI识别模式"}
          {parseMode === "baidu_doc" && "配置百度文档解析"}
        </p>
      </div>

      {/* Local OCR */}
      {parseMode === "local_ocr" && (
        <div className="space-y-3">
          {LOCAL_OCR_OPTIONS.map((option) => (
            <label
              key={option.id}
              className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-all ${
                settings.ocrProvider === option.id
                  ? "border-primary bg-primary/5"
                  : "hover:border-muted-foreground/50"
              }`}
            >
              <input
                type="radio"
                name="ocrProvider"
                value={option.id}
                checked={settings.ocrProvider === option.id}
                onChange={(e) =>
                  onSettingsChange({ ocrProvider: e.target.value as OcrProvider })
                }
                className="mt-1"
              />
              <div className="flex-1">
                <div className="font-medium">{option.label}</div>
                <div className="text-sm text-muted-foreground">{option.description}</div>
              </div>
            </label>
          ))}

          {/* PaddleOCR Download */}
          {(settings.ocrProvider === "paddleocr" || settings.ocrProvider === "auto") && (
            <div className="rounded-lg border bg-muted/30 p-4">
              <FieldLabel className="mb-2">PaddleOCR 模型下载</FieldLabel>
              <DownloadProgressButton
                modelId="paddleocr"
                label="PaddleOCR"
                downloadState={getDownloadState("paddleocr")}
                onDownload={() => startDownload("paddleocr")}
                onCancel={() => cancelDownload("paddleocr")}
              />
            </div>
          )}

          {/* Tesseract Advanced */}
          {(settings.ocrProvider === "tesseract" || settings.ocrProvider === "auto") && (
            <CollapsibleSection title="Tesseract 高级设置" defaultOpen={false}>
              <div className="space-y-4">
                <div className="grid gap-2">
                  <FieldLabel htmlFor="ocrTesseractLanguage">
                    Tesseract 语言
                    <HoverHint text="多语言用 + 连接，如 chi_sim+eng" />
                  </FieldLabel>
                  <Input
                    id="ocrTesseractLanguage"
                    value={settings.ocrTesseractLanguage}
                    onChange={(e) => onSettingsChange({ ocrTesseractLanguage: e.target.value })}
                    placeholder="chi_sim+eng"
                  />
                </div>

                <div className="grid gap-2">
                  <FieldLabel htmlFor="ocrTesseractMinConfidence">
                    最低置信度
                    <HoverHint text="0-100，较低值提高召回率" />
                  </FieldLabel>
                  <Input
                    id="ocrTesseractMinConfidence"
                    type="number"
                    min="0"
                    max="100"
                    value={settings.ocrTesseractMinConfidence}
                    onChange={(e) =>
                      onSettingsChange({ ocrTesseractMinConfidence: e.target.value })
                    }
                  />
                </div>
              </div>
            </CollapsibleSection>
          )}
        </div>
      )}

      {/* Remote OCR (AIOCR) */}
      {parseMode === "remote_ocr" && (
        <div className="space-y-4">
          <div className="space-y-3">
            {REMOTE_OCR_OPTIONS.map((option) => (
              <label
                key={option.id}
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-all ${
                  settings.ocrAiChainMode === option.id
                    ? "border-primary bg-primary/5"
                    : "hover:border-muted-foreground/50"
                }`}
              >
                <input
                  type="radio"
                  name="ocrAiChainMode"
                  value={option.id}
                  checked={settings.ocrAiChainMode === option.id}
                  onChange={(e) =>
                    onSettingsChange({ ocrAiChainMode: e.target.value as OcrAiChainMode })
                  }
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="font-medium">{option.label}</div>
                  <div className="text-sm text-muted-foreground">{option.description}</div>
                </div>
              </label>
            ))}
          </div>

          {/* Primary AI Configuration (for OCR + fallback for layout assist) */}
          <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
            <div className="text-sm text-muted-foreground mb-2">
              主AI配置（用于OCR识别，也可作为布局辅助的回退）
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="provider">
                AI提供商
                <HoverHint text="OpenAI 或 Claude（主要用于OCR识别）" />
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
            {settings.provider === "openai" && (
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
                    placeholder="sk-..."
                    show={showOpenAIKey}
                    onToggleShow={() => setShowOpenAIKey(!showOpenAIKey)}
                  />
                </div>
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
                  placeholder="sk-ant-..."
                  show={showClaudeKey}
                  onToggleShow={() => setShowClaudeKey(!showClaudeKey)}
                />
              </div>
            )}
          </div>

          {/* Secondary AI Configuration (dedicated OCR AI) */}
          <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
            <div className="text-sm text-muted-foreground mb-2">
              专用OCR AI配置（可选，留空则使用上面的主AI配置）
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiProvider">
                OCR AI服务提供商
                <HoverHint text="选择专用的 AI OCR 服务提供商" />
              </FieldLabel>
              <Select
                id="ocrAiProvider"
                value={settings.ocrAiProvider}
                onChange={(e) =>
                  onSettingsChange({ ocrAiProvider: e.target.value as OcrAiProvider })
                }
                options={OCR_AI_PROVIDER_OPTIONS}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiApiKey">
                <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
                专用 OCR AI API Key
              </FieldLabel>
              <SensitiveInput
                id="ocrAiApiKey"
                value={settings.ocrAiApiKey}
                onChange={(e) => onSettingsChange({ ocrAiApiKey: e.target.value })}
                placeholder="留空使用主AI配置"
                show={showOcrAiKey}
                onToggleShow={() => setShowOcrAiKey(!showOcrAiKey)}
              />
            </div>
          </div>

          {/* Layout Model (for layout_block mode) */}
          {settings.ocrAiChainMode === "layout_block" && (
            <div className="rounded-lg border bg-muted/30 p-4">
              <div className="grid gap-2">
                <FieldLabel htmlFor="ocrAiLayoutModel">
                  版面切块模型
                  <HoverHint text="选择用于版面分析的模型" />
                </FieldLabel>
                <Select
                  id="ocrAiLayoutModel"
                  value={settings.ocrAiLayoutModel}
                  onChange={(e) =>
                    onSettingsChange({
                      ocrAiLayoutModel: e.target.value as Settings["ocrAiLayoutModel"],
                    })
                  }
                  options={LAYOUT_MODEL_OPTIONS.map((opt) => ({
                    id: opt.id,
                    label: `${opt.label} (${opt.sizeMb}MB)`,
                  }))}
                />
              </div>
              <div className="mt-2">
                <DownloadProgressButton
                  modelId={settings.ocrAiLayoutModel}
                  label={
                    LAYOUT_MODEL_OPTIONS.find((m) => m.id === settings.ocrAiLayoutModel)?.label ||
                    settings.ocrAiLayoutModel
                  }
                  downloadState={getDownloadState(settings.ocrAiLayoutModel)}
                  onDownload={() => startDownload(settings.ocrAiLayoutModel)}
                  onCancel={() => cancelDownload(settings.ocrAiLayoutModel)}
                />
              </div>
            </div>
          )}

          {/* AIOCR Advanced Settings */}
          <CollapsibleSection title="云端识别高级选项" defaultOpen={false}>
            <div className="space-y-4">
              <div className="grid gap-2">
                <FieldLabel htmlFor="ocrAiBaseUrl">
                  API Base URL
                  <HoverHint text="自定义 API 端点（可选）" />
                </FieldLabel>
                <Input
                  id="ocrAiBaseUrl"
                  value={settings.ocrAiBaseUrl}
                  onChange={(e) => onSettingsChange({ ocrAiBaseUrl: e.target.value })}
                  placeholder="https://api.example.com/v1"
                />
              </div>

              <div className="grid gap-2">
                <FieldLabel htmlFor="ocrAiModel">
                  模型名称
                  <HoverHint text="留空使用默认模型" />
                </FieldLabel>
                <Input
                  id="ocrAiModel"
                  value={settings.ocrAiModel}
                  onChange={(e) => onSettingsChange({ ocrAiModel: e.target.value })}
                  placeholder="留空使用默认"
                />
              </div>
            </div>
          </CollapsibleSection>

          {/* AIOCR Concurrency Settings */}
          <CollapsibleSection title="并发和速率限制" defaultOpen={false}>
            <div className="space-y-4">
              <div className="grid gap-2">
                <FieldLabel htmlFor="ocrAiPageConcurrency">
                  页面并发度
                  <HoverHint text="同时处理的页面数量" />
                </FieldLabel>
                <Input
                  id="ocrAiPageConcurrency"
                  type="number"
                  min="1"
                  max="1000"
                  value={settings.ocrAiPageConcurrency}
                  onChange={(e) => onSettingsChange({ ocrAiPageConcurrency: e.target.value })}
                />
              </div>

              <div className="grid gap-2">
                <FieldLabel htmlFor="ocrAiMaxRetries">
                  最大重试次数
                  <HoverHint text="API 请求失败后的重试次数" />
                </FieldLabel>
                <Input
                  id="ocrAiMaxRetries"
                  type="number"
                  min="0"
                  max="1000"
                  value={settings.ocrAiMaxRetries}
                  onChange={(e) => onSettingsChange({ ocrAiMaxRetries: e.target.value })}
                />
              </div>

              <div className="grid gap-2">
                <FieldLabel htmlFor="ocrAiRequestsPerMinute">
                  每分钟请求数限制（可选）
                  <HoverHint text="API 速率限制，留空不限制" />
                </FieldLabel>
                <Input
                  id="ocrAiRequestsPerMinute"
                  type="number"
                  min="1"
                  value={settings.ocrAiRequestsPerMinute}
                  onChange={(e) => onSettingsChange({ ocrAiRequestsPerMinute: e.target.value })}
                  placeholder="留空不限制"
                />
              </div>

              <div className="grid gap-2">
                <FieldLabel htmlFor="ocrAiTokensPerMinute">
                  每分钟 Token 数限制（可选）
                  <HoverHint text="API Token 速率限制，留空不限制" />
                </FieldLabel>
                <Input
                  id="ocrAiTokensPerMinute"
                  type="number"
                  min="1"
                  value={settings.ocrAiTokensPerMinute}
                  onChange={(e) => onSettingsChange({ ocrAiTokensPerMinute: e.target.value })}
                  placeholder="留空不限制"
                />
              </div>
            </div>
          </CollapsibleSection>
        </div>
      )}

      {/* Baidu Doc Parse */}
      {parseMode === "baidu_doc" && (
        <div className="space-y-4">
          <div className="grid gap-2">
            <FieldLabel htmlFor="baiduDocParseType">
              百度解析类型
              <HoverHint text="选择百度文档解析模式" />
            </FieldLabel>
            <Select
              id="baiduDocParseType"
              value={settings.baiduDocParseType}
              onChange={(e) =>
                onSettingsChange({
                  baiduDocParseType: e.target.value as BaiduDocParseType,
                })
              }
              options={BAIDU_DOC_PARSE_TYPE_OPTIONS}
            />
          </div>

          <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrBaiduAppId" required>
                百度 App ID
              </FieldLabel>
              <Input
                id="ocrBaiduAppId"
                value={settings.ocrBaiduAppId}
                onChange={(e) => onSettingsChange({ ocrBaiduAppId: e.target.value })}
                placeholder="输入 App ID"
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrBaiduApiKey" required>
                <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
                百度 API Key
              </FieldLabel>
              <SensitiveInput
                id="ocrBaiduApiKey"
                value={settings.ocrBaiduApiKey}
                onChange={(e) => onSettingsChange({ ocrBaiduApiKey: e.target.value })}
                placeholder="输入 API Key"
                show={showBaiduKeys}
                onToggleShow={() => setShowBaiduKeys(!showBaiduKeys)}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrBaiduSecretKey" required>
                <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
                百度 Secret Key
              </FieldLabel>
              <SensitiveInput
                id="ocrBaiduSecretKey"
                value={settings.ocrBaiduSecretKey}
                onChange={(e) => onSettingsChange({ ocrBaiduSecretKey: e.target.value })}
                placeholder="输入 Secret Key"
                show={showBaiduKeys}
                onToggleShow={() => setShowBaiduKeys(!showBaiduKeys)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
