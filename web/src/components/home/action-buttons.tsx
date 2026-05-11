"use client"

import * as React from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/components/auth-provider"

interface ActionButtonsProps {
  fileCount: number
  handleConvertAll: () => Promise<void>
  canStart: boolean
  actionError: string | null
  preflightWarning: string | null
  setPreflightAcknowledged: (value: boolean) => void
  setUsePageRange: (value: boolean) => void
  setPageStartInput: (value: string) => void
  setPageEndInput: (value: string) => void
  previewPage: number
}

export function ActionButtons({
  fileCount,
  handleConvertAll,
  canStart,
  actionError,
  preflightWarning,
  setPreflightAcknowledged,
  setUsePageRange,
  setPageStartInput,
  setPageEndInput,
  previewPage,
}: ActionButtonsProps) {
  const { user, isLoading: isAuthLoading } = useAuth()

  return (
    <>
      <div className="space-y-2">
        {preflightWarning && (
          <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <p className="font-medium">⚠️ {preflightWarning}</p>
            <div className="mt-1.5 flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-6 text-[11px]"
                onClick={() => {
                  setPreflightAcknowledged(true)
                  void handleConvertAll()
                }}
              >
                仍然转换
              </Button>
              <Link href="/settings">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 text-[11px]"
                >
                  去设置
                </Button>
              </Link>
            </div>
          </div>
        )}
        {!user && !isAuthLoading ? (
          <Button type="button" variant="outline" className="w-full" asChild>
            <Link href="/login">登录后创建任务</Link>
          </Button>
        ) : (
          <>
            <Button
              type="button"
              className="w-full"
              onClick={handleConvertAll}
              disabled={!canStart}
            >
              {fileCount > 1 ? `全部转换 (${fileCount} 个文件)` : "开始转换"}
            </Button>
            {fileCount === 1 && (
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => {
                  setUsePageRange(true)
                  const current = String(previewPage)
                  setPageStartInput(current)
                  setPageEndInput(current)
                  void handleConvertAll()
                }}
                disabled={!canStart}
              >
                单页试跑（当前页）
              </Button>
            )}
          </>
        )}
      </div>

      {actionError ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {actionError}
        </div>
      ) : null}
    </>
  )
}
