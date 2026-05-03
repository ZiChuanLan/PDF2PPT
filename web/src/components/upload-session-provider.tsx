"use client"

import * as React from "react"

type UploadFileEntry = {
  file: File
  pageStartInput: string
  pageEndInput: string
}

type UploadSessionValue = {
  files: UploadFileEntry[]
  file: File | null
  fileCount: number
  pageStartInput: string
  pageEndInput: string
  setPageStartInput: React.Dispatch<React.SetStateAction<string>>
  setPageEndInput: React.Dispatch<React.SetStateAction<string>>
  addFiles: (newFiles: File[]) => void
  removeFile: (index: number) => void
  clearUpload: () => void
}

const UploadSessionContext = React.createContext<UploadSessionValue | null>(null)

export function UploadSessionProvider({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const [files, setFiles] = React.useState<UploadFileEntry[]>([])
  const [pageStartInput, setPageStartInput] = React.useState("")
  const [pageEndInput, setPageEndInput] = React.useState("")

  const addFiles = React.useCallback((newFiles: File[]) => {
    setFiles((prev) => {
      const existingNames = new Set(prev.map((e) => e.file.name))
      const entries: UploadFileEntry[] = []
      for (const f of newFiles) {
        if (!existingNames.has(f.name)) {
          entries.push({ file: f, pageStartInput: "", pageEndInput: "" })
          existingNames.add(f.name)
        }
      }
      return [...prev, ...entries]
    })
  }, [])

  const removeFile = React.useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const clearUpload = React.useCallback(() => {
    setFiles([])
    setPageStartInput("")
    setPageEndInput("")
  }, [])

  const value = React.useMemo<UploadSessionValue>(
    () => ({
      files,
      file: files.length > 0 ? files[0].file : null,
      fileCount: files.length,
      pageStartInput,
      pageEndInput,
      setPageStartInput,
      setPageEndInput,
      addFiles,
      removeFile,
      clearUpload,
    }),
    [files, pageEndInput, pageStartInput, addFiles, removeFile, clearUpload]
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
