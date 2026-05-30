"use client"

import * as React from "react"
import { KeyRoundIcon, RefreshCwIcon, SearchIcon } from "lucide-react"

import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { HoverHint } from "@/components/ui/hover-hint"
import { Checkbox } from "@/components/ui/checkbox"

import type { Settings } from "@/lib/settings"
import {
  type OcrConfigV3,
  type DocumentParsingProvider,
  type TextRecognitionProvider,
  migrateSettingsToOcrConfigV3,
  applyOcrConfigV3ToSettings,
  getParsingProviderLabel,
  getParsingProviderDescription,
  getRecognitionProviderLabel,
  getRecognitionProviderDescription,
  requiresApiKey,
  requiresParsingApiKey,
  supportsBlockConcurrency,
} from "@/lib/ocr-config-v3"
import { LAYOUT_MODELS } from "@/lib/layout-models"
import {
  FieldLabel,
  SensitiveInput,
  CollapsibleSection,
} from "@/components/settings/settings-shared"
import { useModelDownload } from "@/hooks/use-model-download"
import { useModelStatus } from "@/hooks/use-model-status"
import { DownloadProgressButton } from "@/components/download-progress-button"
import { fetchModels } from "@/lib/api"
import { toast } from "sonner"

const LAYOUT_MODEL_OPTIONS = Object.values(LAYOUT_MODELS).map((m) => ({
  id: m.modelId as OcrConfigV3["layout"]["model"],
  label: m.displayName,
  sizeMb: m.sizeMb,
}))

const AI_PROVIDER_OPTIONS = [
  { id: "auto", label: "自动识别（推荐）" },
  { id: "openai", label: "OpenAI" },
  { id: "siliconflow", label: "SiliconFlow" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "ppio", label: "PPIO" },
  { id: "novita", label: "Novita" },
]

type OcrConfigV3SectionProps = {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}

export function OcrConfigV3Section({ settings, onSettingsChange }: OcrConfigV3SectionProps) {
  // Convert current settings to V3 config
  const config = React.useMemo(() => migrateSettingsToOcrConfigV3(settings), [settings])

  const { data: modelStatus, refetch: refetchModelStatus } = useModelStatus()
  const { startDownload, cancelDownload, getDownloadState } = useModelDownload({
    onDownloadComplete: () => void refetchModelStatus(),
  })

  const [showApiKey, setShowApiKey] = React.useState(false)
  const [showMineruToken, setShowMineruToken] = React.useState(false)
  const [showBaiduKeys, setShowBaiduKeys] = React.useState(false)
  const [fetchingModels, setFetchingModels] = React.useState(false)
  const [availableModels, setAvailableModels] = React.useState<string[]>([])

  // Update settings when config changes
  const updateConfig = (updates: Partial<OcrConfigV3>) => {
    console.log('[OcrConfigV3] updateConfig called with:', updates)
    const newConfig = {
      ...config,
      ...updates,
      // Deep merge nested objects to preserve existing properties
      parsing: { ...config.parsing, ...(updates.parsing || {}) },
      layout: { ...config.layout, ...(updates.layout || {}) },
      recognition: { ...config.recognition, ...(updates.recognition || {}) },
    }
    console.log('[OcrConfigV3] newConfig:', newConfig)
    const settingsUpdates = applyOcrConfigV3ToSettings(newConfig, settings)
    console.log('[OcrConfigV3] settingsUpdates:', settingsUpdates)
    onSettingsChange(settingsUpdates)
  }

  const handleFetchModels = React.useCallback(async () => {
    if (config.recognition.provider !== "aiocr") return
    if (!config.recognition.apiKey) {
      toast.error("请先填写 API Key")
      return
    }
    setFetchingModels(true)
    setAvailableModels([])
    try {
      const models = await fetchModels({
        provider: config.recognition.aiProvider || "auto",
        apiKey: config.recognition.apiKey || "",
        baseUrl: config.recognition.baseUrl || undefined,
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
  }, [config.recognition])

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold">OCR 配置（三层架构）</h3>
        <p className="text-sm text-muted-foreground">
          配置文档解析、版面检测和文字识别，三层独立处理
        </p>
      </div>

      {/* ================================================================ */}
      {/* Layer 1: Document Parsing (Optional) */}
      {/* ================================================================ */}
      <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
        <div>
          <div className="text-sm font-medium">第一层：文档解析（可选）</div>
          <p className="text-xs text-muted-foreground">
            选择文档解析方式，用于处理复杂文档（公式、表格等）
          </p>
        </div>

        {/* Parsing provider selection */}
        <div className="space-y-3">
          {(["local", "mineru", "baidu_doc"] as DocumentParsingProvider[]).map(
            (provider) => (
              <label
                key={provider}
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-all ${
                  config.parsing.provider === provider
                    ? "border-primary bg-primary/5"
                    : "hover:border-muted-foreground/50"
                }`}
              >
                <input
                  type="radio"
                  name="parsingProvider"
                  value={provider}
                  checked={config.parsing.provider === provider}
                  onChange={() => {
                    if (provider === "local") {
                      updateConfig({ parsing: { provider: "local" } })
                    } else if (provider === "mineru") {
                      updateConfig({
                        parsing: {
                          provider: "mineru",
                          mineruApiToken: "",
                          mineruBaseUrl: "https://api.mineru.ai",
                          mineruModelVersion: "vlm",
                          enableFormula: true,
                          enableTable: true,
                        },
                      })
                    } else if (provider === "baidu_doc") {
                      updateConfig({
                        parsing: {
                          provider: "baidu_doc",
                          baiduDocParseType: "paddle_vl",
                        },
                      })
                    }
                  }}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="font-medium">{getParsingProviderLabel(provider)}</div>
                  <div className="text-sm text-muted-foreground">
                    {getParsingProviderDescription(provider)}
                  </div>
                </div>
              </label>
            )
          )}
        </div>

        {/* MinerU settings */}
        {config.parsing.provider === "mineru" && (
          <div className="space-y-4 rounded-lg border bg-background p-3">
            <div className="grid gap-2">
              <FieldLabel htmlFor="mineruApiToken" required>
                <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
                MinerU API Token
              </FieldLabel>
              <SensitiveInput
                id="mineruApiToken"
                value={config.parsing.mineruApiToken || ""}
                onChange={(e) =>
                  updateConfig({
                    parsing: { ...config.parsing, mineruApiToken: e.target.value },
                  })
                }
                placeholder="输入 MinerU API Token"
                show={showMineruToken}
                onToggleShow={() => setShowMineruToken(!showMineruToken)}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="mineruBaseUrl">
                Base URL
                <HoverHint text="MinerU API 端点" />
              </FieldLabel>
              <Input
                id="mineruBaseUrl"
                value={config.parsing.mineruBaseUrl || ""}
                onChange={(e) =>
                  updateConfig({
                    parsing: { ...config.parsing, mineruBaseUrl: e.target.value },
                  })
                }
                placeholder="https://api.mineru.ai"
              />
            </div>

            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="enableFormula"
                  checked={config.parsing.enableFormula ?? true}
                  onCheckedChange={(checked) =>
                    updateConfig({
                      parsing: { ...config.parsing, enableFormula: checked as boolean },
                    })
                  }
                />
                <FieldLabel htmlFor="enableFormula" className="mb-0">
                  启用公式识别
                </FieldLabel>
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox
                  id="enableTable"
                  checked={config.parsing.enableTable ?? true}
                  onCheckedChange={(checked) =>
                    updateConfig({
                      parsing: { ...config.parsing, enableTable: checked as boolean },
                    })
                  }
                />
                <FieldLabel htmlFor="enableTable" className="mb-0">
                  启用表格识别
                </FieldLabel>
              </div>
            </div>
          </div>
        )}

        {/* Baidu Doc settings */}
        {config.parsing.provider === "baidu_doc" && (
          <div className="space-y-4 rounded-lg border bg-background p-3">
            <div className="grid gap-2">
              <FieldLabel htmlFor="baiduDocParseType">
                解析类型
                <HoverHint text="选择百度文档解析的模式" />
              </FieldLabel>
              <Select
                id="baiduDocParseType"
                value={config.parsing.baiduDocParseType || "paddle_vl"}
                onChange={(e) =>
                  updateConfig({
                    parsing: {
                      ...config.parsing,
                      baiduDocParseType: e.target.value as "general" | "paddle_vl",
                    },
                  })
                }
                options={[
                  { id: "general", label: "通用解析" },
                  { id: "paddle_vl", label: "PaddleVL 解析（推荐）" },
                ]}
              />
            </div>
          </div>
        )}
      </div>

      {/* ================================================================ */}
      {/* Layer 2: Layout Detection (Optional) */}
      {/* ================================================================ */}
      <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">第二层：版面检测（可选）</div>
            <p className="text-xs text-muted-foreground">
              先检测页面中的文本块、图像块、表格等区域
            </p>
          </div>
          <Checkbox
            id="layoutEnabled"
            checked={config.layout.enabled}
            onCheckedChange={(checked) =>
              updateConfig({
                layout: { ...config.layout, enabled: checked as boolean },
              })
            }
          />
        </div>

        {config.layout.enabled && (
          <div className="space-y-4 pt-2">
            <div className="grid gap-2">
              <FieldLabel htmlFor="layoutModel">
                版面检测模型
                <HoverHint text="选择用于版面分析的模型" />
              </FieldLabel>
              <Select
                id="layoutModel"
                value={config.layout.model}
                onChange={(e) =>
                  updateConfig({
                    layout: {
                      ...config.layout,
                      model: e.target.value as OcrConfigV3["layout"]["model"],
                    },
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
                  modelId={config.layout.model}
                  label={
                    LAYOUT_MODEL_OPTIONS.find((m) => m.id === config.layout.model)?.label ||
                    config.layout.model
                  }
                  downloadState={getDownloadState(config.layout.model)}
                  isReady={modelStatus?.local[config.layout.model]?.ready ?? false}
                  onDownload={() => startDownload(config.layout.model)}
                  onCancel={() => cancelDownload(config.layout.model)}
                  onRefreshStatus={() => void refetchModelStatus()}
                />
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="enableSam"
                checked={config.layout.enableSam}
                onCheckedChange={(checked) =>
                  updateConfig({
                    layout: { ...config.layout, enableSam: checked as boolean },
                  })
                }
              />
              <FieldLabel htmlFor="enableSam" className="mb-0">
                启用 SAM 多边形细化
                <HoverHint text="使用 MobileSAM 将图像区域的矩形框细化为精确多边形（仅对图像块生效）" />
              </FieldLabel>
            </div>
          </div>
        )}
      </div>

      {/* ================================================================ */}
      {/* Layer 3: Text Recognition (Required) */}
      {/* ================================================================ */}
      <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
        <div>
          <div className="text-sm font-medium">第三层：文字识别（必选）</div>
          <p className="text-xs text-muted-foreground">
            选择识别引擎，对{config.layout.enabled ? "每个文本块" : "整页"}进行文字识别
          </p>
        </div>

        {/* Recognition provider selection */}
        <div className="space-y-3">
          {(["paddleocr", "tesseract", "aiocr", "baidu"] as TextRecognitionProvider[]).map(
            (provider) => (
              <label
                key={provider}
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-all ${
                  config.recognition.provider === provider
                    ? "border-primary bg-primary/5"
                    : "hover:border-muted-foreground/50"
                }`}
              >
                <input
                  type="radio"
                  name="recognitionProvider"
                  value={provider}
                  checked={config.recognition.provider === provider}
                  onChange={() => {
                    if (provider === "paddleocr") {
                      updateConfig({ recognition: { provider: "paddleocr" } })
                    } else if (provider === "tesseract") {
                      updateConfig({
                        recognition: {
                          provider: "tesseract",
                          language: "chi_sim+eng",
                          minConfidence: 35,
                        },
                      })
                    } else if (provider === "aiocr") {
                      updateConfig({
                        recognition: {
                          provider: "aiocr",
                          aiProvider: "siliconflow",
                          apiKey: "",
                          baseUrl: "https://api.siliconflow.cn/v1",
                          pageConcurrency: 1,
                          maxRetries: 0,
                        },
                      })
                    } else if (provider === "baidu") {
                      updateConfig({
                        recognition: {
                          provider: "baidu",
                          baiduAppId: "",
                          baiduApiKey: "",
                          baiduSecretKey: "",
                        },
                      })
                    }
                  }}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="font-medium">{getRecognitionProviderLabel(provider)}</div>
                  <div className="text-sm text-muted-foreground">
                    {getRecognitionProviderDescription(provider)}
                  </div>
                </div>
              </label>
            )
          )}
        </div>

        {/* Provider-specific settings */}
        {config.recognition.provider === "paddleocr" && (
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

        {config.recognition.provider === "tesseract" && (
          <CollapsibleSection title="Tesseract 设置" defaultOpen={true}>
            <div className="space-y-4">
              <div className="grid gap-2">
                <FieldLabel htmlFor="tesseractLanguage">
                  语言
                  <HoverHint text="多语言用 + 连接，如 chi_sim+eng" />
                </FieldLabel>
                <Input
                  id="tesseractLanguage"
                  value={config.recognition.language || "chi_sim+eng"}
                  onChange={(e) =>
                    updateConfig({
                      recognition: { ...config.recognition, language: e.target.value },
                    })
                  }
                  placeholder="chi_sim+eng"
                />
              </div>

              <div className="grid gap-2">
                <FieldLabel htmlFor="tesseractMinConfidence">
                  最低置信度
                  <HoverHint text="0-100，较低值提高召回率" />
                </FieldLabel>
                <Input
                  id="tesseractMinConfidence"
                  type="number"
                  min="0"
                  max="100"
                  value={config.recognition.minConfidence ?? 35}
                  onChange={(e) =>
                    updateConfig({
                      recognition: {
                        ...config.recognition,
                        minConfidence: parseInt(e.target.value) || 35,
                      },
                    })
                  }
                />
              </div>
            </div>
          </CollapsibleSection>
        )}

        {config.recognition.provider === "baidu" && (
          <div className="space-y-4 rounded-lg border bg-background p-3">
            <div className="grid gap-2">
              <FieldLabel htmlFor="baiduAppId" required>
                <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
                百度 OCR App ID
              </FieldLabel>
              <SensitiveInput
                id="baiduAppId"
                value={config.recognition.baiduAppId || ""}
                onChange={(e) =>
                  updateConfig({
                    recognition: { ...config.recognition, baiduAppId: e.target.value },
                  })
                }
                placeholder="输入 App ID"
                show={showBaiduKeys}
                onToggleShow={() => setShowBaiduKeys(!showBaiduKeys)}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="baiduApiKey" required>
                <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
                百度 OCR API Key
              </FieldLabel>
              <SensitiveInput
                id="baiduApiKey"
                value={config.recognition.baiduApiKey || ""}
                onChange={(e) =>
                  updateConfig({
                    recognition: { ...config.recognition, baiduApiKey: e.target.value },
                  })
                }
                placeholder="输入 API Key"
                show={showBaiduKeys}
                onToggleShow={() => setShowBaiduKeys(!showBaiduKeys)}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="baiduSecretKey" required>
                <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
                百度 OCR Secret Key
              </FieldLabel>
              <SensitiveInput
                id="baiduSecretKey"
                value={config.recognition.baiduSecretKey || ""}
                onChange={(e) =>
                  updateConfig({
                    recognition: { ...config.recognition, baiduSecretKey: e.target.value },
                  })
                }
                placeholder="输入 Secret Key"
                show={showBaiduKeys}
                onToggleShow={() => setShowBaiduKeys(!showBaiduKeys)}
              />
            </div>
          </div>
        )}

        {config.recognition.provider === "aiocr" && (
          <div className="space-y-4">
            <div className="grid gap-2">
              <FieldLabel htmlFor="aiProvider">
                AI 提供方
                <HoverHint text="选择 AI OCR 服务提供商" />
              </FieldLabel>
              <Select
                id="aiProvider"
                value={config.recognition.aiProvider || "auto"}
                onChange={(e) =>
                  updateConfig({
                    recognition: { ...config.recognition, aiProvider: e.target.value },
                  })
                }
                options={AI_PROVIDER_OPTIONS}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="aiApiKey" required>
                <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
                API Key
              </FieldLabel>
              <SensitiveInput
                id="aiApiKey"
                value={config.recognition.apiKey || ""}
                onChange={(e) =>
                  updateConfig({
                    recognition: { ...config.recognition, apiKey: e.target.value },
                  })
                }
                placeholder="输入 API Key"
                show={showApiKey}
                onToggleShow={() => setShowApiKey(!showApiKey)}
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="aiBaseUrl">
                Base URL
                <HoverHint text="自定义 API 端点（可选）" />
              </FieldLabel>
              <Input
                id="aiBaseUrl"
                value={config.recognition.baseUrl || ""}
                onChange={(e) =>
                  updateConfig({
                    recognition: { ...config.recognition, baseUrl: e.target.value },
                  })
                }
                placeholder="https://api.example.com/v1"
              />
            </div>

            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <FieldLabel htmlFor="aiModel" className="mb-0">
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
                  id="aiModel"
                  value={config.recognition.model || ""}
                  onChange={(e) =>
                    updateConfig({
                      recognition: { ...config.recognition, model: e.target.value },
                    })
                  }
                  options={[
                    { id: "", label: "留空使用默认" },
                    ...availableModels.map((m) => ({ id: m, label: m })),
                  ]}
                />
              ) : (
                <Input
                  id="aiModel"
                  value={config.recognition.model || ""}
                  onChange={(e) =>
                    updateConfig({
                      recognition: { ...config.recognition, model: e.target.value },
                    })
                  }
                  placeholder="留空使用默认"
                />
              )}
            </div>

            <CollapsibleSection title="高级选项" defaultOpen={false}>
              <div className="space-y-4">
                <div className="grid gap-2">
                  <FieldLabel htmlFor="pageConcurrency">
                    页面并发度
                    <HoverHint text="同时处理的页面数量" />
                  </FieldLabel>
                  <Input
                    id="pageConcurrency"
                    type="number"
                    min="1"
                    max="1000"
                    value={config.recognition.pageConcurrency ?? 1}
                    onChange={(e) =>
                      updateConfig({
                        recognition: {
                          ...config.recognition,
                          pageConcurrency: parseInt(e.target.value) || 1,
                        },
                      })
                    }
                  />
                </div>

                {supportsBlockConcurrency(config) && (
                  <div className="grid gap-2">
                    <FieldLabel htmlFor="blockConcurrency">
                      块并发度
                      <HoverHint text="版面检测模式下同时处理的块数量" />
                    </FieldLabel>
                    <Input
                      id="blockConcurrency"
                      type="number"
                      min="1"
                      max="1000"
                      value={config.recognition.blockConcurrency ?? ""}
                      onChange={(e) =>
                        updateConfig({
                          recognition: {
                            ...config.recognition,
                            blockConcurrency: e.target.value
                              ? parseInt(e.target.value)
                              : undefined,
                          },
                        })
                      }
                      placeholder="留空自动计算"
                    />
                  </div>
                )}

                <div className="grid gap-2">
                  <FieldLabel htmlFor="maxRetries">
                    最大重试次数
                    <HoverHint text="API 请求失败后的重试次数" />
                  </FieldLabel>
                  <Input
                    id="maxRetries"
                    type="number"
                    min="0"
                    max="1000"
                    value={config.recognition.maxRetries ?? 0}
                    onChange={(e) =>
                      updateConfig({
                        recognition: {
                          ...config.recognition,
                          maxRetries: parseInt(e.target.value) || 0,
                        },
                      })
                    }
                  />
                </div>

                <div className="grid gap-2">
                  <FieldLabel htmlFor="requestsPerMinute">
                    每分钟请求数限制（可选）
                    <HoverHint text="API 速率限制，留空不限制" />
                  </FieldLabel>
                  <Input
                    id="requestsPerMinute"
                    type="number"
                    min="1"
                    value={config.recognition.requestsPerMinute ?? ""}
                    onChange={(e) =>
                      updateConfig({
                        recognition: {
                          ...config.recognition,
                          requestsPerMinute: e.target.value
                            ? parseInt(e.target.value)
                            : undefined,
                        },
                      })
                    }
                    placeholder="留空不限制"
                  />
                </div>

                <div className="grid gap-2">
                  <FieldLabel htmlFor="tokensPerMinute">
                    每分钟 Token 数限制（可选）
                    <HoverHint text="API Token 速率限制，留空不限制" />
                  </FieldLabel>
                  <Input
                    id="tokensPerMinute"
                    type="number"
                    min="1"
                    value={config.recognition.tokensPerMinute ?? ""}
                    onChange={(e) =>
                      updateConfig({
                        recognition: {
                          ...config.recognition,
                          tokensPerMinute: e.target.value
                            ? parseInt(e.target.value)
                            : undefined,
                        },
                      })
                    }
                    placeholder="留空不限制"
                  />
                </div>
              </div>
            </CollapsibleSection>
          </div>
        )}
      </div>

      {/* ================================================================ */}
      {/* Common Settings */}
      {/* ================================================================ */}
      <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
        <div className="text-sm font-medium">通用设置</div>

        <div className="grid gap-2">
          <FieldLabel htmlFor="renderDpi">
            OCR 渲染 DPI
            <HoverHint text="72-400，更高 DPI 提升识别精度但增加处理时间" />
          </FieldLabel>
          <Input
            id="renderDpi"
            type="number"
            min="72"
            max="400"
            value={config.renderDpi}
            onChange={(e) =>
              updateConfig({ renderDpi: parseInt(e.target.value) || 200 })
            }
          />
        </div>

        <div className="flex items-center space-x-2">
          <Checkbox
            id="strictMode"
            checked={config.strictMode}
            onCheckedChange={(checked) =>
              updateConfig({ strictMode: checked as boolean })
            }
          />
          <FieldLabel htmlFor="strictMode" className="mb-0">
            OCR 严格模式
            <HoverHint text="开启后 OCR 失败会报错，关闭后会静默降级" />
          </FieldLabel>
        </div>
      </div>

      {/* Architecture explanation */}
      <div className="rounded-lg bg-amber-50 dark:bg-amber-950/30 p-4 text-sm text-amber-900 dark:text-amber-100">
        <div className="font-medium mb-2">三层架构说明</div>
        <ul className="space-y-1 text-xs list-disc list-inside">
          <li>
            <strong>第一层：文档解析</strong> — 可选，用于处理复杂文档（MinerU、百度文档解析）
          </li>
          <li>
            <strong>第二层：版面检测</strong> — 可选，将页面切分为文本块、图像块、表格等区域
          </li>
          <li>
            <strong>第三层：文字识别</strong> — 必选，对文本区域进行 OCR 识别
          </li>
          <li>
            <strong>PaddleOCR</strong> 内部总是使用版面检测（无法关闭）
          </li>
          <li>
            <strong>百度 OCR</strong> 支持远程识别，速度快且稳定
          </li>
          <li>
            <strong>SAM 细化</strong>仅对图像块生效，不影响文本块
          </li>
        </ul>
      </div>
    </div>
  )
}
