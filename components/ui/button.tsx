import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "../../lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus/30 focus-visible:border-focus disabled:pointer-events-none disabled:border-disabled disabled:bg-disabled/20 disabled:text-disabled-foreground disabled:opacity-100 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow hover:bg-primary/90",
        destructive:
          "border border-danger-border bg-danger text-danger-foreground shadow-sm hover:bg-danger/90",
        outline:
          "border border-panel-border bg-app-background text-foreground shadow-sm hover:border-hover hover:bg-hover/60",
        secondary:
          "border border-panel-border bg-surface-muted text-panel-foreground shadow-sm hover:bg-hover",
        ghost: "text-muted-foreground hover:bg-hover/70 hover:text-foreground",
        panel:
          "border border-panel-border bg-panel text-panel-foreground shadow-sm hover:border-hover hover:bg-surface-elevated",
        chip:
          "border border-panel-border bg-surface-overlay/80 text-muted-foreground shadow-sm hover:border-hover hover:bg-hover/60 hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
