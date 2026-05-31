import * as React from "react"
import { cn } from "@/lib/utils"

interface CalloutProps {
  variant?: "info" | "warning" | "success" | "error"
  icon?: React.ReactNode
  children: React.ReactNode
  action?: React.ReactNode
  className?: string
}

const variantStyles = {
  info: "border-l-[#3b82f6] bg-[#eff6ff]/60 text-[#1e40af]",
  warning: "border-l-amber-500 bg-amber-50/60 text-amber-800",
  success: "border-l-emerald-500 bg-emerald-50/60 text-emerald-800",
  error: "border-l-destructive bg-destructive/5 text-destructive",
}

export function Callout({
  variant = "info",
  icon,
  children,
  action,
  className,
}: CalloutProps) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 border-l-2 py-1.5 pl-2.5 pr-2 text-xs",
        variantStyles[variant],
        className,
      )}
    >
      {icon && (
        <span className="mt-0.5 shrink-0 [&>svg]:size-3">{icon}</span>
      )}
      <div className="min-w-0 flex-1">{children}</div>
      {action && <span className="shrink-0">{action}</span>}
    </div>
  )
}
