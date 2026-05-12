import type { Metadata } from "next"
import "./globals.css"

import { ThemeProvider } from "@/components/theme-provider"
import { Toaster } from "@/components/ui/sonner"
import { UploadSessionProvider } from "@/components/upload-session-provider"
import { AuthProvider } from "@/components/auth-provider"
import { WorkbenchNav } from "@/components/workbench-nav"

export const metadata: Metadata = {
  title: "PDF2PPT",
  description: "上传 PDF 或图片，自动生成可编辑 PPT",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body
        className="font-body antialiased"
      >
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-white focus:text-black focus:rounded"
        >
          跳到主内容
        </a>
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem={false}
          forcedTheme="light"
          disableTransitionOnChange
        >
          <AuthProvider>
            <UploadSessionProvider>
              <WorkbenchNav />
              <main id="main-content">{children}</main>
              <Toaster />
            </UploadSessionProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
