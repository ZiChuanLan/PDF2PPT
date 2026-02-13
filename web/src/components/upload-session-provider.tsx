"use client"

import * as React from "react"

type UploadSessionValue = {
  file: File | null
  setFile: React.Dispatch<React.SetStateAction<File | null>>
  pageStartInput: string
  setPageStartInput: React.Dispatch<React.SetStateAction<string>>
  pageEndInput: string
  setPageEndInput: React.Dispatch<React.SetStateAction<string>>
  clearUpload: () => void
}

const UploadSessionContext = React.createContext<UploadSessionValue | null>(null)

export function UploadSessionProvider({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const [file, setFile] = React.useState<File | null>(null)
  const [pageStartInput, setPageStartInput] = React.useState("")
  const [pageEndInput, setPageEndInput] = React.useState("")

  const clearUpload = React.useCallback(() => {
    setFile(null)
    setPageStartInput("")
    setPageEndInput("")
  }, [])

  const value = React.useMemo<UploadSessionValue>(
    () => ({
      file,
      setFile,
      pageStartInput,
      setPageStartInput,
      pageEndInput,
      setPageEndInput,
      clearUpload,
    }),
    [file, pageEndInput, pageStartInput, clearUpload]
  )

  return <UploadSessionContext.Provider value={value}>{children}</UploadSessionContext.Provider>
}

export function useUploadSession(): UploadSessionValue {
  const context = React.useContext(UploadSessionContext)
  if (!context) {
    throw new Error("useUploadSession must be used within UploadSessionProvider")
  }
  return context
}
