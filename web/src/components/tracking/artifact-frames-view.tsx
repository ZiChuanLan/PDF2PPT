"use client"

import * as React from "react"

import { TrackingArtifactImage } from "./tracking-artifact-image"

type ArtifactImage = {
  page_index: number
  path: string
  url: string
}

export type ArtifactFramesViewProps = {
  apiOrigin: string
  activeTrackedPageLabel: string
  /** Find artifact image by page index */
  findArtifactByPage: (
    images: ArtifactImage[] | undefined,
    page: number | null
  ) => ArtifactImage | null
  trackedArtifacts: {
    original_images?: ArtifactImage[]
    cleaned_images?: ArtifactImage[]
    final_preview_images?: ArtifactImage[]
    ocr_overlay_images?: ArtifactImage[]
    layout_before_images?: ArtifactImage[]
    layout_after_images?: ArtifactImage[]
  } | null
  activeTrackedPage: number | null
}

/**
 * Artifact frames view — two side-by-side panels with before/after overlays.
 * Left: original PDF with hover overlay. Right: converted image with hover overlay.
 */
export function ArtifactFramesView({
  apiOrigin,
  activeTrackedPageLabel,
  findArtifactByPage,
  trackedArtifacts,
  activeTrackedPage,
}: ArtifactFramesViewProps) {
  const trackedOriginal = findArtifactByPage(trackedArtifacts?.original_images, activeTrackedPage)
  const trackedClean = findArtifactByPage(trackedArtifacts?.cleaned_images, activeTrackedPage)
  const trackedFinalPreview = findArtifactByPage(
    trackedArtifacts?.final_preview_images,
    activeTrackedPage
  )
  const trackedOcrOverlay = findArtifactByPage(
    trackedArtifacts?.ocr_overlay_images,
    activeTrackedPage
  )
  const trackedLayoutBefore = findArtifactByPage(
    trackedArtifacts?.layout_before_images,
    activeTrackedPage
  )
  const trackedLayoutAfter = findArtifactByPage(
    trackedArtifacts?.layout_after_images,
    activeTrackedPage
  )

  const trackedBeforeOverlay = trackedLayoutBefore || trackedOcrOverlay
  const trackedAfterOverlay = trackedFinalPreview || trackedLayoutAfter || trackedClean || null

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="grid gap-2">
        <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          原始 PDF（悬停显示识别框）
        </div>
        <div className="panel-contrast tracking-stage group relative min-h-[22rem] overflow-hidden border sm:min-h-[28rem]">
          {trackedOriginal ? (
            <TrackingArtifactImage
              src={`${apiOrigin}${trackedOriginal.url}`}
              alt={`原始第 ${activeTrackedPageLabel} 页`}
              className="object-contain"
              priority
            />
          ) : (
            <div className="grid h-52 place-items-center text-xs text-white/80">
              暂无原始页图
            </div>
          )}
          {trackedBeforeOverlay ? (
            <TrackingArtifactImage
              src={`${apiOrigin}${trackedBeforeOverlay.url}`}
              alt={`第 ${activeTrackedPageLabel} 页识别框`}
              className="pointer-events-none object-contain opacity-0 transition-opacity duration-200 group-hover:opacity-100"
            />
          ) : null}
        </div>
      </div>

      <div className="grid gap-2">
        <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          转换完成图（悬停显示后处理框）
        </div>
        <div className="panel-contrast tracking-stage group relative min-h-[22rem] overflow-hidden border sm:min-h-[28rem]">
          {trackedAfterOverlay ? (
            <TrackingArtifactImage
              src={`${apiOrigin}${trackedAfterOverlay.url}`}
              alt={`第 ${activeTrackedPageLabel} 页转换对比`}
              className="object-contain"
              priority
            />
          ) : trackedOriginal ? (
            <TrackingArtifactImage
              src={`${apiOrigin}${trackedOriginal.url}`}
              alt={`第 ${activeTrackedPageLabel} 页原图`}
              className="object-contain"
              priority
            />
          ) : (
            <div className="grid h-52 place-items-center text-xs text-white/80">
              暂无转换对比图
            </div>
          )}
          {trackedLayoutAfter ? (
            <TrackingArtifactImage
              src={`${apiOrigin}${trackedLayoutAfter.url}`}
              alt={`第 ${activeTrackedPageLabel} 页后处理框`}
              className="pointer-events-none object-contain opacity-0 transition-opacity duration-200 group-hover:opacity-100"
            />
          ) : null}
        </div>
      </div>
    </div>
  )
}
