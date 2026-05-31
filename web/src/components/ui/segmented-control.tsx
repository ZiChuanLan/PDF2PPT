"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

interface SegmentedControlOption<T extends string> {
  id: T
  label: string
  icon?: React.ReactNode
  badge?: string
}

interface SegmentedControlProps<T extends string> {
  options: SegmentedControlOption<T>[]
  value: T
  onChange: (v: T) => void
  disabled?: boolean
  className?: string
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  disabled,
  className,
}: SegmentedControlProps<T>) {
  const activeIndex = options.findIndex((o) => o.id === value)
  const containerRef = React.useRef<HTMLDivElement>(null)
  const [pillStyle, setPillStyle] = React.useState<React.CSSProperties>({})

  React.useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return
    const buttons = container.querySelectorAll<HTMLButtonElement>("[data-segment]")
    const active = buttons[activeIndex]
    if (!active) return

    const containerRect = container.getBoundingClientRect()
    const activeRect = active.getBoundingClientRect()

    setPillStyle({
      left: activeRect.left - containerRect.left,
      width: activeRect.width,
      transitionDuration: "var(--duration-base)",
      transitionTimingFunction: "var(--ease-emphasized)",
    })
  }, [activeIndex])

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative flex h-8 items-center border border-border/60 bg-muted/30 p-0.5",
        disabled && "pointer-events-none opacity-50",
        className,
      )}
    >
      {/* Sliding pill indicator */}
      <div
        className="absolute top-0.5 bottom-0.5 bg-foreground"
        style={pillStyle}
      />
      {options.map((opt) => {
        const isActive = opt.id === value
        return (
          <button
            key={opt.id}
            type="button"
            data-segment={opt.id}
            onClick={() => onChange(opt.id)}
            className={cn(
              "relative z-10 flex flex-1 items-center justify-center gap-1 px-2 text-xs font-medium transition-colors",
              isActive
                ? "text-primary-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {opt.icon}
            {opt.label}
            {opt.badge && (
              <span className={cn(
                "font-mono text-[8px] uppercase tracking-widest",
                isActive ? "text-primary-foreground/70" : "text-emerald-600"
              )}>
                {opt.badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
