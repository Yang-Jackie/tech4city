import { Send, ShieldCheck } from "lucide-react"

import { Button } from "@/components/ui/button"

type TelegramOnboardingProps = {
  onConnect: () => void
}

export function TelegramOnboarding({ onConnect }: TelegramOnboardingProps) {
  return (
    <main
      id="conversation"
      className="flex h-full min-h-0 flex-1 items-center justify-center bg-background px-6 py-10 text-center"
    >
      <div className="flex w-full max-w-xl flex-col items-center">
        <span className="flex size-14 items-center justify-center rounded-2xl border border-primary/35 bg-primary/15 text-primary">
          <Send className="size-6" aria-hidden="true" />
        </span>
        <h1 className="mt-6 text-2xl font-semibold tracking-tight text-balance">
          Connect Telegram to start
        </h1>
        <p className="mt-3 max-w-lg text-sm leading-6 text-pretty text-muted-foreground sm:text-base">
          Tech4City uses TDLib to load your Telegram chat list. Choose a chat to
          review its text messages and analyze new messages as they arrive.
        </p>
        <Button className="mt-6" size="lg" onClick={onConnect}>
          <Send aria-hidden="true" />
          Connect Telegram
        </Button>
        <div className="mt-6 flex max-w-md items-start gap-2.5 text-left text-sm text-muted-foreground">
          <ShieldCheck
            className="mt-0.5 size-4 shrink-0 text-emerald-400"
            aria-hidden="true"
          />
          <p>
            Access is read-only. Tech4City does not send, edit, or delete
            Telegram messages.
          </p>
        </div>
      </div>
    </main>
  )
}
