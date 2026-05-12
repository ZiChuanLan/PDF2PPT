"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

export function Checkbox({
  checked,
  onCheckedChange,
  className,
  id,
  ...props
}: {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  className?: string
  id?: string
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "checked" | "onChange" | "type">) {
  return (
    <input
      type="checkbox"
      id={id}
      checked={checked}
      onChange={(e) => onCheckedChange(e.target.checked)}
      className={cn("h-4 w-4 accent-foreground", className)}
      {...props}
    />
  )
}
