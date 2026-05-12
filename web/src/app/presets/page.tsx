"use client"

import * as React from "react"
import Link from "next/link"
import { ArrowLeftIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { PresetManager } from "@/components/preset-manager"
import { loadStoredSettings } from "@/lib/settings"

export default function PresetsPage() {
  const [currentSettings, setCurrentSettings] = React.useState(() => loadStoredSettings())

  React.useEffect(() => {
    setCurrentSettings(loadStoredSettings())
  }, [])

  return (
    <div className="min-h-dvh bg-background">
      <div className="mx-auto w-full max-w-screen-xl px-4 py-6 md:py-10">
        <header className="flex items-center justify-between py-4">
          <div>
            <h1 className="font-serif text-2xl leading-tight tracking-tight">预设管理</h1>
            <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Preset Management
            </div>
          </div>
          <Button type="button" variant="ghost" size="sm" asChild>
            <Link href="/">
              <ArrowLeftIcon className="size-4" />
              返回工作台
            </Link>
          </Button>
        </header>

        <main className="mt-6">
          <PresetManager currentSettings={currentSettings} />
        </main>
      </div>
    </div>
  )
}
