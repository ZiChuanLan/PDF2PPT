"use client"

import * as React from "react"
import Link from "next/link"
import { ArrowLeftIcon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { useSettings } from "@/hooks/use-settings"

import { QuickPresets } from "@/components/settings/quick-presets"
import { ParsingMethodSection } from "@/components/settings/parsing-method-section"
import { OcrStrategySection } from "@/components/settings/ocr-strategy-section"
import { OutputQualitySection } from "@/components/settings/output-quality-section"
import { GeneralAdvancedSection } from "@/components/settings/general-advanced-section"
import { AdminSettings } from "@/components/settings/admin-settings"

export default function SettingsPage() {
  const {
    settings,
    setSettings,
    settingsHydrated,
    isPublicMode,
    save: saveSettings,
    clear: clearSettings,
  } = useSettings()

  const [saving, setSaving] = React.useState(false)
  const [showAdmin, setShowAdmin] = React.useState(false)

  const handleSettingsChange = React.useCallback(
    (updates: Partial<typeof settings>) => {
      setSettings((prev) => ({ ...prev, ...updates }))
    },
    [setSettings]
  )

  const handleApplyPreset = React.useCallback(
    (presetConfig: Partial<typeof settings>) => {
      setSettings((prev) => ({ ...prev, ...presetConfig }))
      toast.success("已应用预设配置")
    },
    [setSettings]
  )

  const handleSave = React.useCallback(async () => {
    setSaving(true)
    try {
      await saveSettings()
      toast.success("设置已保存")
    } catch (error) {
      toast.error("保存失败：" + String(error))
    } finally {
      setSaving(false)
    }
  }, [saveSettings])

  const handleReset = React.useCallback(() => {
    if (confirm("确定要重置所有设置吗？此操作不可撤销。")) {
      clearSettings()
      toast.success("设置已重置")
    }
  }, [clearSettings])

  if (!settingsHydrated) {
    return (
      <main className="container mx-auto max-w-5xl px-4 py-8">
        <div className="text-center text-muted-foreground">加载中...</div>
      </main>
    )
  }

  return (
    <main className="container mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            >
              <ArrowLeftIcon className="h-4 w-4" />
              返回首页
            </Link>
          </div>
          <h1 className="mt-2 text-2xl font-bold">设置</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            按照处理流程配置：文档解析 → 文字识别 → 输出质量
          </p>
        </div>
        <div className="flex gap-2">
          {!isPublicMode && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowAdmin(!showAdmin)}
            >
              {showAdmin ? "隐藏管理员" : "管理员设置"}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleReset}>
            重置
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? "保存中..." : "保存设置"}
          </Button>
        </div>
      </div>

      {showAdmin && !isPublicMode && (
        <div className="mb-6 rounded-lg border bg-muted/50 p-6">
          <AdminSettings />
        </div>
      )}

      <div className="space-y-8">
        {/* Quick Presets */}
        <div className="rounded-lg border bg-card p-6">
          <QuickPresets onApplyPreset={handleApplyPreset} />
        </div>

        {/* Main Flow Sections */}
        <div className="space-y-6">
          {/* 1. Parsing Method */}
          <div className="rounded-lg border bg-card p-6">
            <ParsingMethodSection
              settings={settings}
              onSettingsChange={handleSettingsChange}
            />
          </div>

          {/* 2. OCR Strategy */}
          <div className="rounded-lg border bg-card p-6">
            <OcrStrategySection
              settings={settings}
              onSettingsChange={handleSettingsChange}
            />
          </div>

          {/* 3. Output Quality */}
          <div className="rounded-lg border bg-card p-6">
            <OutputQualitySection
              settings={settings}
              onSettingsChange={handleSettingsChange}
            />
          </div>

          {/* General Advanced Settings */}
          <div className="rounded-lg border bg-card p-6">
            <GeneralAdvancedSection
              settings={settings}
              onSettingsChange={handleSettingsChange}
            />
          </div>
        </div>
      </div>

      <div className="mt-8 flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={handleReset}>
          重置所有设置
        </Button>
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {saving ? "保存中..." : "保存设置"}
        </Button>
      </div>
    </main>
  )
}
