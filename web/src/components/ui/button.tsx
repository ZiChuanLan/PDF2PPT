import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex min-h-[44px] min-w-[44px] items-center justify-center gap-2 whitespace-nowrap border border-transparent px-4 py-2 font-sans text-xs font-semibold uppercase tracking-[0.14em] transition-all duration-200 ease-out motion-safe:transform-gpu motion-safe:hover:-translate-y-px motion-safe:active:translate-y-0 motion-safe:active:scale-[0.985] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-primary bg-primary text-primary-foreground hover:bg-background hover:text-foreground hover:border-border",
        destructive:
          "border-destructive bg-destructive text-primary-foreground hover:bg-background hover:text-destructive hover:border-destructive",
        outline:
          "border-border bg-transparent text-foreground hover:bg-foreground hover:text-background",
        secondary: "border-border bg-secondary text-foreground hover:bg-muted",
        ghost: "border-transparent bg-transparent text-foreground hover:border-border hover:bg-muted",
        link: "border-transparent bg-transparent text-foreground underline-offset-4 decoration-2 decoration-[#cc0000] hover:underline",
      },
      size: {
        default: "h-11 has-[>svg]:px-3",
        xs: "h-8 min-h-8 min-w-8 gap-1 px-2 text-[10px] tracking-[0.12em] has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-9 min-h-9 gap-1.5 px-3 text-[11px] has-[>svg]:px-2.5",
        lg: "h-12 px-6 text-sm has-[>svg]:px-4",
        icon: "size-11",
        "icon-xs": "size-8 min-h-8 min-w-8 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-9 min-h-9 min-w-9",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
