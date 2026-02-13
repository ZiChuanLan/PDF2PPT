import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 whitespace-nowrap border px-2.5 py-1 font-mono text-[10px] font-medium uppercase tracking-[0.14em] transition-colors overflow-hidden [&>svg]:size-3 [&>svg]:pointer-events-none",
  {
    variants: {
      variant: {
        default: "border-primary bg-primary text-primary-foreground [a&]:hover:bg-foreground",
        secondary: "border-border bg-secondary text-foreground [a&]:hover:bg-muted",
        destructive: "border-destructive bg-destructive text-primary-foreground [a&]:hover:bg-[#a80000]",
        outline: "border-border bg-transparent text-foreground [a&]:hover:bg-muted",
        ghost: "border-transparent bg-transparent text-foreground [a&]:hover:bg-muted",
        link: "border-transparent bg-transparent text-foreground underline-offset-4 decoration-2 decoration-[#cc0000] [a&]:hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
