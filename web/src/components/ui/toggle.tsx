"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import { HoverHint } from "@/components/ui/hover-hint"

interface ToggleProps {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  hint?: string
  disabled?: boolean
  className?: string
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
  disabled,
  className,
}: ToggleProps) {
  return (
    <label
      className={cn(
        "flex items-center justify-between gap-3 group",
        disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
        className,
      )}
    >
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-foreground">{label}</span>
        {hint && <HoverHint text={hint} />}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-5 w-9 shrink-0 items-center border transition-colors",
          checked
            ? "border-foreground bg-foreground"
            : "border-border bg-transparent group-hover:border-foreground/40",
        )}
      >
        <span
          className={cn(
            "pointer-events-none block size-3.5 transition-all",
            checked
              ? "translate-x-[18px] bg-primary-foreground"
              : "translate-x-0.5 bg-muted-foreground",
          )}
          style={{
            transitionDuration: "var(--duration-quick)",
            transitionTimingFunction: "var(--ease-emphasized)",
          }}
        />
      </button>
    </label>
  )
}
