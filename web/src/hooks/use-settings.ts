"use client"

import * as React from "react"
import { apiFetch } from "@/lib/api"
import {
  SETTINGS_STORAGE_KEY,
  defaultSettings,
  type Settings,
} from "@/lib/settings"

export type DeployMode = "self" | "public"

// API key fields that should be disabled in public mode
export const SENSITIVE_KEYS: ReadonlySet<keyof Settings> = new Set([
  "openaiApiKey",
  "claudeApiKey",
  "mineruApiToken",
  "ocrBaiduApiKey",
  "ocrBaiduSecretKey",
  "ocrAiApiKey",
])

function isSensitiveKey(key: string): boolean {
  return SENSITIVE_KEYS.has(key as keyof Settings)
}

function mergeSettings(
  base: Settings,
  overrides: Record<string, string | null | undefined>,
): Settings {
  const result = { ...base }
  for (const [key, value] of Object.entries(overrides)) {
    if (key in result && value !== null && value !== undefined) {
      const target = result[key as keyof Settings]
      if (typeof target === "boolean") {
        ;(result as Record<string, unknown>)[key] = value === "true" || value === "1"
      } else {
        ;(result as Record<string, unknown>)[key] = value
      }
    }
  }
  return result
}

export function useSettings() {
  const [settings, setSettings] = React.useState<Settings>(defaultSettings)
  const [settingsHydrated, setSettingsHydrated] = React.useState(false)
  const [deployMode, setDeployMode] = React.useState<DeployMode>("self")
  const [lastSavedAt, setLastSavedAt] = React.useState<number | null>(null)

  // Load deploy mode
  React.useEffect(() => {
    let mounted = true
    void apiFetch("/config/deploy-mode")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch deploy mode")
        return res.json()
      })
      .then((data: { mode: DeployMode }) => {
        if (mounted) setDeployMode(data.mode)
      })
      .catch(() => {
        // Default to self on error
        if (mounted) setDeployMode("self")
      })
    return () => { mounted = false }
  }, [])

  // Load settings based on deploy mode
  React.useEffect(() => {
    let mounted = true

    async function load() {
      if (deployMode === "self") {
        // Self mode: load from localStorage
        try {
          const raw = localStorage.getItem(SETTINGS_STORAGE_KEY)
          if (raw) {
            const parsed = JSON.parse(raw) as Partial<Settings>
            if (mounted) setSettings({ ...defaultSettings, ...parsed })
          }
        } catch {
          // Ignore parse errors
        }
        if (mounted) setSettingsHydrated(true)
      } else {
        // Public mode: load user_preferences from API
        try {
          const prefRes = await apiFetch("/user/preferences")
          if (!prefRes.ok) throw new Error("Failed to fetch preferences")
          const prefData: { preferences: Record<string, string | null> } = await prefRes.json()

          // Start with defaults
          let merged = { ...defaultSettings }

          // Apply user preferences
          merged = mergeSettings(merged, prefData.preferences)

          if (mounted) setSettings(merged)
        } catch {
          // Fallback to defaults
        }
        if (mounted) setSettingsHydrated(true)
      }
    }

    // Wait for deploy mode to be loaded
    if (deployMode) {
      void load()
    }

    return () => { mounted = false }
  }, [deployMode])

  // Auto-save
  React.useEffect(() => {
    if (!settingsHydrated) return
    const timer = window.setTimeout(() => {
      if (deployMode === "self") {
        localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))
      } else {
        // Public mode: save non-sensitive keys to user_preferences
        const prefs: Record<string, string> = {}
        for (const [key, value] of Object.entries(settings)) {
          if (!isSensitiveKey(key)) {
            prefs[key] = String(value)
          }
        }
        void apiFetch("/user/preferences", {
          method: "PUT",
          body: JSON.stringify({ preferences: prefs }),
        }).catch(() => {
          // Silently fail - will retry on next change
        })
      }
      setLastSavedAt(Date.now())
    }, 500)
    return () => window.clearTimeout(timer)
  }, [settings, settingsHydrated, deployMode])

  const save = React.useCallback(() => {
    if (deployMode === "self") {
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))
    } else {
      const prefs: Record<string, string> = {}
      for (const [key, value] of Object.entries(settings)) {
        if (!isSensitiveKey(key)) {
          prefs[key] = String(value)
        }
      }
      void apiFetch("/user/preferences", {
        method: "PUT",
        body: JSON.stringify({ preferences: prefs }),
      }).catch(() => { /* ignore */ })
    }
    setLastSavedAt(Date.now())
  }, [settings, deployMode])

  const clear = React.useCallback(() => {
    localStorage.removeItem(SETTINGS_STORAGE_KEY)
    setSettings(defaultSettings)
    setLastSavedAt(null)
  }, [])

  const isPublicMode = deployMode === "public"

  return {
    settings,
    setSettings,
    settingsHydrated,
    deployMode,
    isPublicMode,
    lastSavedAt,
    save,
    clear,
  }
}
