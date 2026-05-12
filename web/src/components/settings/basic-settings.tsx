"use client"

import * as React from "react"
import { KeyRoundIcon } from "lucide-react"
import { toast } from "sonner"

import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { HoverHint } from "@/components/ui/hover-hint"

import type { Settings, ParseEngineMode, Provider, MainProvider } from "@/lib/settings"
import { PARSE_ENGINE_MODE_LABELS } from "@/lib/run-config"
import { PPT_GENERATION_MODE_LABELS } from "@/lib/settings"
import {
  FieldLabel,
  SensitiveInput,
} from "@/components/settings/settings-shared"

const PARSE_ENGINE_OPTIONS: Array<{ id: ParseEngineMode; label: string }> = [
  { id: "local_ocr", label: PARSE_ENGINE_MODE_LABELS.local_ocr },
  { id: "remote_ocr", label: PARSE_ENGINE_MODE_LABELS.remote_ocr },
  { id: "baidu_doc", label: PARSE_ENGINE_MODE_LABELS.baidu_doc },
  { id: "mineru_cloud", label: PARSE_ENGINE_MODE_LABELS.mineru_cloud },
]

const PROVIDER_OPTIONS: Array<{ id: Provider; label: string }> = [
  { id: "openai", label: "OpenAI" },
  { id: "claude", label: "Claude" },
  { id: "mineru", label: "MinerU" },
]

const PPT_MODE_OPTIONS = Object.entries(PPT_GENERATION_MODE_LABELS).map(([id, label]) => ({
  id: id as Settings["pptGenerationMode"],
  label,
}))

type BasicSettingsProps = {
  settings: Settings
  onSettingsChange: (updates: Partial<Settings>) => void
}

export function BasicSettings({ settings, onSettingsChange }: BasicSettingsProps) {
  const [showOpenAIKey, setShowOpenAIKey] = React.useState(false)
  const [showClaudeKey, setShowClaudeKey] = React.useState(false)

  const handleParseEngineModeChange = (mode: ParseEngineMode) => {
    const updates: Partial<Settings> = { parseEngineMode: mode }

    // Auto-adjust provider based on parse engine mode
    if (mode === "mineru_cloud") {
      updates.provider = "mineru"
    } else if (settings.provider === "mineru") {
      updates.provider = settings.preferredMainProvider
      updates.preferredMainProvider = settings.preferredMainProvider
    }

    onSettingsChange(updates)
  }

  const validateApiKey = (key: string, provider: string): boolean => {
    if (!key.trim()) return true // Empty is valid (user may not have set it yet)

    // Basic format validation
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

  return (
    <div className="space-y-6">
      {/* Parse Engine Mode */}
      <div className="grid gap-2">
        <FieldLabel htmlFor="parseEngineMode" required>
          解析引擎
          <HoverHint text="选择 PDF 解析方式：传统 OCR（本地）、AIOCR（远程）、百度解析或 MinerU 云端" />
        </FieldLabel>
        <Select
          id="parseEngineMode"
          value={settings.parseEngineMode}
          onChange={(e) => handleParseEngineModeChange(e.target.value as ParseEngineMode)}
          options={PARSE_ENGINE_OPTIONS}
        />
      </div>

      {/* Provider (for non-MinerU modes) */}
      {settings.parseEngineMode !== "mineru_cloud" && (
        <div className="grid gap-2">
          <FieldLabel htmlFor="provider" required>
            PPT 生成提供方
            <HoverHint text="选择用于生成 PPT 的 AI 提供方" />
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
      )}

      {/* OpenAI API Key */}
      {(settings.provider === "openai" || settings.parseEngineMode === "remote_ocr") && (
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

      {/* MinerU API Token */}
      {settings.parseEngineMode === "mineru_cloud" && (
        <div className="grid gap-2">
          <FieldLabel htmlFor="mineruApiToken" required>
            <KeyRoundIcon className="inline-block h-4 w-4 mr-1" />
            MinerU API Token
          </FieldLabel>
          <Input
            id="mineruApiToken"
            type="password"
            value={settings.mineruApiToken}
            onChange={(e) => onSettingsChange({ mineruApiToken: e.target.value })}
            placeholder="输入 MinerU API Token"
          />
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
    </div>
  )
}
