import * as React from "react"
import { LoaderCircle, Send, ShieldCheck } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import type {
  TelegramLoginAction,
  TelegramLoginStatus,
} from "@/data/telegram-api"

type TelegramLoginDialogProps = {
  open: boolean
  status?: TelegramLoginStatus
  busy: boolean
  error?: string
  onOpenChange: (open: boolean) => void
  onStart: () => void
  onSubmit: (action: TelegramLoginAction, value: string) => void
  onLogout: () => void
}

type LoginField = {
  action: TelegramLoginAction
  label: string
  placeholder: string
  buttonLabel: string
  type: React.HTMLInputTypeAttribute
  autoComplete: string
  inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"]
}

const LOGIN_FIELDS: Partial<Record<string, LoginField>> = {
  wait_phone: {
    action: "phone",
    label: "Phone number",
    placeholder: "+84 90 123 4567",
    buttonLabel: "Send code",
    type: "tel",
    autoComplete: "tel",
    inputMode: "tel",
  },
  wait_code: {
    action: "code",
    label: "Telegram code",
    placeholder: "Enter the code",
    buttonLabel: "Verify code",
    type: "text",
    autoComplete: "one-time-code",
    inputMode: "numeric",
  },
  wait_password: {
    action: "password",
    label: "Two-step verification password",
    placeholder: "Enter your password",
    buttonLabel: "Continue",
    type: "password",
    autoComplete: "current-password",
  },
}

function statusDescription(status?: TelegramLoginStatus): string {
  if (!status) {
    return "Connect Telegram to import regular text conversations to this device."
  }

  switch (status.status) {
    case "starting":
      return "Starting a secure Telegram session."
    case "wait_phone":
      return "Use your full international phone number. It is sent directly to Telegram."
    case "wait_code":
      return status.code_type
        ? `Enter the ${status.code_type} code sent by Telegram.`
        : "Enter the login code sent by Telegram."
    case "wait_password":
      return status.password_hint
        ? `Two-step verification is enabled. Hint: ${status.password_hint}`
        : "Enter your Telegram two-step verification password."
    case "ready":
      return "Connected. New text messages will be analyzed as they arrive."
    case "logging_out":
      return "Closing the Telegram session."
    case "registration_required":
      return "This account must be registered in the official Telegram app first."
    case "unsupported":
      return "Telegram requested a login step this app does not support."
    default:
      return "Continue the Telegram login from this device."
  }
}

export function TelegramLoginDialog({
  open,
  status,
  busy,
  error,
  onOpenChange,
  onStart,
  onSubmit,
  onLogout,
}: TelegramLoginDialogProps) {
  const field = status ? LOGIN_FIELDS[status.status] : undefined
  const [value, setValue] = React.useState("")

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const submittedValue = field?.action === "password" ? value : value.trim()
    if (!field || !submittedValue) return
    setValue("")
    onSubmit(field.action, submittedValue)
  }

  const waiting =
    busy || status?.status === "starting" || status?.status === "logging_out"
  const connected = status?.status === "ready"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect Telegram</DialogTitle>
          <DialogDescription>{statusDescription(status)}</DialogDescription>
        </DialogHeader>

        {connected ? (
          <div className="flex items-center gap-3 rounded-lg border bg-secondary/55 p-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
              <Send className="size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">
                {status.display_name || "Telegram account"}
              </p>
              <p className="text-xs text-muted-foreground">
                Telegram conversations connected
              </p>
            </div>
            <ShieldCheck
              className="ml-auto size-4 shrink-0 text-emerald-400"
              aria-label="Connected"
            />
          </div>
        ) : null}

        {field ? (
          <form className="grid gap-4" onSubmit={submit}>
            <div className="grid gap-2">
              <label
                htmlFor="telegram-login-value"
                className="text-sm font-medium"
              >
                {field.label}
              </label>
              <Input
                id="telegram-login-value"
                value={value}
                onChange={(event) => setValue(event.target.value)}
                type={field.type}
                inputMode={field.inputMode}
                autoComplete={field.autoComplete}
                placeholder={field.placeholder}
                disabled={waiting}
                aria-invalid={Boolean(error)}
                autoFocus
              />
            </div>
            {error ? (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            ) : null}
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={onLogout}
                disabled={waiting}
              >
                Cancel login
              </Button>
              <Button type="submit" disabled={waiting || !value.trim()}>
                {waiting ? (
                  <LoaderCircle className="animate-spin" aria-hidden="true" />
                ) : null}
                {field.buttonLabel}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <>
            {error ? (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            ) : null}
            <DialogFooter>
              {connected ? (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={onLogout}
                    disabled={waiting}
                  >
                    Log out
                  </Button>
                  <Button type="button" onClick={() => onOpenChange(false)}>
                    Done
                  </Button>
                </>
              ) : status && !waiting ? (
                <Button type="button" variant="outline" onClick={onLogout}>
                  Close session
                </Button>
              ) : (
                <Button type="button" onClick={onStart} disabled={waiting}>
                  {waiting ? (
                    <LoaderCircle className="animate-spin" aria-hidden="true" />
                  ) : (
                    <Send aria-hidden="true" />
                  )}
                  {waiting ? "Waiting for Telegram" : "Start login"}
                </Button>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
