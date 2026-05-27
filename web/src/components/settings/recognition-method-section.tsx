"use client"

import * as React from "react"
import { ChevronDownIcon, KeyRoundIcon, RefreshCwIcon, SearchIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { HoverHint } from "@/components/ui/hover-hint"
import { Checkbox } from "@/components/ui/checkbox"

import type {
  Settings,
  OcrAiProvider,
  OcrAiPromptPreset,
  BaiduDocParseType,
  MineruModelVersion,
} from "@/lib/settings"
import { BAIDU_DOC_PARSE_TYPE_LABELS } from "@/lib/settings"
import { LAYOUT_MODELS } from "@/lib/layout-models"
import {
  AdvancedReveal,
  FieldLabel,
  SensitiveInput,
  CollapsibleSection,
  PromptTextarea,
} from "@/components/settings/settings-shared"
import { useModelDownload } from "@/hooks/use-model-download"
import { useModelStatus } from "@/hooks/use-model-status"
import { DownloadProgressButton } from "@/components/download-progress-button"
import { fetchModels } from "@/lib/api"
import { toast } from "sonner"

// ============================================================================
// Unified recognition method options
// ============================================================================

type RecognitionOption = {
  id: string
  group: "local" | "ai" | "baidu" | "mineru"
  label: string
  description: string
  needsApi: boolean
}

const RECOGNITION_OPTIONS: RecognitionOption[] = [
  // Local recognition (no API needed)
  {
    id: "local_machine",
    group: "local",
    label: "机器提取",
    description: "从PDF提取原生文字，速度最快",
    needsApi: false,
  },
  {
    id: "local_paddleocr",
    group: "local",
    label: "PaddleOCR",
    description: "百度开源OCR引擎，推荐使用",
    needsApi: false,
  },
  {
    id: "local_tesseract",
    group: "local",
    label: "Tesseract",
    description: "开源OCR引擎，支持多语言",
    needsApi: false,
  },
  // AI recognition (needs API)
  {
    id: "ai_direct",
    group: "ai",
    label: "直接识别",
    description: "AI模型直接输出文字和位置",
    needsApi: true,
  },
  {
    id: "ai_layout_block",
    group: "ai",
    label: "版面分析",
    description: "本地切块后AI识别，精度最高",
    needsApi: true,
  },
  // Baidu
  {
    id: "baidu",
    group: "baidu",
    label: "百度识别",
    description: "百度文档解析接口",
    needsApi: true,
  },
  // MinerU
  {
    id: "mineru",
    group: "mineru",
    label: "MinerU",
    description: "结构化文档解析服务",
    needsApi: true,
  },
]

const GROUP_LABELS: Record<string, string> = {
  local: "本地识别（无需 API）",
  ai: "AI 识别（需要 API）",
  baidu: "百度识别",
  mineru: "MinerU",
}

// ============================================================================
// Helper: map settings to recognition option ID
// ============================================================================

function getRecognitionId(settings: Settings): string {
  const mode = settings.parseEngineMode
  if (mode === "mineru_cloud") return "mineru"
  if (mode === "baidu_doc") return "baidu"
  if (mode === "remote_ocr") {
    return settings.ocrAiChainMode === "layout_block" ? "ai_layout_block" : "ai_direct"
  }
  // local_ocr
  const ocrProvider = settings.ocrProvider
  if (ocrProvider === "paddleocr") return "local_paddleocr"
  if (ocrProvider === "tesseract") return "local_tesseract"
  return "local_machine"
}

function applyRecognitionId(id: string, current: Settings): Partial<Settings> {
  switch (id) {
    case "local_machine":
      return { parseEngineMode: "local_ocr", ocrProvider: "machine" }
    case "local_paddleocr":
      return { parseEngineMode: "local_ocr", ocrProvider: "paddleocr" }
    case "local_tesseract":
      return { parseEngineMode: "local_ocr", ocrProvider: "tesseract" }
    case "ai_direct":
      return {
        parseEngineMode: "remote_ocr",
        ocrProvider: "aiocr",
        ocrAiChainMode: "direct",
        ocrAiProvider: current.ocrAiProvider === "auto" ? "siliconflow" : current.ocrAiProvider,
        ocrAiBaseUrl: current.ocrAiBaseUrl || "https://api.siliconflow.cn/v1",
      }
    case "ai_layout_block":
      return {
        parseEngineMode: "remote_ocr",
        ocrProvider: "aiocr",
        ocrAiChainMode: "layout_block",
        ocrAiProvider: current.ocrAiProvider === "auto" ? "siliconflow" : current.ocrAiProvider,
        ocrAiBaseUrl: current.ocrAiBaseUrl || "https://api.siliconflow.cn/v1",
      }
    case "baidu":
      return { parseEngineMode: "baidu_doc", ocrProvider: "baidu" }
    case "mineru":
      return { parseEngineMode: "mineru_cloud", provider: "mineru" }
    default:
      return {}
  }
}

// ============================================================================
// Sub-components for API config sections
// ============================================================================

const AI_PROVIDER_OPTIONS: Array<{ id: OcrAiProvider; label: string }> = [
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

const MINERU_MODEL_OPTIONS: Array<{ id: MineruModelVersion; label: string }> = [
  { id: "pipeline", label: "Pipeline" },
  { id: "vlm", label: "VLM" },
  { id: "MinerU-HTML", label: "MinerU-HTML" },
]

const BAIDU_DOC_PARSE_TYPE_OPTIONS = Object.entries(BAIDU_DOC_PARSE_TYPE_LABELS).map(
  ([id, label]) => ({
    id: id as BaiduDocParseType,
    label,
  })
)

function AiOcrApiConfig({
  settings,
  onSettingsChange,
}: {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}) {
  const [showKey, setShowKey] = React.useState(false)
  const [fetchingModels, setFetchingModels] = React.useState(false)
  const [availableModels, setAvailableModels] = React.useState<string[]>([])

  const { data: modelStatus, refetch: refetchModelStatus } = useModelStatus()
  const { startDownload, cancelDownload, getDownloadState } = useModelDownload({
    onDownloadComplete: () => void refetchModelStatus(),
  })

  const downloadedLayoutModels = React.useMemo(() => {
    if (!modelStatus?.local) return new Set<string>()
    return new Set(
      LAYOUT_MODEL_OPTIONS
        .filter((opt) => modelStatus.local[opt.id]?.ready)
        .map((opt) => opt.id)
    )
  }, [modelStatus])

  React.useEffect(() => {
    if (downloadedLayoutModels.size > 0 && settings.ocrAiLayoutModel) {
      if (!downloadedLayoutModels.has(settings.ocrAiLayoutModel)) {
        const first = [...downloadedLayoutModels][0]
        if (first) {
          onSettingsChange({ ocrAiLayoutModel: first as Settings["ocrAiLayoutModel"] })
        }
      }
    }
  }, [downloadedLayoutModels, settings.ocrAiLayoutModel, onSettingsChange])

  const handleFetchModels = React.useCallback(async () => {
    if (!settings.ocrAiApiKey) {
      toast.error("请先填写 API Key")
      return
    }
    setFetchingModels(true)
    setAvailableModels([])
    try {
      const models = await fetchModels({
        provider: settings.ocrAiProvider,
        apiKey: settings.ocrAiApiKey,
        baseUrl: settings.ocrAiBaseUrl || undefined,
        capability: "vision",
      })
      setAvailableModels(models)
      if (models.length === 0) {
        toast.info("该 API 未返回可用模型")
      } else {
        toast.success(`获取到 ${models.length} 个模型`)
      }
    } catch (e) {
      console.error("Failed to fetch models:", e)
      toast.error(String(e))
    } finally {
      setFetchingModels(false)
    }
  }, [settings.ocrAiProvider, settings.ocrAiApiKey, settings.ocrAiBaseUrl])

  return (
    <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
      <div className="text-sm font-medium text-muted-foreground">AI 识别 API 设置</div>

      <div className="grid gap-2">
        <FieldLabel htmlFor="ocrAiProvider">
          API 提供方
          <HoverHint text="选择 AI OCR 服务提供商" />
        </FieldLabel>
        <Select
          id="ocrAiProvider"
          value={settings.ocrAiProvider}
          onChange={(e) =>
            onSettingsChange({ ocrAiProvider: e.target.value as OcrAiProvider })
          }
          options={AI_PROVIDER_OPTIONS}
        />
      </div>

      <div className="grid gap-2">
        <FieldLabel htmlFor="ocrAiApiKey" required>
          <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
          API Key
        </FieldLabel>
        <SensitiveInput
          id="ocrAiApiKey"
          value={settings.ocrAiApiKey}
          onChange={(e) => onSettingsChange({ ocrAiApiKey: e.target.value })}
          placeholder="输入 API Key"
          show={showKey}
          onToggleShow={() => setShowKey(!showKey)}
        />
      </div>

      <div className="grid gap-2">
        <FieldLabel htmlFor="ocrAiBaseUrl">
          Base URL
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
        <div className="flex items-center justify-between">
          <FieldLabel htmlFor="ocrAiModel" className="mb-0">
            模型名称
            <HoverHint text="留空使用默认模型" />
          </FieldLabel>
          <button
            type="button"
            onClick={handleFetchModels}
            disabled={fetchingModels}
            className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors disabled:opacity-50"
          >
            {fetchingModels ? (
              <RefreshCwIcon className="h-3 w-3 animate-spin" />
            ) : (
              <SearchIcon className="h-3 w-3" />
            )}
            获取模型列表
          </button>
        </div>
        {availableModels.length > 0 ? (
          <Select
            id="ocrAiModel"
            value={settings.ocrAiModel}
            onChange={(e) => onSettingsChange({ ocrAiModel: e.target.value })}
            options={[
              { id: "", label: "留空使用默认" },
              ...availableModels.map((m) => ({ id: m, label: m })),
            ]}
          />
        ) : (
          <Input
            id="ocrAiModel"
            value={settings.ocrAiModel}
            onChange={(e) => onSettingsChange({ ocrAiModel: e.target.value })}
            placeholder="留空使用默认"
          />
        )}
      </div>

      {/* Layout model download (for layout_block mode) */}
      {settings.ocrAiChainMode === "layout_block" && (
        <div className="grid gap-2">
          <FieldLabel htmlFor="ocrAiLayoutModel">
            版面分析模型
            <HoverHint text="选择用于版面分析的本地模型" />
          </FieldLabel>
          <Select
            id="ocrAiLayoutModel"
            value={settings.ocrAiLayoutModel}
            onChange={(e) =>
              onSettingsChange({
                ocrAiLayoutModel: e.target.value as Settings["ocrAiLayoutModel"],
              })
            }
            options={LAYOUT_MODEL_OPTIONS.map((opt) => {
              const isDownloaded = modelStatus?.local[opt.id]?.ready ?? false
              return {
                id: opt.id,
                label: `${opt.label} (${opt.sizeMb}MB) — ${isDownloaded ? "已下载" : "未下载"}`,
              }
            })}
          />
          <div className="mt-2">
            <DownloadProgressButton
              modelId={settings.ocrAiLayoutModel}
              label={
                LAYOUT_MODEL_OPTIONS.find(
                  (m) => m.id === settings.ocrAiLayoutModel
                )?.label || settings.ocrAiLayoutModel
              }
              downloadState={getDownloadState(settings.ocrAiLayoutModel)}
              isReady={modelStatus?.local[settings.ocrAiLayoutModel]?.ready ?? false}
              onDownload={() => startDownload(settings.ocrAiLayoutModel)}
              onCancel={() => cancelDownload(settings.ocrAiLayoutModel)}
              onRefreshStatus={() => void refetchModelStatus()}
            />
          </div>
        </div>
      )}

      {/* Advanced AI OCR options */}
      <CollapsibleSection title="高级选项" defaultOpen={false}>
        <div className="space-y-4">
          {(settings.ocrAiChainMode === "direct" ||
            settings.ocrAiChainMode === "layout_block") && (
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
          )}

          {settings.ocrAiChainMode === "direct" && (
            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiDirectPromptOverride">直出模式提示词覆盖</FieldLabel>
              <PromptTextarea
                id="ocrAiDirectPromptOverride"
                value={settings.ocrAiDirectPromptOverride}
                onChange={(e) => onSettingsChange({ ocrAiDirectPromptOverride: e.target.value })}
                placeholder="留空使用默认提示词"
              />
            </div>
          )}

          {settings.ocrAiChainMode === "layout_block" && (
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
          )}

          {settings.ocrAiChainMode === "layout_block" && (
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
          )}

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

          {settings.ocrAiChainMode === "layout_block" && (
            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiBlockConcurrency">
                块并发度
                <HoverHint text="布局分块模式下同时处理的块数量" />
              </FieldLabel>
              <Input
                id="ocrAiBlockConcurrency"
                type="number"
                min="1"
                max="1000"
                value={settings.ocrAiBlockConcurrency}
                onChange={(e) => onSettingsChange({ ocrAiBlockConcurrency: e.target.value })}
                placeholder="留空自动计算"
              />
            </div>
          )}

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
              onChange={(e) =>
                onSettingsChange({ ocrAiRequestsPerMinute: e.target.value })
              }
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
              onChange={(e) =>
                onSettingsChange({ ocrAiTokensPerMinute: e.target.value })
              }
              placeholder="留空不限制"
            />
          </div>

          {settings.ocrAiChainMode === "doc_parser" && (
            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrPaddleVlDocparserMaxSidePx">
                PaddleOCR-VL 最大边长
                <HoverHint text="文档解析模式下图片最大边长像素" />
              </FieldLabel>
              <Input
                id="ocrPaddleVlDocparserMaxSidePx"
                type="number"
                min="1"
                value={settings.ocrPaddleVlDocparserMaxSidePx}
                onChange={(e) => onSettingsChange({ ocrPaddleVlDocparserMaxSidePx: e.target.value })}
                placeholder="2200"
              />
            </div>
          )}
        </div>
      </CollapsibleSection>
    </div>
  )
}

function BaiduApiConfig({
  settings,
  onSettingsChange,
}: {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}) {
  const [showKeys, setShowKeys] = React.useState(false)

  return (
    <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
      <div className="text-sm font-medium text-muted-foreground">百度 API 设置</div>

      <div className="grid gap-2">
        <FieldLabel htmlFor="baiduDocParseType">
          解析类型
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

      <div className="grid gap-2">
        <FieldLabel htmlFor="ocrBaiduAppId" required>
          App ID
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
          API Key
        </FieldLabel>
        <SensitiveInput
          id="ocrBaiduApiKey"
          value={settings.ocrBaiduApiKey}
          onChange={(e) => onSettingsChange({ ocrBaiduApiKey: e.target.value })}
          placeholder="输入 API Key"
          show={showKeys}
          onToggleShow={() => setShowKeys(!showKeys)}
        />
      </div>

      <div className="grid gap-2">
        <FieldLabel htmlFor="ocrBaiduSecretKey" required>
          <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
          Secret Key
        </FieldLabel>
        <SensitiveInput
          id="ocrBaiduSecretKey"
          value={settings.ocrBaiduSecretKey}
          onChange={(e) => onSettingsChange({ ocrBaiduSecretKey: e.target.value })}
          placeholder="输入 Secret Key"
          show={showKeys}
          onToggleShow={() => setShowKeys(!showKeys)}
        />
      </div>
    </div>
  )
}

function MineruApiConfig({
  settings,
  onSettingsChange,
}: {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}) {
  const [showToken, setShowToken] = React.useState(false)

  return (
    <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
      <div className="text-sm font-medium text-muted-foreground">MinerU API 设置</div>

      <div className="grid gap-2">
        <FieldLabel htmlFor="mineruApiToken" required>
          <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
          API Token
        </FieldLabel>
        <SensitiveInput
          id="mineruApiToken"
          value={settings.mineruApiToken}
          onChange={(e) => onSettingsChange({ mineruApiToken: e.target.value })}
          placeholder="输入 MinerU API Token"
          show={showToken}
          onToggleShow={() => setShowToken(!showToken)}
        />
      </div>

      <CollapsibleSection title="MinerU 高级选项" defaultOpen={false}>
        <div className="space-y-4">
          <div className="grid gap-2">
            <FieldLabel htmlFor="mineruBaseUrl">Base URL</FieldLabel>
            <Input
              id="mineruBaseUrl"
              value={settings.mineruBaseUrl}
              onChange={(e) => onSettingsChange({ mineruBaseUrl: e.target.value })}
              placeholder="https://api.mineru.com"
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="mineruModelVersion">模型版本</FieldLabel>
            <Select
              id="mineruModelVersion"
              value={settings.mineruModelVersion}
              onChange={(e) =>
                onSettingsChange({
                  mineruModelVersion: e.target.value as MineruModelVersion,
                })
              }
              options={MINERU_MODEL_OPTIONS}
            />
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="mineruEnableFormula"
              checked={settings.mineruEnableFormula}
              onCheckedChange={(checked) =>
                onSettingsChange({ mineruEnableFormula: checked as boolean })
              }
            />
            <FieldLabel htmlFor="mineruEnableFormula" className="mb-0">
              启用公式识别
            </FieldLabel>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="mineruEnableTable"
              checked={settings.mineruEnableTable}
              onCheckedChange={(checked) =>
                onSettingsChange({ mineruEnableTable: checked as boolean })
              }
            />
            <FieldLabel htmlFor="mineruEnableTable" className="mb-0">
              启用表格识别
            </FieldLabel>
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="mineruLanguage">语言</FieldLabel>
            <Input
              id="mineruLanguage"
              value={settings.mineruLanguage}
              onChange={(e) => onSettingsChange({ mineruLanguage: e.target.value })}
              placeholder="留空自动检测"
            />
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="mineruIsOcr"
              checked={settings.mineruIsOcr}
              onCheckedChange={(checked) =>
                onSettingsChange({ mineruIsOcr: checked as boolean })
              }
            />
            <FieldLabel htmlFor="mineruIsOcr" className="mb-0">
              OCR 模式
            </FieldLabel>
          </div>
        </div>
      </CollapsibleSection>
    </div>
  )
}

// ============================================================================
// Local OCR settings
// ============================================================================

function LocalOcrSettings({
  settings,
  onSettingsChange,
}: {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}) {
  const { data: modelStatus, refetch: refetchModelStatus } = useModelStatus()
  const { startDownload, cancelDownload, getDownloadState } = useModelDownload({
    onDownloadComplete: () => void refetchModelStatus(),
  })

  return (
    <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
      <div className="text-sm font-medium text-muted-foreground">本地识别参数</div>

      {/* PaddleOCR Download */}
      {(settings.ocrProvider === "paddleocr" || settings.ocrProvider === "auto") && (
        <div className="rounded-lg border bg-background p-3">
          <FieldLabel className="mb-2">PaddleOCR 模型下载</FieldLabel>
          <DownloadProgressButton
            modelId="paddleocr"
            label="PaddleOCR"
            downloadState={getDownloadState("paddleocr")}
            isReady={modelStatus?.local.paddleocr?.ready ?? false}
            onDownload={() => startDownload("paddleocr")}
            onCancel={() => cancelDownload("paddleocr")}
            onRefreshStatus={() => void refetchModelStatus()}
          />
        </div>
      )}

      <div className="grid gap-2">
        <FieldLabel htmlFor="ocrRenderDpi">
          OCR 渲染 DPI
          <HoverHint text="72-400，更高 DPI 提升识别精度但增加处理时间" />
        </FieldLabel>
        <Input
          id="ocrRenderDpi"
          type="number"
          min="72"
          max="400"
          value={settings.ocrRenderDpi}
          onChange={(e) => onSettingsChange({ ocrRenderDpi: e.target.value })}
        />
      </div>

      <div className="flex items-center space-x-2">
        <Checkbox
          id="ocrStrictMode"
          checked={settings.ocrStrictMode}
          onCheckedChange={(checked) =>
            onSettingsChange({ ocrStrictMode: checked as boolean })
          }
        />
        <FieldLabel htmlFor="ocrStrictMode" className="mb-0">
          OCR 严格模式
          <HoverHint text="开启后 OCR 失败会报错，关闭后会静默降级" />
        </FieldLabel>
      </div>

      <div className="flex items-center space-x-2">
        <Checkbox
          id="enableOcr"
          checked={settings.enableOcr}
          onCheckedChange={(checked) =>
            onSettingsChange({ enableOcr: checked as boolean })
          }
        />
        <FieldLabel htmlFor="enableOcr" className="mb-0">
          启用 OCR
          <HoverHint text="关闭后将跳过 OCR 处理" />
        </FieldLabel>
      </div>

      {/* Tesseract Advanced */}
      {settings.ocrProvider === "tesseract" && (
        <CollapsibleSection title="Tesseract 高级设置" defaultOpen={false}>
          <div className="space-y-4">
            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrTesseractLanguage">
                语言
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
  )
}

// ============================================================================
// Main component
// ============================================================================

type RecognitionMethodSectionProps = {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}

export function RecognitionMethodSection({
  settings,
  onSettingsChange,
}: RecognitionMethodSectionProps) {
  const currentId = getRecognitionId(settings)

  const handleSelect = (id: string) => {
    const updates = applyRecognitionId(id, settings)
    onSettingsChange(updates)
  }

  // Group options by group
  const grouped = RECOGNITION_OPTIONS.reduce(
    (acc, opt) => {
      if (!acc[opt.group]) acc[opt.group] = []
      acc[opt.group].push(opt)
      return acc
    },
    {} as Record<string, RecognitionOption[]>
  )

  const initialGroup =
    RECOGNITION_OPTIONS.find((o) => o.id === currentId)?.group ?? null
  const [expandedGroup, setExpandedGroup] = React.useState<string | null>(initialGroup)

  React.useEffect(() => {
    const group = RECOGNITION_OPTIONS.find((o) => o.id === currentId)?.group
    if (group) setExpandedGroup(group)
  }, [currentId])

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">识别方式</h3>
        <p className="text-sm text-muted-foreground">
          选择文档识别方法，不同方式对精度和速度有不同影响
        </p>
      </div>

      {/* Recognition method selection */}
      <div className="space-y-4">
        {Object.entries(grouped).map(([group, options]) => {
          const isExpanded = expandedGroup === group
          const selectedInGroup = options.find((o) => o.id === currentId)

          return (
            <div key={group}>
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-lg border px-4 py-3 text-left transition-colors hover:bg-muted/50"
                onClick={() => setExpandedGroup(isExpanded ? null : group)}
              >
                <span className="text-sm font-medium">
                  {GROUP_LABELS[group]}
                  {!isExpanded && selectedInGroup && (
                    <span className="ml-1 text-muted-foreground">
                      · {selectedInGroup.label}
                    </span>
                  )}
                </span>
                <ChevronDownIcon
                  className={cn(
                    "size-4 text-muted-foreground transition-transform duration-200",
                    isExpanded && "rotate-180"
                  )}
                />
              </button>
              <AdvancedReveal show={isExpanded}>
                <div className="space-y-2 pt-2">
                  {options.map((option) => (
                    <label
                      key={option.id}
                      className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-all ${
                        currentId === option.id
                          ? "border-primary bg-primary/5"
                          : "hover:border-muted-foreground/50"
                      }`}
                    >
                      <input
                        type="radio"
                        name="recognitionMethod"
                        value={option.id}
                        checked={currentId === option.id}
                        onChange={() => handleSelect(option.id)}
                        className="mt-1"
                      />
                      <div className="flex-1">
                        <div className="font-medium">{option.label}</div>
                        <div className="text-sm text-muted-foreground">
                          {option.description}
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              </AdvancedReveal>
            </div>
          )
        })}
      </div>

      {/* API config - only shown when needed */}
      {currentId.startsWith("ai_") && (
        <AiOcrApiConfig settings={settings} onSettingsChange={onSettingsChange} />
      )}

      {currentId === "baidu" && (
        <BaiduApiConfig settings={settings} onSettingsChange={onSettingsChange} />
      )}

      {currentId === "mineru" && (
        <MineruApiConfig settings={settings} onSettingsChange={onSettingsChange} />
      )}

      {/* Local OCR settings */}
      {currentId.startsWith("local_") && (
        <LocalOcrSettings settings={settings} onSettingsChange={onSettingsChange} />
      )}
    </div>
  )
}
