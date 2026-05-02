"use client"

import * as React from "react"
import Link from "next/link"
import { ChevronDownIcon, LogOutIcon, ShieldIcon, UserIcon } from "lucide-react"

import { useAuth } from "@/components/auth-provider"
import { apiFetch } from "@/lib/api"
import { getAvatarUrl, isAdmin } from "@/lib/auth"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

export function UserMenu() {
  const { user, isLoading, logout } = useAuth()
  const [isOpen, setIsOpen] = React.useState(false)
  const [deployMode, setDeployMode] = React.useState<string>("self")
  const menuRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    void (async () => {
      try {
        const res = await apiFetch("/config/deploy-mode")
        if (res.ok) {
          const data = await res.json().catch(() => null)
          if (data?.mode) setDeployMode(data.mode)
        }
      } catch {
        // Ignore - default to self
      }
    })()
  }, [])

  // Close menu when clicking outside
  React.useEffect(() => {
    if (!isOpen) return

    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [isOpen])

  // Close menu on escape key
  React.useEffect(() => {
    if (!isOpen) return

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false)
      }
    }

    document.addEventListener("keydown", handleEscape)
    return () => document.removeEventListener("keydown", handleEscape)
  }, [isOpen])

  if (isLoading) {
    return (
      <div className="flex items-center gap-2">
        <div className="size-8 animate-pulse bg-muted" />
        <div className="hidden h-4 w-16 animate-pulse bg-muted sm:block" />
      </div>
    )
  }

  if (!user) {
    return (
      <Button type="button" variant="outline" size="sm" asChild>
        <Link href="/login">登录</Link>
      </Button>
    )
  }

  const avatarUrl = getAvatarUrl(user.avatar_url, 32)
  const userIsAdmin = isAdmin(user)

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={cn(
          "flex items-center gap-2 border px-2 py-1.5 transition-colors",
          isOpen
            ? "border-border bg-secondary"
            : "border-border/70 bg-background hover:bg-muted/50"
        )}
        aria-expanded={isOpen}
        aria-haspopup="true"
        aria-label="用户菜单"
      >
        {avatarUrl ? (
          <img
            src={avatarUrl}
            alt={user.username}
            className="size-6 border border-border"
            width={24}
            height={24}
          />
        ) : (
          <UserIcon className="size-4 text-muted-foreground" />
        )}
        <span className="hidden font-mono text-xs uppercase tracking-[0.12em] sm:block">
          {user.username}
        </span>
        <ChevronDownIcon
          className={cn(
            "size-3 text-muted-foreground transition-transform",
            isOpen && "rotate-180"
          )}
        />
      </button>

      {isOpen ? (
        <div className="absolute right-0 top-full z-50 mt-1 min-w-48 border border-border bg-background shadow-lg">
          <div className="border-b border-border px-3 py-2">
            <div className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
              已登录
            </div>
            <div className="mt-1 font-medium">{user.username}</div>
            {user.name ? (
              <div className="text-xs text-muted-foreground">{user.name}</div>
            ) : null}
          </div>

          <div className="py-1">
            {userIsAdmin ? (
              <Link
                href="/admin"
                onClick={() => setIsOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-muted/50"
              >
                <ShieldIcon className="size-4 text-muted-foreground" />
                管理后台
              </Link>
            ) : deployMode === "public" ? (
              <Link
                href="/manage"
                onClick={() => setIsOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-muted/50"
              >
                <UserIcon className="size-4 text-muted-foreground" />
                账号管理
              </Link>
            ) : null}

            <button
              type="button"
              onClick={() => {
                setIsOpen(false)
                void logout()
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-muted/50"
            >
              <LogOutIcon className="size-4 text-muted-foreground" />
              退出登录
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
