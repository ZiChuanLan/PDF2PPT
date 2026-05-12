"use client"

import * as React from "react"
import {
  ChevronDownIcon,
  EyeIcon,
  EyeOffIcon,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { HoverHint } from "@/components/ui/hover-hint"
import { Input } from "@/components/ui/input"

export function FieldLabel({
  htmlFor,
  children,
  hint,
  required,
  className,
}: {
  htmlFor?: string
  children: React.ReactNode
  hint?: string
  required?: boolean
  className?: string
}) {
  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      <label className="text-muted-foreground text-xs" htmlFor={htmlFor}>
        {children}
        {required && <span className="text-destructive ml-0.5">*</span>}
      </label>
      {hint ? <HoverHint text={hint} /> : null}
    </div>
  )
}

export function AdvancedReveal({
  show,
  children,
}: {
  show: boolean
  children: React.ReactNode
}) {
  return (
    <div
      aria-hidden={!show}
      className={`grid overflow-hidden transition-[grid-template-rows,opacity,transform,filter] duration-500 ${
        show
          ? "grid-rows-[1fr] translate-y-0 opacity-100 blur-0 ease-[cubic-bezier(0.16,1,0.3,1)]"
          : "pointer-events-none grid-rows-[0fr] -translate-y-1.5 opacity-0 blur-[2px] ease-[cubic-bezier(0.4,0,0.2,1)]"
      }`}
    >
      <div className="min-h-0 overflow-hidden">
        <div
          className={`grid gap-3 transition-[padding,opacity,transform] duration-500 ${
            show ? "translate-y-0 pt-0.5 opacity-100" : "translate-y-1 pt-0 opacity-0"
          }`}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

export function PromptTextarea(props: React.ComponentProps<"textarea">) {
  return (
    <textarea
      {...props}
      className="min-h-[148px] w-full resize-y border border-input bg-transparent px-3 py-2 font-mono text-xs leading-relaxed text-foreground outline-none transition-colors placeholder:text-muted-foreground focus-visible:bg-[#f0f0f0] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
    />
  )
}

export function CollapsibleSection({
  title,
  description,
  hint,
  defaultOpen = false,
  children,
}: {
  title: string
  description?: string
  hint?: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [isOpen, setIsOpen] = React.useState(defaultOpen)

  return (
    <div className="border border-border">
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-left"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div>
          <div className="font-sans text-sm font-semibold uppercase tracking-[0.14em]">
            {title}
          </div>
          {description ? (
            <div className="mt-0.5 text-xs text-muted-foreground">
              {description}
            </div>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {hint ? <HoverHint text={hint} /> : null}
          <ChevronDownIcon
            className={cn(
              "size-4 text-muted-foreground transition-transform",
              isOpen && "rotate-180"
            )}
          />
        </div>
      </button>
      {isOpen ? (
        <div className="grid gap-3 border-t border-border px-4 py-4">
          {children}
        </div>
      ) : null}
    </div>
  )
}

export function SensitiveInput({
  id,
  value,
  onChange,
  onBlur,
  placeholder,
  disabled,
  autoComplete = "off",
  show,
  onToggleShow,
}: {
  id?: string
  value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void
  placeholder?: string
  disabled?: boolean
  autoComplete?: string
  show: boolean
  onToggleShow: () => void
}) {
  return (
    <div className="relative">
      <Input
        id={id}
        type={show ? "text" : "password"}
        autoComplete={autoComplete}
        value={value}
        onChange={onChange}
        onBlur={onBlur}
        placeholder={placeholder}
        disabled={disabled}
        className="pr-10"
      />
      <Button
        type="button"
        variant="ghost"
        size="icon-xs"
        className="absolute right-1 top-1/2 -translate-y-1/2"
        onClick={onToggleShow}
      >
        {show ? (
          <EyeOffIcon className="size-3.5" />
        ) : (
          <EyeIcon className="size-3.5" />
        )}
      </Button>
    </div>
  )
}

export function NumberInputField({
  id,
  label,
  hint,
  value,
  onChange,
  step,
}: {
  id: string
  label: string
  hint?: string
  value: number
  onChange: (v: number) => void
  step?: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <label className="text-muted-foreground text-xs" htmlFor={id}>
          {label}
        </label>
        {hint ? <HoverHint text={hint} /> : null}
      </div>
      <Input
        id={id}
        type="number"
        value={value}
        step={step ?? "1"}
        onChange={(e) => {
          const v = Number(e.target.value)
          if (Number.isFinite(v)) onChange(v)
        }}
        className="h-8 text-xs"
      />
    </div>
  )
}

// Backward-compatible alias
export const FieldBlock = NumberInputField
