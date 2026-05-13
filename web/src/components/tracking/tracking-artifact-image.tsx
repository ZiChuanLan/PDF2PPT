"use client"

import Image, { type ImageLoader } from "next/image"

const passthroughImageLoader: ImageLoader = ({ src }) => src

/**
 * Shared artifact image renderer used by tracking sub-components.
 * Uses Next.js Image with unoptimized passthrough loader for external URLs.
 */
export function TrackingArtifactImage({
  src,
  alt,
  className,
  priority = false,
}: {
  src: string
  alt: string
  className?: string
  priority?: boolean
}) {
  return (
    <Image
      loader={passthroughImageLoader}
      unoptimized
      src={src}
      alt={alt}
      fill
      priority={priority}
      sizes="(min-width: 1280px) 720px, (min-width: 1024px) 50vw, 100vw"
      className={className}
    />
  )
}
