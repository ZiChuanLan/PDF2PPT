"use client"

import * as React from "react"

import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { HoverHint } from "@/components/ui/hover-hint"
import { Checkbox } from "@/components/ui/checkbox"

import type { Settings } from "@/lib/settings"
import {
  FieldLabel,
  CollapsibleSection,
  PromptTextarea,
} from "@/components/settings/settings-shared"

const TEXT_ERASE_MODE_OPTIONS: Array<{ id: Settings["textEraseMode"]; label: string }> = [
  { id: "fill", label: "快速填充" },
  { id: "smart", label: "智能擦除" },
]

const SCANNED_PAGE_MODE_OPTIONS: Array<{
  id: Settings["scannedPageMode"]
  label: string
}> = [
  { id: "segmented", label: "分段模式（图片可编辑）" },
  { id: "fullpage", label: "整页模式（图片作为背景）" },
]

const VISUAL_ASSIST_MODE_OPTIONS: Array<{
  id: Settings["visualAssistModeLocal"]
  label: string
}> = [
  { id: "off", label: "关闭" },
  { id: "on", label: "开启" },
  { id: "auto", label: "自动" },
]

type AdvancedSettingsProps = {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}

export function AdvancedSettings({ settings, onSettingsChange }: AdvancedSettingsProps) {
  return (
    <div className="space-y-6">
      {/* OCR Advanced Settings */}
      <CollapsibleSection title="OCR 高级设置" defaultOpen={false}>
        <div className="space-y-4">
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
              <HoverHint text="开启后 OCR 失败会报错，关闭后会静默降级（不推荐）" />
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
        </div>
      </CollapsibleSection>

      {/* AIOCR Concurrency Settings */}
      {settings.parseEngineMode === "remote_ocr" && (
        <CollapsibleSection title="AIOCR 并发设置" defaultOpen={false}>
          <div className="space-y-4">
            <div className="grid gap-2">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="ocrAiPageConcurrencyAuto"
                  checked={settings.ocrAiPageConcurrencyAuto}
                  onCheckedChange={(checked) =>
                    onSettingsChange({ ocrAiPageConcurrencyAuto: checked as boolean })
                  }
                />
                <FieldLabel htmlFor="ocrAiPageConcurrencyAuto" className="mb-0">
                  自动页面并发度
                  <HoverHint text="自动根据 API 限制调整并发" />
                </FieldLabel>
              </div>
            </div>

            {!settings.ocrAiPageConcurrencyAuto && (
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
                  onChange={(e) =>
                    onSettingsChange({ ocrAiPageConcurrency: e.target.value })
                  }
                />
              </div>
            )}

            <div className="grid gap-2">
              <FieldLabel htmlFor="ocrAiBlockConcurrency">
                块并发度（可选）
                <HoverHint text="留空使用默认值" />
              </FieldLabel>
              <Input
                id="ocrAiBlockConcurrency"
                type="number"
                min="1"
                value={settings.ocrAiBlockConcurrency}
                onChange={(e) => onSettingsChange({ ocrAiBlockConcurrency: e.target.value })}
                placeholder="留空使用默认"
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
                onChange={(e) => onSettingsChange({ ocrAiTokensPerMinute: e.target.value })}
                placeholder="留空不限制"
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
          </div>
        </CollapsibleSection>
      )}

      {/* Layout Assist Settings */}
      <CollapsibleSection title="版面辅助设置" defaultOpen={false}>
        <div className="space-y-4">
          <div className="grid gap-2">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="enableLayoutAssist"
                checked={settings.enableLayoutAssist}
                onCheckedChange={(checked) =>
                  onSettingsChange({ enableLayoutAssist: checked as boolean })
                }
              />
              <FieldLabel htmlFor="enableLayoutAssist" className="mb-0">
                启用版面辅助
                <HoverHint text="使用 AI 辅助版面分析（实验性功能）" />
              </FieldLabel>
            </div>
          </div>

          {settings.enableLayoutAssist && (
            <>
              <div className="grid gap-2">
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

              <div className="grid gap-2">
                <FieldLabel htmlFor="visualAssistModeLocal">
                  传统 OCR 视觉辅助
                </FieldLabel>
                <Select
                  id="visualAssistModeLocal"
                  value={settings.visualAssistModeLocal}
                  onChange={(e) =>
                    onSettingsChange({
                      visualAssistModeLocal: e.target.value as Settings["visualAssistModeLocal"],
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
                      visualAssistModeRemote: e.target
                        .value as Settings["visualAssistModeRemote"],
                    })
                  }
                  options={VISUAL_ASSIST_MODE_OPTIONS}
                />
              </div>

              <div className="grid gap-2">
                <FieldLabel htmlFor="visualAssistModeBaiduDoc">
                  百度解析视觉辅助
                </FieldLabel>
                <Select
                  id="visualAssistModeBaiduDoc"
                  value={settings.visualAssistModeBaiduDoc}
                  onChange={(e) =>
                    onSettingsChange({
                      visualAssistModeBaiduDoc: e.target
                        .value as Settings["visualAssistModeBaiduDoc"],
                    })
                  }
                  options={VISUAL_ASSIST_MODE_OPTIONS}
                />
              </div>

              <div className="grid gap-2">
                <FieldLabel htmlFor="visualAssistModeMineru">
                  MinerU 视觉辅助
                </FieldLabel>
                <Select
                  id="visualAssistModeMineru"
                  value={settings.visualAssistModeMineru}
                  onChange={(e) =>
                    onSettingsChange({
                      visualAssistModeMineru: e.target
                        .value as Settings["visualAssistModeMineru"],
                    })
                  }
                  options={VISUAL_ASSIST_MODE_OPTIONS}
                />
              </div>
            </>
          )}
        </div>
      </CollapsibleSection>

      {/* PPT Generation Advanced */}
      <CollapsibleSection title="PPT 生成高级设置" defaultOpen={false}>
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
              options={TEXT_ERASE_MODE_OPTIONS}
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
              options={SCANNED_PAGE_MODE_OPTIONS}
            />
          </div>

          <div className="grid gap-2">
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
        </div>
      </CollapsibleSection>

      {/* Image Processing Tunables */}
      <CollapsibleSection title="图片处理参数" defaultOpen={false}>
        <div className="space-y-4">
          <div className="grid gap-2">
            <FieldLabel htmlFor="imageBgClearExpandMinPt">
              背景清除最小扩展（pt）
            </FieldLabel>
            <Input
              id="imageBgClearExpandMinPt"
              type="number"
              step="0.01"
              value={settings.imageBgClearExpandMinPt}
              onChange={(e) =>
                onSettingsChange({ imageBgClearExpandMinPt: e.target.value })
              }
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="imageBgClearExpandMaxPt">
              背景清除最大扩展（pt）
            </FieldLabel>
            <Input
              id="imageBgClearExpandMaxPt"
              type="number"
              step="0.01"
              value={settings.imageBgClearExpandMaxPt}
              onChange={(e) =>
                onSettingsChange({ imageBgClearExpandMaxPt: e.target.value })
              }
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="imageBgClearExpandRatio">背景清除扩展比例</FieldLabel>
            <Input
              id="imageBgClearExpandRatio"
              type="number"
              step="0.001"
              value={settings.imageBgClearExpandRatio}
              onChange={(e) =>
                onSettingsChange({ imageBgClearExpandRatio: e.target.value })
              }
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel htmlFor="scannedImageRegionMinAreaRatio">
              图片区域最小面积比
            </FieldLabel>
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
            <FieldLabel htmlFor="scannedImageRegionMaxAreaRatio">
              图片区域最大面积比
            </FieldLabel>
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

      {/* AIOCR Prompt Overrides */}
      {settings.parseEngineMode === "remote_ocr" && (
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
                    ocrAiPromptPreset: e.target.value as Settings["ocrAiPromptPreset"],
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
              <FieldLabel htmlFor="ocrAiDirectPromptOverride">
                直出模式提示词覆盖
              </FieldLabel>
              <PromptTextarea
                id="ocrAiDirectPromptOverride"
                value={settings.ocrAiDirectPromptOverride}
                onChange={(e) =>
                  onSettingsChange({ ocrAiDirectPromptOverride: e.target.value })
                }
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

      {/* MinerU Settings */}
      {settings.parseEngineMode === "mineru_cloud" && (
        <CollapsibleSection title="MinerU 设置" defaultOpen={false}>
          <div className="space-y-4">
            <div className="grid gap-2">
              <FieldLabel htmlFor="mineruBaseUrl">MinerU Base URL</FieldLabel>
              <Input
                id="mineruBaseUrl"
                value={settings.mineruBaseUrl}
                onChange={(e) => onSettingsChange({ mineruBaseUrl: e.target.value })}
                placeholder="https://api.mineru.com"
              />
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="mineruModelVersion">MinerU 模型版本</FieldLabel>
              <Select
                id="mineruModelVersion"
                value={settings.mineruModelVersion}
                onChange={(e) =>
                  onSettingsChange({
                    mineruModelVersion: e.target.value as Settings["mineruModelVersion"],
                  })
                }
                options={[
                  { id: "pipeline", label: "Pipeline" },
                  { id: "vlm", label: "VLM" },
                  { id: "MinerU-HTML", label: "MinerU-HTML" },
                ]}
              />
            </div>

            <div className="grid gap-2">
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
            </div>

            <div className="grid gap-2">
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
            </div>

            <div className="grid gap-2">
              <FieldLabel htmlFor="mineruLanguage">MinerU 语言</FieldLabel>
              <Input
                id="mineruLanguage"
                value={settings.mineruLanguage}
                onChange={(e) => onSettingsChange({ mineruLanguage: e.target.value })}
                placeholder="留空自动检测"
              />
            </div>

            <div className="grid gap-2">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="mineruIsOcr"
                  checked={settings.mineruIsOcr}
                  onCheckedChange={(checked) =>
                    onSettingsChange({ mineruIsOcr: checked as boolean })
                  }
                />
                <FieldLabel htmlFor="mineruIsOcr" className="mb-0">
                  MinerU OCR 模式
                </FieldLabel>
              </div>
            </div>

            <div className="grid gap-2">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="mineruHybridOcr"
                  checked={settings.mineruHybridOcr}
                  onCheckedChange={(checked) =>
                    onSettingsChange({ mineruHybridOcr: checked as boolean })
                  }
                />
                <FieldLabel htmlFor="mineruHybridOcr" className="mb-0">
                  MinerU 混合 OCR
                </FieldLabel>
              </div>
            </div>
          </div>
        </CollapsibleSection>
      )}
    </div>
  )
}
