"use client"

import * as React from "react"
import Link from "next/link"
import { ArrowLeftIcon, FileTextIcon, ScanIcon, SlidersHorizontalIcon, WrenchIcon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
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
  const [activeTab, setActiveTab] = React.useState("parse")

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
      {/* Header */}
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
            按照处理流程配置：解析 → 识别 → 输出 → 高级
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleReset}>
            重置
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? "保存中..." : "保存设置"}
          </Button>
        </div>
      </div>

      {/* QuickPresets — compact row above tabs */}
      <div className="mb-6">
        <QuickPresets onApplyPreset={handleApplyPreset} compact />
      </div>

      {/* Tab Layout */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-0 w-full justify-start rounded-b-none">
          <TabsTrigger value="parse" className="gap-1.5">
            <FileTextIcon className="h-4 w-4" />
            解析
          </TabsTrigger>
          <TabsTrigger value="ocr" className="gap-1.5">
            <ScanIcon className="h-4 w-4" />
            识别
          </TabsTrigger>
          <TabsTrigger value="output" className="gap-1.5">
            <SlidersHorizontalIcon className="h-4 w-4" />
            输出
          </TabsTrigger>
          <TabsTrigger value="advanced" className="gap-1.5">
            <WrenchIcon className="h-4 w-4" />
            高级
          </TabsTrigger>
        </TabsList>

        {/* Content panels — all kept mounted (hidden) to preserve fold state across tab switches */}
        <div className="rounded-b-lg border border-t-0 bg-card p-6">
          <div
            role="tabpanel"
            id="tabpanel-parse"
            className={activeTab !== "parse" ? "hidden" : ""}
          >
            <ParsingMethodSection
              settings={settings}
              onSettingsChange={handleSettingsChange}
            />
          </div>

          <div
            role="tabpanel"
            id="tabpanel-ocr"
            className={activeTab !== "ocr" ? "hidden" : ""}
          >
            {settings.parseEngineMode === "mineru_cloud" ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                MinerU 已内置 OCR 处理，无需额外配置
              </div>
            ) : (
              <OcrStrategySection
                settings={settings}
                onSettingsChange={handleSettingsChange}
              />
            )}
          </div>

          <div
            role="tabpanel"
            id="tabpanel-output"
            className={activeTab !== "output" ? "hidden" : ""}
          >
            <OutputQualitySection
              settings={settings}
              onSettingsChange={handleSettingsChange}
            />
          </div>

          <div
            role="tabpanel"
            id="tabpanel-advanced"
            className={activeTab !== "advanced" ? "hidden" : ""}
          >
            <div className="space-y-6">
              <GeneralAdvancedSection
                settings={settings}
                onSettingsChange={handleSettingsChange}
              />
              {!isPublicMode && <AdminSettings />}
            </div>
          </div>
        </div>
      </Tabs>

      {/* Bottom actions */}
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
