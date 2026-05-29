"use client"

import * as React from "react"
import Link from "next/link"
import { ArrowLeftIcon, ScanIcon, SlidersHorizontalIcon, WrenchIcon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Tabs } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { useSettings } from "@/hooks/use-settings"
import { clearStoredApiOrigin } from "@/lib/api"

import { QuickPresets } from "@/components/settings/quick-presets"
import { RecognitionMethodSection } from "@/components/settings/recognition-method-section"
import { OutputQualitySection } from "@/components/settings/output-quality-section"
import { AdminSettings } from "@/components/settings/admin-settings"
import { ModelManagement } from "@/components/settings/model-management"

function formatTimeAgo(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000)
  if (seconds < 60) return "刚刚"
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`
  return `${Math.floor(seconds / 86400)} 天前`
}

export default function SettingsPage() {
  const {
    settings,
    setSettings,
    settingsHydrated,
    isPublicMode,
    lastSavedAt,
    save: saveSettings,
    clear: clearSettings,
  } = useSettings()

  const [saving, setSaving] = React.useState(false)
  const [activeTab, setActiveTab] = React.useState("recognition")
  const [isDirty, setIsDirty] = React.useState(false)

  // beforeunload warning when there are unsaved changes
  React.useEffect(() => {
    if (!isDirty) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ""
    }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [isDirty])

  const handleSettingsChange = React.useCallback(
    (updates: Partial<typeof settings>) => {
      setSettings((prev) => ({ ...prev, ...updates }))
      setIsDirty(true)
    },
    [setSettings]
  )

  const handleApplyPreset = React.useCallback(
    (presetConfig: Partial<typeof settings>) => {
      setSettings((prev) => ({ ...prev, ...presetConfig }))
      setIsDirty(true)
      toast.success("已应用预设配置")
    },
    [setSettings]
  )

  const handleSave = React.useCallback(async () => {
    setSaving(true)
    try {
      await saveSettings()
      setIsDirty(false)
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
      clearStoredApiOrigin()
      setIsDirty(false)
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
            选择识别方式 → 配置 API → 调整输出
          </p>
        </div>
        <div className="flex gap-2">
          {lastSavedAt != null && !isDirty && (
            <span className="self-center text-xs text-muted-foreground">
              已保存 {formatTimeAgo(lastSavedAt)}
            </span>
          )}
          {isDirty && (
            <span className="self-center inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-600">
              <span className="inline-block size-1.5 rounded-full bg-amber-500" />
              未保存
            </span>
          )}
          <Button variant="outline" size="sm" onClick={handleReset}>
            重置
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? "保存中..." : isDirty ? "保存设置 *" : "保存设置"}
          </Button>
        </div>
      </div>

      {/* QuickPresets — compact row above tabs */}
      <div className="mb-6">
        <QuickPresets onApplyPreset={handleApplyPreset} compact />
      </div>

      {/* Tab Layout */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <nav className="flex border-b border-border" role="tablist">
          {([
            ["recognition", "识别", ScanIcon],
            ["output", "输出", SlidersHorizontalIcon],
            ["advanced", "高级", WrenchIcon],
          ] as const).map(([val, label, Icon]) => (
            <button
              key={val}
              type="button"
              role="tab"
              aria-selected={activeTab === val}
              aria-controls={`tabpanel-${val}`}
              onClick={() => setActiveTab(val)}
              className={cn(
                "inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors",
                activeTab === val
                  ? "border-b-2 border-destructive text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </nav>

        {/* Content panels — conditionally rendered to avoid mount-side-effects on inactive tabs */}
        <div className="border border-t-0 p-6">
          {activeTab === "recognition" && (
            <div role="tabpanel" id="tabpanel-recognition">
              <RecognitionMethodSection
                settings={settings}
                onSettingsChange={handleSettingsChange}
              />
            </div>
          )}

          {activeTab === "output" && (
            <div role="tabpanel" id="tabpanel-output">
              <OutputQualitySection
                settings={settings}
                onSettingsChange={handleSettingsChange}
              />
            </div>
          )}

          {activeTab === "advanced" && (
            <div role="tabpanel" id="tabpanel-advanced">
              <div className="space-y-6">
                {/* Model Management — visible to all users */}
                <div>
                  <h3 className="text-base font-semibold">模型管理</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    下载或删除本地 OCR 和版面分析模型。下载后的模型可在任意识别方式中使用。
                  </p>
                  <div className="mt-3">
                    <ModelManagement />
                  </div>
                </div>
                {!isPublicMode && <AdminSettings />}
              </div>
            </div>
          )}
        </div>
      </Tabs>

      {/* Bottom actions */}
      <div className="mt-8 flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={handleReset}>
          重置所有设置
        </Button>
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {saving ? "保存中..." : isDirty ? "保存设置 *" : "保存设置"}
        </Button>
      </div>
    </main>
  )
}
