import * as React from "react"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "w-full min-w-0 border-b-2 border-input bg-transparent px-3 py-2 font-mono text-sm text-foreground outline-none transition-colors file:inline-flex file:h-7 file:border-0 file:bg-transparent file:font-mono file:text-xs file:uppercase file:tracking-[0.12em] placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        "focus-visible:bg-[#f0f0f0] focus-visible:outline-none focus-visible:ring-0",
        "aria-invalid:border-destructive",
        className
      )}
      {...props}
    />
  )
}

export { Input }
