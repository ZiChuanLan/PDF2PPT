"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

type DeployMode = "self" | "public"

type DeployModeComparisonProps = {
  selectedMode: DeployMode
  onModeChange: (mode: DeployMode) => void
  className?: string
}

export function DeployModeComparison({
  selectedMode,
  onModeChange,
  className,
}: DeployModeComparisonProps) {
  return (
    <div className={cn("space-y-4", className)}>
      <div className="grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={() => onModeChange("self")}
          className={cn(
            "rounded-lg border-2 p-4 text-left transition-colors",
            selectedMode === "self"
              ? "border-foreground bg-muted/50"
              : "border-border hover:border-muted-foreground/50"
          )}
        >
          <h3 className="font-medium">自用模式</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            适合个人使用。登录后自动保持会话，无需每次输入密码。
          </p>
        </button>
        <button
          type="button"
          onClick={() => onModeChange("public")}
          className={cn(
            "rounded-lg border-2 p-4 text-left transition-colors",
            selectedMode === "public"
              ? "border-foreground bg-muted/50"
              : "border-border hover:border-muted-foreground/50"
          )}
        >
          <h3 className="font-medium">公开模式</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            适合团队或公开部署。支持多用户注册、邀请码和配额管理。
          </p>
        </button>
      </div>

      {/* Comparison table */}
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="px-3 py-2 text-left font-medium">功能</th>
              <th className="px-3 py-2 text-center font-medium">自用模式</th>
              <th className="px-3 py-2 text-center font-medium">公开模式</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            <tr>
              <td className="px-3 py-2 text-muted-foreground">用户注册</td>
              <td className="px-3 py-2 text-center">✗</td>
              <td className="px-3 py-2 text-center">✓</td>
            </tr>
            <tr>
              <td className="px-3 py-2 text-muted-foreground">邀请码系统</td>
              <td className="px-3 py-2 text-center">✗</td>
              <td className="px-3 py-2 text-center">✓</td>
            </tr>
            <tr>
              <td className="px-3 py-2 text-muted-foreground">配额管理</td>
              <td className="px-3 py-2 text-center">✗</td>
              <td className="px-3 py-2 text-center">✓</td>
            </tr>
            <tr>
              <td className="px-3 py-2 text-muted-foreground">自动保持登录</td>
              <td className="px-3 py-2 text-center">✓</td>
              <td className="px-3 py-2 text-center">✗</td>
            </tr>
            <tr>
              <td className="px-3 py-2 text-muted-foreground">适用场景</td>
              <td className="px-3 py-2 text-center text-muted-foreground">个人</td>
              <td className="px-3 py-2 text-center text-muted-foreground">团队/公开</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p className="text-xs text-muted-foreground">
        提示：部署模式可在管理后台修改。
      </p>
    </div>
  )
}
