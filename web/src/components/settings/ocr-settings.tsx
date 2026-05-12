"use client"

import * as React from "react"

import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { HoverHint } from "@/components/ui/hover-hint"

import type { Settings, OcrProvider, OcrAiProvider, OcrAiChainMode } from "@/lib/settings"
import { BAIDU_DOC_PARSE_TYPE_LABELS } from "@/lib/settings"
import { LAYOUT_MODELS } from "@/lib/layout-models"
import {
  FieldLabel,
  SensitiveInput,
  CollapsibleSection,
} from "@/components/settings/settings-shared"
import { useModelDownload } from "@/hooks/use-model-download"
import { DownloadProgressButton } from "@/components/download-progress-button"

const OCR_PROVIDER_OPTIONS: Array<{ id: OcrProvider; label: string }> = [
  { id: "machine", label: "本地 OCR（PaddleOCR/Tesseract）" },
  { id: "paddleocr", label: "PaddleOCR" },
  { id: "tesseract", label: "Tesseract" },
  { id: "aiocr", label: "AIOCR（远程）" },
  { id: "baidu", label: "百度 OCR" },
]

const OCR_AI_PROVIDER_OPTIONS: Array<{ id: OcrAiProvider; label: string }> = [
  { id: "auto", label: "自动识别（推荐）" },
  { id: "openai", label: "OpenAI" },
  { id: "siliconflow", label: "SiliconFlow" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "ppio", label: "PPIO" },
  { id: "novita", label: "Novita" },
]

const OCR_AI_CHAIN_MODE_OPTIONS: Array<{ id: OcrAiChainMode; label: string }> = [
  { id: "layout_block", label: "本地切块识别（默认推荐）" },
  { id: "direct", label: "模型直出框和文字（提示词驱动）" },
  { id: "doc_parser", label: "内置文档解析（PaddleOCR-VL）" },
]

const BAIDU_DOC_PARSE_TYPE_OPTIONS = Object.entries(BAIDU_DOC_PARSE_TYPE_LABELS).map(
  ([id, label]) => ({
    id: id as Settings["baiduDocParseType"],
    label,
  })
)

const LAYOUT_MODEL_OPTIONS = Object.values(LAYOUT_MODELS).map((m) => ({
  id: m.modelId as Settings["ocrAiLayoutModel"],
  label: m.displayName,
  sizeMb: m.sizeMb,
  description: m.description,
}))

type OcrSettingsProps = {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}

export function OcrSettings({ settings, onSettingsChange }: OcrSettingsProps) {
  const [showOcrAiKey, setShowOcrAiKey] = React.useState(false)
  const [showBaiduKeys, setShowBaiduKeys] = React.useState(false)

  const { startDownload, cancelDownload, getDownloadState } = useModelDownload()

  const showTraditionalOcr = settings.parseEngineMode === "local_ocr"
  const showAiOcr = settings.parseEngineMode === "remote_ocr"
  const showBaiduOcr = settings.parseEngineMode === "baidu_doc"

  return (
    <div className="space-y-6">
      {/* Traditional OCR Settings */}
      {showTraditionalOcr && (
        <CollapsibleSection title="传统 OCR 设置" defaultOpen>
          <div className="space-y-4">
            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrProvider">
                OCR 提供方
                <HoverHint text="选择本地 OCR 引擎" />
              </FieldLabel>
              <Select
                id="ocrProvider"
                value={settings.ocrProvider}
                onChange={(e) =>
                  onSettingsChange({ ocrProvider: e.target.value as OcrProvider })
                }
                options={OCR_PROVIDER_OPTIONS.filter((opt) =>
                  ["machine", "paddleocr", "tesseract"].includes(opt.id)
                )}
              />
            </div>

            {/* PaddleOCR Download */}
            {(settings.ocrProvider === "paddleocr" || settings.ocrProvider === "machine") && (
              <div className="grid gap-2">
                <FieldLabel>PaddleOCR 模型</FieldLabel>
                <DownloadProgressButton
                  modelId="paddleocr"
                  label="PaddleOCR"
                  downloadState={getDownloadState("paddleocr")}
                  onDownload={() => startDownload("paddleocr")}
                  onCancel={() => cancelDownload("paddleocr")}
                />
              </div>
            )}

            {/* Tesseract Settings */}
            {(settings.ocrProvider === "tesseract" || settings.ocrProvider === "machine") && (
              <CollapsibleSection title="Tesseract 高级设置" defaultOpen={false}>
                <div className="grid gap-2">
                  <FieldLabel htmlFor="ocrTesseractLanguage">
                    Tesseract 语言
                    <HoverHint text="多语言用 + 连接，如 chi_sim+eng" />
                  </FieldLabel>
                  <Input
                    id="ocrTesseractLanguage"
                    value={settings.ocrTesseractLanguage}
                    onChange={(e) =>
                      onSettingsChange({ ocrTesseractLanguage: e.target.value })
                    }
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
              </CollapsibleSection>
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* AIOCR Settings */}
      {showAiOcr && (
        <CollapsibleSection title="AIOCR 设置" defaultOpen>
          <div className="space-y-4">
            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiProvider">
                AIOCR 提供方
                <HoverHint text="选择 AI OCR 服务提供商" />
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
              <FieldLabel htmlFor="ocrAiApiKey" required>
                AIOCR API Key
              </FieldLabel>
              <SensitiveInput
                id="ocrAiApiKey"
                value={settings.ocrAiApiKey}
                onChange={(e) => onSettingsChange({ ocrAiApiKey: e.target.value })}
                placeholder="输入 API Key"
                show={showOcrAiKey}
                onToggleShow={() => setShowOcrAiKey(!showOcrAiKey)}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiChainMode">
                识别链路模式
                <HoverHint text="版面切块：本地切块后识别（推荐）；直出：模型直接输出；文档解析：使用 PaddleOCR-VL" />
              </FieldLabel>
              <Select
                id="ocrAiChainMode"
                value={settings.ocrAiChainMode}
                onChange={(e) =>
                  onSettingsChange({ ocrAiChainMode: e.target.value as OcrAiChainMode })
                }
                options={OCR_AI_CHAIN_MODE_OPTIONS}
              />
            </div>

            {/* Layout Model (for layout_block mode) */}
            {settings.ocrAiChainMode === "layout_block" && (
              <div className="grid gap-2">
                <FieldLabel htmlFor="ocrAiLayoutModel">
                  版面切块模型
                  <HoverHint text="选择用于版面分析的模型" />
                </FieldLabel>
                <div className="space-y-2">
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
                  <DownloadProgressButton
                    modelId={settings.ocrAiLayoutModel}
                    label={
                      LAYOUT_MODEL_OPTIONS.find((m) => m.id === settings.ocrAiLayoutModel)
                        ?.label || settings.ocrAiLayoutModel
                    }
                    downloadState={getDownloadState(settings.ocrAiLayoutModel)}
                    onDownload={() => startDownload(settings.ocrAiLayoutModel)}
                    onCancel={() => cancelDownload(settings.ocrAiLayoutModel)}
                  />
                </div>
              </div>
            )}

            <CollapsibleSection title="AIOCR 高级设置" defaultOpen={false}>
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
            </CollapsibleSection>
          </div>
        </CollapsibleSection>
      )}

      {/* Baidu OCR Settings */}
      {showBaiduOcr && (
        <CollapsibleSection title="百度 OCR 设置" defaultOpen>
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
                    baiduDocParseType: e.target.value as Settings["baiduDocParseType"],
                  })
                }
                options={BAIDU_DOC_PARSE_TYPE_OPTIONS}
              />
            </div>

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
        </CollapsibleSection>
      )}
    </div>
  )
}
