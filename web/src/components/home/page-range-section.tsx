"use client"

import * as React from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

interface PageRangeSectionProps {
  isImageInput: boolean
  usePageRange: boolean
  setUsePageRange: (value: boolean) => void
  pageStartInput: string
  setPageStartInput: (value: string) => void
  pageEndInput: string
  setPageEndInput: (value: string) => void
  currentPreviewFile: File | null
  previewPage: number
}

export function PageRangeSection({
  isImageInput,
  usePageRange,
  setUsePageRange,
  pageStartInput,
  setPageStartInput,
  pageEndInput,
  setPageEndInput,
  currentPreviewFile,
  previewPage,
}: PageRangeSectionProps) {
  return (
    <div className="home-inline-panel px-4 py-3">
      {isImageInput ? (
        <p className="text-xs leading-6 text-muted-foreground">
          图片输入自动包装成单页 PDF，无需设置页码范围。
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 accent-foreground"
                checked={usePageRange}
                onChange={(e) => {
                  const enabled = e.target.checked
                  setUsePageRange(enabled)
                  if (!enabled) {
                    setPageStartInput("")
                    setPageEndInput("")
                  }
                }}
              />
              限定页码范围
            </label>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="xs"
                disabled={!currentPreviewFile}
                onClick={() => {
                  setUsePageRange(true)
                  const current = String(previewPage)
                  setPageStartInput(current)
                  setPageEndInput(current)
                }}
              >
                单页试跑
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                onClick={() => {
                  setUsePageRange(false)
                  setPageStartInput("")
                  setPageEndInput("")
                }}
              >
                整份
              </Button>
            </div>
          </div>
          {usePageRange ? (
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div className="grid gap-1">
                <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  起始页
                </label>
                <Input
                  inputMode="numeric"
                  placeholder="1"
                  value={pageStartInput}
                  onChange={(e) => setPageStartInput(e.target.value)}
                  className="h-9"
                />
              </div>
              <div className="grid gap-1">
                <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  结束页
                </label>
                <Input
                  inputMode="numeric"
                  placeholder="5"
                  value={pageEndInput}
                  onChange={(e) => setPageEndInput(e.target.value)}
                  className="h-9"
                />
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
