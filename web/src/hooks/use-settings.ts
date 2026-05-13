"use client"

import * as React from "react"
import { apiFetch } from "@/lib/api"
import { toast } from "sonner"
import {
  SETTINGS_STORAGE_KEY,
  defaultSettings,
  loadStoredSettings,
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
  const saveErrorShownRef = React.useRef(false)

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
      .catch((e) => {
        console.error("Failed to fetch deploy mode:", e)
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
        // Self mode: load from localStorage with validation and migration
        if (mounted) setSettings(loadStoredSettings())
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
        } catch (e) {
          console.error("Failed to load preferences:", e)
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
        setLastSavedAt(Date.now())
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
        })
          .then((res) => {
            if (res.ok) {
              setLastSavedAt(Date.now())
              saveErrorShownRef.current = false
            }
          })
          .catch((e) => {
            console.error("Failed to save settings:", e)
            // Show toast only once per save cycle to avoid spamming
            if (!saveErrorShownRef.current) {
              saveErrorShownRef.current = true
              toast.error("自动保存设置失败，请检查网络连接或手动保存")
            }
          })
      }
    }, 500)
    return () => window.clearTimeout(timer)
  }, [settings, settingsHydrated, deployMode])

  const save = React.useCallback(async () => {
    if (deployMode === "self") {
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))
      setLastSavedAt(Date.now())
    } else {
      const prefs: Record<string, string> = {}
      for (const [key, value] of Object.entries(settings)) {
        if (!isSensitiveKey(key)) {
          prefs[key] = String(value)
        }
      }
      const res = await apiFetch("/user/preferences", {
        method: "PUT",
        body: JSON.stringify({ preferences: prefs }),
      })
      if (!res.ok) {
        throw new Error("保存设置失败")
      }
      setLastSavedAt(Date.now())
    }
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
