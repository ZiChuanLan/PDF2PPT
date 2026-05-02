"use client"

import * as React from "react"
import { apiFetch } from "@/lib/api"
import { normalizeUser, type User } from "@/lib/auth"

type AuthContextValue = {
  user: User | null
  isLoading: boolean
  error: string | null
  refetch: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = React.createContext<AuthContextValue | null>(null)

export function AuthProvider({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const [user, setUser] = React.useState<User | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const fetchUser = React.useCallback(async (retries = 2) => {
    try {
      const response = await apiFetch("/auth/me")
      if (!response.ok) {
        if (response.status === 401 && retries > 0) {
          await new Promise((r) => setTimeout(r, 500))
          return fetchUser(retries - 1)
        }
        if (response.status === 401) {
          setUser(null)
          setError(null)
          return
        }
        throw new Error("Failed to fetch user info")
      }
      const data = await response.json().catch(() => null)
      const normalized = normalizeUser(data)
      setUser(normalized)
      setError(null)
    } catch {
      // Silently fail - user is not authenticated
      setUser(null)
      setError(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const logout = React.useCallback(async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST" })
    } catch {
      // Ignore logout errors
    }
    localStorage.setItem("userLoggedOut", "true")
    setUser(null)
    window.location.href = "/login"
  }, [])

  React.useEffect(() => {
    void fetchUser()
  }, [fetchUser])

  const value = React.useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      error,
      refetch: fetchUser,
      logout,
    }),
    [user, isLoading, error, fetchUser, logout]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider")
  }
  return context
}
