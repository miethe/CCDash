import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "../../lib/utils"

export const inputVariants = cva(
  "flex w-full rounded-lg border text-foreground shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus/30 focus-visible:border-focus disabled:cursor-not-allowed disabled:border-disabled disabled:bg-disabled/20 disabled:text-disabled-foreground disabled:opacity-100 md:text-sm",
  {
    variants: {
      tone: {
        default: "border-panel-border bg-surface-overlay/70",
        panel: "border-panel-border bg-panel",
        muted: "border-panel-border bg-surface-muted",
      },
      fieldSize: {
        default: "h-10 px-3 py-2",
        sm: "h-8 px-2.5 py-1.5 text-sm",
        lg: "h-11 px-4 py-3",
      },
    },
    defaultVariants: {
      tone: "default",
      fieldSize: "default",
    },
  }
)

export interface InputProps
  extends React.ComponentProps<"input">,
    VariantProps<typeof inputVariants> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, tone, fieldSize, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          inputVariants({ tone, fieldSize }),
          "text-base",
          className,
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
