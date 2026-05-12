import * as React from "react"

import { cn } from "@/lib/utils"

type SelectOption = {
  id: string
  label: string
}

type SelectProps = Omit<React.ComponentProps<"select">, "children"> & {
  options: SelectOption[]
}

function Select({ className, options, ...props }: SelectProps) {
  return (
    <select
      data-slot="select"
      className={cn(
        "h-11 w-full min-w-0 border-b-2 border-input bg-transparent px-3 py-2 font-sans text-sm text-foreground outline-none transition-colors disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        "focus-visible:bg-[#f0f0f0] focus-visible:outline-none focus-visible:ring-0",
        "aria-invalid:border-destructive",
        className
      )}
      {...props}
    >
      {options.map((opt) => (
        <option key={opt.id} value={opt.id}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}

export { Select }
