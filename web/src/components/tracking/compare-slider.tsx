"use client"

import * as React from "react"

import { Badge } from "@/components/ui/badge"
import { TrackingArtifactImage } from "./tracking-artifact-image"

type ArtifactImage = {
  page_index: number
  path: string
  url: string
}

export type CompareSliderProps = {
  /** Base image for the comparison */
  trackedCompareBase: ArtifactImage | null
  /** After image overlaid on the right */
  trackedCompareAfter: ArtifactImage | null
  /** Before overlay on the left side */
  trackedBeforeOverlay: ArtifactImage | null
  /** After (layout) overlay on the right side */
  trackedLayoutAfter: ArtifactImage | null
  /** Whether layout after differs from compare after */
  showLayoutAfterOverlay: boolean
  activeTrackedPageLabel: string
  compareSplitRatio: number
  setCompareSplitRatio: React.Dispatch<React.SetStateAction<number>>
}

/**
 * Before/after image comparison slider.
 *
 * Supports mouse move, touch move, and a range input for precise control.
 * The left side shows "before" and the right side shows "after" via clip-path.
 */
export function CompareSlider({
  trackedCompareBase,
  trackedCompareAfter,
  trackedBeforeOverlay,
  trackedLayoutAfter,
  showLayoutAfterOverlay,
  activeTrackedPageLabel,
  compareSplitRatio,
  setCompareSplitRatio,
}: CompareSliderProps) {
  const compareSplitPercent = Math.round(compareSplitRatio * 100)

  const updateCompareSplitRatio = React.useCallback(
    (clientX: number, rect: DOMRect) => {
      if (rect.width <= 0) return
      const ratio = (clientX - rect.left) / rect.width
      setCompareSplitRatio(Math.max(0, Math.min(1, ratio)))
    },
    [setCompareSplitRatio]
  )

  const handleComparePointerMove = React.useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      updateCompareSplitRatio(event.clientX, event.currentTarget.getBoundingClientRect())
    },
    [updateCompareSplitRatio]
  )

  const handleCompareTouchMove = React.useCallback(
    (event: React.TouchEvent<HTMLDivElement>) => {
      const touch = event.touches[0]
      if (!touch) return
      updateCompareSplitRatio(touch.clientX, event.currentTarget.getBoundingClientRect())
    },
    [updateCompareSplitRatio]
  )

  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between gap-2">
        <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          悬停对比（左：转换前 · 右：转换后）
        </div>
        <Badge variant="outline">分割线 {compareSplitPercent}%</Badge>
      </div>
      <div
        className="panel-contrast-strong tracking-stage group relative min-h-[24rem] overflow-hidden border sm:min-h-[30rem]"
        onMouseMove={handleComparePointerMove}
        onTouchStart={handleCompareTouchMove}
        onTouchMove={handleCompareTouchMove}
      >
        {trackedCompareBase ? (
          <TrackingArtifactImage
            src={trackedCompareBase.url}
            alt={`第 ${activeTrackedPageLabel} 页对比底图`}
            className="object-contain"
            priority
          />
        ) : (
          <div className="grid h-64 place-items-center text-sm text-white/80">
            暂无可用于对比的图片
          </div>
        )}

        {trackedCompareAfter ? (
          <div
            className="pointer-events-none absolute inset-0 transition-[clip-path] duration-150 ease-out"
            style={{ clipPath: `inset(0 0 0 ${compareSplitPercent}%)` }}
          >
            <TrackingArtifactImage
              src={trackedCompareAfter.url}
              alt={`第 ${activeTrackedPageLabel} 页转换后`}
              className="object-contain"
            />
          </div>
        ) : null}

        {trackedBeforeOverlay ? (
          <div
            className="pointer-events-none absolute inset-0"
            style={{ clipPath: `inset(0 ${100 - compareSplitPercent}% 0 0)` }}
          >
            <TrackingArtifactImage
              src={trackedBeforeOverlay.url}
              alt={`第 ${activeTrackedPageLabel} 页转换前高亮`}
              className="object-contain opacity-45"
            />
          </div>
        ) : null}

        {trackedLayoutAfter && showLayoutAfterOverlay ? (
          <div
            className="pointer-events-none absolute inset-0"
            style={{ clipPath: `inset(0 0 0 ${compareSplitPercent}%)` }}
          >
            <TrackingArtifactImage
              src={trackedLayoutAfter.url}
              alt={`第 ${activeTrackedPageLabel} 页转换后高亮`}
              className="object-contain opacity-60"
            />
          </div>
        ) : null}

        <div
          className="compare-divider pointer-events-none absolute inset-y-0 z-20 w-0.5"
          style={{ left: `${compareSplitPercent}%` }}
        />
        <div className="pointer-events-none absolute left-2 top-2 z-20 border bg-black/50 px-2 py-1 font-mono text-[11px] text-white">
          转换前
        </div>
        <div className="pointer-events-none absolute right-2 top-2 z-20 border bg-black/50 px-2 py-1 font-mono text-[11px] text-white">
          转换后
        </div>
      </div>
      <div className="grid gap-2 border border-border bg-muted/20 p-3 sm:grid-cols-[1fr_auto] sm:items-center">
        <label
          htmlFor="compare-split"
          className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground"
        >
          分割线位置
        </label>
        <Badge variant="outline">{compareSplitPercent}%</Badge>
        <input
          id="compare-split"
          type="range"
          min={0}
          max={100}
          step={1}
          value={compareSplitPercent}
          onChange={(e) => {
            const next = Number(e.target.value)
            if (Number.isFinite(next)) {
              setCompareSplitRatio(Math.max(0, Math.min(1, next / 100)))
            }
          }}
          className="col-span-full h-2 w-full accent-foreground"
          aria-label="调整前后对比滑杆位置"
        />
      </div>
      <div className="text-xs text-muted-foreground">
        桌面端可移动鼠标调整分割线，移动端可拖动图片或使用滑杆精确控制对比位置。
      </div>
    </div>
  )
}
