"use client"

import * as React from "react"
import Link from "next/link"
import { ArrowLeftIcon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useSettings } from "@/hooks/use-settings"

import { BasicSettings } from "@/components/settings/basic-settings"
import { OcrSettings } from "@/components/settings/ocr-settings"
import { AdvancedSettings } from "@/components/settings/advanced-settings"
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

  const [activeTab, setActiveTab] = React.useState("basic")
  const [saving, setSaving] = React.useState(false)

  const handleSettingsChange = React.useCallback(
    (updates: Partial<typeof settings>) => {
      setSettings((prev) => ({ ...prev, ...updates }))
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
            配置 PDF 解析引擎、OCR 提供方和 PPT 生成参数
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

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="basic">基础设置</TabsTrigger>
          <TabsTrigger value="ocr">OCR 设置</TabsTrigger>
          <TabsTrigger value="advanced">高级设置</TabsTrigger>
          {!isPublicMode && <TabsTrigger value="admin">管理员</TabsTrigger>}
        </TabsList>

        <TabsContent value="basic" className="space-y-6">
          <BasicSettings settings={settings} onSettingsChange={handleSettingsChange} />
        </TabsContent>

        <TabsContent value="ocr" className="space-y-6">
          <OcrSettings settings={settings} onSettingsChange={handleSettingsChange} />
        </TabsContent>

        <TabsContent value="advanced" className="space-y-6">
          <AdvancedSettings settings={settings} onSettingsChange={handleSettingsChange} />
        </TabsContent>

        {!isPublicMode && (
          <TabsContent value="admin" className="space-y-6">
            <AdminSettings />
          </TabsContent>
        )}
      </Tabs>

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
