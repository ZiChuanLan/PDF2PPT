"use client"

import * as React from "react"
import { PlusIcon, Trash2Icon, EditIcon, StarIcon, CheckIcon } from "lucide-react"
import { toast } from "sonner"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  getAllPresets,
  getDefaultPreset,
  setDefaultPreset,
  createCustomPreset,
  updateCustomPreset,
  deleteCustomPreset,
  type JobPreset,
  type Settings,
} from "@/lib/settings"

type PresetManagerProps = {
  currentSettings: Settings
  className?: string
}

type EditingPreset = {
  id: string | null
  name: string
  description: string
  icon: string
}

export function PresetManager({ currentSettings, className }: PresetManagerProps) {
  const [allPresets, setAllPresets] = React.useState<JobPreset[]>([])
  const [defaultPresetId, setDefaultPresetId] = React.useState<string | null>(null)
  const [isCreating, setIsCreating] = React.useState(false)
  const [editingPreset, setEditingPreset] = React.useState<EditingPreset | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = React.useState<string | null>(null)

  const refreshPresets = React.useCallback(() => {
    const presets = getAllPresets()
    const defaultP = getDefaultPreset()
    setAllPresets(presets)
    setDefaultPresetId(defaultP?.id ?? null)
  }, [])

  React.useEffect(() => {
    refreshPresets()
  }, [refreshPresets])

  const handleCreatePreset = React.useCallback(() => {
    if (!editingPreset) return

    const { name, description, icon } = editingPreset
    if (!name.trim()) {
      toast.error("预设名称不能为空")
      return
    }

    try {
      createCustomPreset(name.trim(), description.trim(), currentSettings, icon.trim() || undefined)
      toast.success("预设已创建")
      setIsCreating(false)
      setEditingPreset(null)
      refreshPresets()
    } catch (e) {
      console.error("Failed to create preset:", e)
      toast.error("创建预设失败")
    }
  }, [editingPreset, currentSettings, refreshPresets])

  const handleUpdatePreset = React.useCallback(() => {
    if (!editingPreset || !editingPreset.id) return

    const { id, name, description, icon } = editingPreset
    if (!name.trim()) {
      toast.error("预设名称不能为空")
      return
    }

    try {
      const success = updateCustomPreset(id, {
        name: name.trim(),
        description: description.trim(),
        icon: icon.trim() || undefined,
      })
      if (success) {
        toast.success("预设已更新")
        setEditingPreset(null)
        refreshPresets()
      } else {
        toast.error("更新预设失败")
      }
    } catch (e) {
      console.error("Failed to update preset:", e)
      toast.error("更新预设失败")
    }
  }, [editingPreset, refreshPresets])

  const handleDeletePreset = React.useCallback(
    (id: string) => {
      try {
        const success = deleteCustomPreset(id)
        if (success) {
          toast.success("预设已删除")
          setDeleteConfirmId(null)
          refreshPresets()
        } else {
          toast.error("删除预设失败")
        }
      } catch (e) {
        console.error("Failed to delete preset:", e)
        toast.error("删除预设失败")
      }
    },
    [refreshPresets]
  )

  const handleSetDefault = React.useCallback(
    (id: string) => {
      try {
        const newDefaultId = defaultPresetId === id ? null : id
        setDefaultPreset(newDefaultId)
        setDefaultPresetId(newDefaultId)
        toast.success(newDefaultId ? "已设为默认预设" : "已取消默认预设")
      } catch (e) {
        console.error("Failed to set default preset:", e)
        toast.error("设置默认预设失败")
      }
    },
    [defaultPresetId]
  )

  const handleStartCreate = React.useCallback(() => {
    setIsCreating(true)
    setEditingPreset({
      id: null,
      name: "",
      description: "",
      icon: "",
    })
  }, [])

  const handleStartEdit = React.useCallback((preset: JobPreset) => {
    setEditingPreset({
      id: preset.id,
      name: preset.name,
      description: preset.description,
      icon: preset.icon || "",
    })
  }, [])

  const handleCancelEdit = React.useCallback(() => {
    setIsCreating(false)
    setEditingPreset(null)
  }, [])

  return (
    <div className={cn("space-y-6", className)}>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-serif text-2xl">预设管理</h2>
          <p className="text-sm text-muted-foreground">管理任务配置预设</p>
        </div>
        <Button
          type="button"
          variant="default"
          size="sm"
          onClick={handleStartCreate}
          disabled={isCreating}
        >
          <PlusIcon className="size-4" />
          保存当前配置为预设
        </Button>
      </div>

      {/* Create/Edit Form */}
      {(isCreating || editingPreset) && (
        <Card className="border-foreground/30 bg-muted/20">
          <CardHeader>
            <CardTitle className="text-lg">
              {isCreating ? "创建新预设" : "编辑预设"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2">
              <label htmlFor="preset-name" className="text-sm font-medium">
                预设名称 <span className="text-destructive">*</span>
              </label>
              <Input
                id="preset-name"
                type="text"
                placeholder="例如：快速处理"
                value={editingPreset?.name || ""}
                onChange={(e) =>
                  setEditingPreset((prev) =>
                    prev ? { ...prev, name: e.target.value } : null
                  )
                }
                maxLength={50}
              />
            </div>

            <div className="grid gap-2">
              <label htmlFor="preset-description" className="text-sm font-medium">
                描述
              </label>
              <textarea
                id="preset-description"
                placeholder="例如：本地处理，速度最快，无需 API 密钥"
                value={editingPreset?.description || ""}
                onChange={(e) =>
                  setEditingPreset((prev) =>
                    prev ? { ...prev, description: e.target.value } : null
                  )
                }
                maxLength={200}
                rows={3}
                className="w-full min-w-0 border-b-2 border-input bg-transparent px-3 py-2 font-mono text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus-visible:bg-[#f0f0f0] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>

            <div className="grid gap-2">
              <label htmlFor="preset-icon" className="text-sm font-medium">
                图标（可选）
              </label>
              <Input
                id="preset-icon"
                type="text"
                placeholder="例如：⚡"
                value={editingPreset?.icon || ""}
                onChange={(e) =>
                  setEditingPreset((prev) =>
                    prev ? { ...prev, icon: e.target.value } : null
                  )
                }
                maxLength={2}
              />
              <p className="text-xs text-muted-foreground">
                输入一个 emoji 作为图标
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="default"
                size="sm"
                onClick={isCreating ? handleCreatePreset : handleUpdatePreset}
              >
                <CheckIcon className="size-4" />
                {isCreating ? "创建" : "保存"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleCancelEdit}
              >
                取消
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Preset List */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-muted-foreground">所有预设</h3>
        <div className="grid gap-3">
          {allPresets.map((preset) => {
            const isDefault = defaultPresetId === preset.id
            const isDeleting = deleteConfirmId === preset.id

            return (
              <Card
                key={preset.id}
                className={cn(
                  "transition-all",
                  isDefault && "border-foreground/50"
                )}
              >
                <CardHeader>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      {preset.icon && (
                        <span className="text-xl leading-none shrink-0" aria-hidden="true">
                          {preset.icon}
                        </span>
                      )}
                      <div className="min-w-0 flex-1">
                        <CardTitle className="text-base">{preset.name}</CardTitle>
                        {preset.isBuiltIn && (
                          <Badge variant="outline" className="mt-1 text-[10px]">
                            内置
                          </Badge>
                        )}
                        {isDefault && (
                          <Badge variant="outline" className="mt-1 text-[10px]">
                            默认
                          </Badge>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-1 shrink-0">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => handleSetDefault(preset.id)}
                        title={isDefault ? "取消默认" : "设为默认"}
                      >
                        <StarIcon
                          className={cn(
                            "size-4",
                            isDefault && "fill-current text-amber-500"
                          )}
                        />
                      </Button>

                      {!preset.isBuiltIn && (
                        <>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => handleStartEdit(preset)}
                            title="编辑"
                          >
                            <EditIcon className="size-4" />
                          </Button>

                          {isDeleting ? (
                            <>
                              <Button
                                type="button"
                                variant="destructive"
                                size="icon-sm"
                                onClick={() => handleDeletePreset(preset.id)}
                                title="确认删除"
                              >
                                <CheckIcon className="size-4" />
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon-sm"
                                onClick={() => setDeleteConfirmId(null)}
                                title="取消"
                              >
                                ×
                              </Button>
                            </>
                          ) : (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon-sm"
                              onClick={() => setDeleteConfirmId(preset.id)}
                              title="删除"
                            >
                              <Trash2Icon className="size-4" />
                            </Button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-xs leading-relaxed">
                    {preset.description}
                  </CardDescription>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>
    </div>
  )
}
