"use client"

import * as React from "react"
import { KeyRoundIcon } from "lucide-react"

import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { HoverHint } from "@/components/ui/hover-hint"
import { Checkbox } from "@/components/ui/checkbox"

import type { Settings, ParseEngineMode, MineruModelVersion } from "@/lib/settings"
import { PARSE_ENGINE_MODE_LABELS } from "@/lib/run-config"
import {
  FieldLabel,
  SensitiveInput,
  CollapsibleSection,
} from "@/components/settings/settings-shared"

const PARSE_ENGINE_OPTIONS: Array<{ id: ParseEngineMode; label: string; description: string }> = [
  {
    id: "local_ocr",
    label: "本地解析",
    description: "快速，支持扫描件，无需API",
  },
  {
    id: "remote_ocr",
    label: "云端解析",
    description: "高精度AI识别，需要API密钥",
  },
  {
    id: "baidu_doc",
    label: "百度文档解析",
    description: "百度专用接口，需要百度账号",
  },
  {
    id: "mineru_cloud",
    label: "MinerU云端",
    description: "结构化文档解析，需要MinerU账号",
  },
]

const MINERU_MODEL_OPTIONS: Array<{ id: MineruModelVersion; label: string }> = [
  { id: "pipeline", label: "Pipeline" },
  { id: "vlm", label: "VLM" },
  { id: "MinerU-HTML", label: "MinerU-HTML" },
]

type ParsingMethodSectionProps = {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}

export function ParsingMethodSection({
  settings,
  onSettingsChange,
}: ParsingMethodSectionProps) {
  const [showMineruToken, setShowMineruToken] = React.useState(false)

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">1. 文档解析方式</h3>
        <p className="text-sm text-muted-foreground">选择PDF文档的解析方法</p>
      </div>

      <div className="space-y-3">
        {PARSE_ENGINE_OPTIONS.map((option) => (
          <label
            key={option.id}
            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-all ${
              settings.parseEngineMode === option.id
                ? "border-primary bg-primary/5"
                : "hover:border-muted-foreground/50"
            }`}
          >
            <input
              type="radio"
              name="parseEngineMode"
              value={option.id}
              checked={settings.parseEngineMode === option.id}
              onChange={(e) =>
                onSettingsChange({ parseEngineMode: e.target.value as ParseEngineMode })
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

      {/* Advanced options based on selected mode */}
      {settings.parseEngineMode === "local_ocr" && (
        <CollapsibleSection title="本地解析高级选项" defaultOpen={false}>
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
          </div>
        </CollapsibleSection>
      )}

      {settings.parseEngineMode === "mineru_cloud" && (
        <>
          <div className="grid gap-2">
            <FieldLabel htmlFor="mineruApiToken" required>
              <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
              MinerU API Token
            </FieldLabel>
            <SensitiveInput
              id="mineruApiToken"
              value={settings.mineruApiToken}
              onChange={(e) => onSettingsChange({ mineruApiToken: e.target.value })}
              placeholder="输入 MinerU API Token"
              show={showMineruToken}
              onToggleShow={() => setShowMineruToken(!showMineruToken)}
            />
          </div>

          <CollapsibleSection title="MinerU 高级选项" defaultOpen={false}>
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
                <FieldLabel htmlFor="mineruLanguage">MinerU 语言</FieldLabel>
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
                  MinerU OCR 模式
                </FieldLabel>
              </div>

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
          </CollapsibleSection>
        </>
      )}
    </div>
  )
}
