"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

type PasswordStrength = "weak" | "fair" | "good" | "strong"

type PasswordStrengthMeterProps = {
  password: string
  className?: string
}

function calculatePasswordStrength(password: string): PasswordStrength {
  if (password.length === 0) return "weak"

  let score = 0

  // Length scoring
  if (password.length >= 8) score += 1
  if (password.length >= 12) score += 1
  if (password.length >= 16) score += 1

  // Character variety scoring
  if (/[a-z]/.test(password)) score += 1 // lowercase
  if (/[A-Z]/.test(password)) score += 1 // uppercase
  if (/[0-9]/.test(password)) score += 1 // numbers
  if (/[^a-zA-Z0-9]/.test(password)) score += 1 // special chars

  // Map score to strength
  if (score <= 2) return "weak"
  if (score <= 4) return "fair"
  if (score <= 6) return "good"
  return "strong"
}

function getStrengthConfig(strength: PasswordStrength) {
  switch (strength) {
    case "weak":
      return {
        label: "弱",
        color: "bg-red-500",
        textColor: "text-red-600",
        width: "w-1/4",
      }
    case "fair":
      return {
        label: "一般",
        color: "bg-amber-500",
        textColor: "text-amber-600",
        width: "w-2/4",
      }
    case "good":
      return {
        label: "良好",
        color: "bg-emerald-500",
        textColor: "text-emerald-600",
        width: "w-3/4",
      }
    case "strong":
      return {
        label: "强",
        color: "bg-emerald-600",
        textColor: "text-emerald-700",
        width: "w-full",
      }
  }
}

export function PasswordStrengthMeter({ password, className }: PasswordStrengthMeterProps) {
  const strength = calculatePasswordStrength(password)
  const config = getStrengthConfig(strength)

  if (password.length === 0) {
    return null
  }

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full transition-all duration-300",
            config.color,
            config.width
          )}
        />
      </div>
      <div className="flex items-center justify-between text-xs">
        <span className={cn("font-medium", config.textColor)}>
          密码强度: {config.label}
        </span>
        <span className="text-muted-foreground">
          {password.length >= 8 ? "✓" : "✗"} 至少 8 个字符
        </span>
      </div>
    </div>
  )
}
