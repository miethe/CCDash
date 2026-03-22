import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "../../lib/utils"

export const surfaceVariants = cva(
  "rounded-xl border text-panel-foreground",
  {
    variants: {
      tone: {
        panel: "border-panel-border bg-panel",
        muted: "border-panel-border bg-surface-muted",
        elevated: "border-panel-border bg-surface-elevated",
        overlay: "border-panel-border bg-surface-overlay/95",
      },
      padding: {
        none: "",
        sm: "p-3",
        md: "p-4",
        lg: "p-6",
      },
      shadow: {
        none: "",
        sm: "shadow-sm",
        md: "shadow-md",
        viewer: "shadow-[var(--viewer-shell-shadow)]",
      },
    },
    defaultVariants: {
      tone: "panel",
      padding: "md",
      shadow: "sm",
    },
  }
)

export interface SurfaceProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof surfaceVariants> {}

export const Surface = React.forwardRef<HTMLDivElement, SurfaceProps>(
  ({ className, tone, padding, shadow, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(surfaceVariants({ tone, padding, shadow }), className)}
      {...props}
    />
  )
)
Surface.displayName = "Surface"

export const alertSurfaceVariants = cva(
  "rounded-xl border px-4 py-3 text-sm",
  {
    variants: {
      intent: {
        neutral: "border-panel-border bg-surface-overlay/80 text-panel-foreground",
        info: "border-info-border bg-info/10 text-info-foreground",
        success: "border-success-border bg-success/10 text-success-foreground",
        warning: "border-warning-border bg-warning/10 text-warning-foreground",
        danger: "border-danger-border bg-danger/10 text-danger-foreground",
      },
    },
    defaultVariants: {
      intent: "neutral",
    },
  }
)

export interface AlertSurfaceProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertSurfaceVariants> {}

export const AlertSurface = React.forwardRef<HTMLDivElement, AlertSurfaceProps>(
  ({ className, intent, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(alertSurfaceVariants({ intent }), className)}
      {...props}
    />
  )
)
AlertSurface.displayName = "AlertSurface"

export const controlRowVariants = cva(
  "flex flex-wrap rounded-lg border border-panel-border bg-surface-overlay/70 text-panel-foreground",
  {
    variants: {
      density: {
        default: "items-center gap-3 px-3 py-3",
        compact: "items-center gap-2 px-2.5 py-2",
        relaxed: "items-start gap-4 px-4 py-3.5",
      },
    },
    defaultVariants: {
      density: "default",
    },
  }
)

export interface ControlRowProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof controlRowVariants> {}

export const ControlRow = React.forwardRef<HTMLDivElement, ControlRowProps>(
  ({ className, density, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(controlRowVariants({ density }), className)}
      {...props}
    />
  )
)
ControlRow.displayName = "ControlRow"
