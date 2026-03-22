import * as React from "react"
import { ChevronDown } from "lucide-react"
import { type VariantProps } from "class-variance-authority"

import { inputVariants } from "./input"
import { cn } from "../../lib/utils"

export interface SelectProps
  extends React.ComponentProps<"select">,
    VariantProps<typeof inputVariants> {}

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, tone, fieldSize, ...props }, ref) => (
    <div className="relative">
      <select
        ref={ref}
        className={cn(
          inputVariants({ tone, fieldSize }),
          "appearance-none pr-10 text-base",
          className
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
    </div>
  )
)
Select.displayName = "Select"

export { Select }
