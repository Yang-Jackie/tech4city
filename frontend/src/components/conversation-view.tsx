import * as React from "react"
import {
  AlertCircle,
  ArrowLeft,
  CheckCheck,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { Conversation, Message } from "@/data/models"

type ConversationViewProps = {
  conversation: Conversation
  selectedMessageId?: string
  loading: boolean
  error?: string
  onRetry: () => void
  onBack: () => void
  onSelectMessage: (message: Message) => void
}

function MessageSkeletons() {
  return (
    <div
      className="space-y-4 px-3 py-5 sm:px-5 sm:py-6 lg:px-6"
      aria-label="Loading conversation"
    >
      <Skeleton className="h-20 w-[min(28rem,88%)] rounded-lg bg-muted" />
      <Skeleton className="ml-auto h-20 w-[min(30rem,88%)] rounded-lg bg-muted" />
      <Skeleton className="h-24 w-[min(30rem,88%)] rounded-lg bg-muted" />
    </div>
  )
}

export function ConversationView({
  conversation,
  selectedMessageId,
  loading,
  error,
  onRetry,
  onBack,
  onSelectMessage,
}: ConversationViewProps) {
  const viewportRef = React.useRef<HTMLDivElement>(null)
  const stickToBottomRef = React.useRef(true)
  const previousConversationIdRef = React.useRef(conversation.id)
  const failedCount = conversation.messages.filter(
    (message) => message.analysisState === "failed"
  ).length
  const pendingCount = conversation.messages.filter(
    (message) =>
      message.analysisState === "pending" ||
      message.analysisState === "processing"
  ).length
  const analysisNotice = failedCount
    ? `${failedCount} message analysis failed. Unhighlighted messages are not confirmed safe.`
    : pendingCount
      ? `${pendingCount} message analysis still running. Highlights may change.`
      : undefined

  const handleViewportScroll = React.useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      const viewport = event.currentTarget
      const distanceFromBottom =
        viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight
      stickToBottomRef.current = distanceFromBottom <= 48
    },
    []
  )

  React.useLayoutEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return

    const conversationChanged =
      previousConversationIdRef.current !== conversation.id
    if (conversationChanged) {
      previousConversationIdRef.current = conversation.id
      stickToBottomRef.current = true
    }

    if (stickToBottomRef.current) {
      viewport.scrollTop = viewport.scrollHeight
    }
  }, [
    conversation.flaggedCount,
    conversation.id,
    conversation.messages.length,
    failedCount,
    pendingCount,
  ])

  return (
    <main
      id="conversation"
      className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background"
    >
      <header className="flex h-16 shrink-0 items-center gap-3 border-b bg-card/70 px-3 sm:px-5">
        <Button
          variant="ghost"
          size="icon"
          className="shrink-0 text-muted-foreground lg:hidden"
          onClick={onBack}
          aria-label="Back to conversations"
        >
          <ArrowLeft className="size-5" />
        </Button>
        <Avatar size="lg">
          <AvatarFallback className={conversation.avatarClass}>
            {conversation.initials}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-base font-semibold">
            {conversation.name}
          </h1>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            Last active {conversation.lastActive}
          </p>
        </div>
        {conversation.flaggedCount ? (
          <Badge
            variant="outline"
            className="hidden border-[var(--warning-border)]/50 bg-[var(--warning-surface)] px-2.5 text-[var(--warning-text)] sm:inline-flex"
          >
            <ShieldAlert className="size-3.5" />
            {conversation.flaggedCount} to review
          </Badge>
        ) : (
          <Badge
            variant="outline"
            className="hidden text-muted-foreground sm:inline-flex"
          >
            No flagged messages
          </Badge>
        )}
      </header>

      <ScrollArea
        className="min-h-0 flex-1"
        viewportRef={viewportRef}
        onViewportScroll={handleViewportScroll}
      >
        {error ? (
          <div
            className="flex min-h-full items-center justify-center px-6 py-12 text-center"
            role="alert"
          >
            <div className="max-w-sm">
              <AlertCircle
                className="mx-auto size-5 text-destructive"
                aria-hidden="true"
              />
              <p className="mt-3 font-medium">Could not load messages</p>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                {error}
              </p>
              <Button
                className="mt-4"
                size="sm"
                variant="outline"
                onClick={onRetry}
              >
                <RefreshCw className="size-4" />
                Retry messages
              </Button>
            </div>
          </div>
        ) : loading ? (
          <MessageSkeletons />
        ) : (
          <div className="flex min-h-full w-full flex-col px-3 py-5 sm:px-5 sm:py-6 lg:px-6">
            <div className="mb-5 flex items-center gap-3 text-xs text-muted-foreground">
              <span>Today</span>
              <span className="h-px flex-1 bg-border" />
            </div>
            {analysisNotice ? (
              <div
                className="mb-5 flex items-start gap-2 rounded-lg border border-[var(--warning-border)]/60 bg-[var(--warning-surface)] px-3 py-2.5 text-xs leading-relaxed text-[var(--warning-text)]"
                role="status"
              >
                <ShieldAlert
                  className="mt-0.5 size-3.5 shrink-0"
                  aria-hidden="true"
                />
                <span>{analysisNotice}</span>
              </div>
            ) : null}
            <div
              className="space-y-4"
              role="log"
              aria-label={`Messages with ${conversation.name}`}
            >
              {conversation.messages.map((message) => {
                const outgoing = message.direction === "outgoing"
                const selected = selectedMessageId === message.id
                const safeAnalysis =
                  message.analysis !== undefined && !message.analysis.harmful
                const content = (
                  <>
                    <span className="block text-[0.95rem] leading-relaxed text-foreground">
                      {message.text}
                    </span>
                    <span className="mt-2 flex items-center justify-end gap-1.5 text-xs text-muted-foreground tabular-nums">
                      {message.time}
                      {outgoing ? (
                        <CheckCheck
                          className="size-3.5 text-primary"
                          aria-label="Read"
                        />
                      ) : null}
                    </span>
                  </>
                )

                return (
                  <div
                    key={message.id}
                    className={cn(
                      "flex",
                      outgoing ? "justify-end" : "justify-start"
                    )}
                  >
                    <div className="max-w-[88%] sm:max-w-[34rem]">
                      {message.flagged || safeAnalysis ? (
                        <button
                          type="button"
                          onClick={() => onSelectMessage(message)}
                          className={cn(
                            "w-full rounded-lg border px-4 py-3 text-left transition duration-150 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none active:scale-[0.99]",
                            message.flagged
                              ? "border-[var(--warning-border)] bg-[var(--warning-surface)] hover:bg-[var(--warning-surface-hover)] focus-visible:ring-[var(--warning-border)]"
                              : outgoing
                                ? "border-primary/30 bg-[var(--outgoing-message)] hover:border-primary/60 focus-visible:ring-primary"
                                : "border-border bg-[var(--incoming-message)] hover:border-primary/50 focus-visible:ring-primary",
                            selected &&
                              (message.flagged
                                ? "ring-2 ring-[var(--warning-border)] ring-offset-2 ring-offset-background"
                                : "ring-2 ring-primary ring-offset-2 ring-offset-background")
                          )}
                          aria-label={`${message.text}. ${message.flagged ? "Potential bullying" : "No bullying detected"}. Review analysis.`}
                        >
                          <span
                            className={cn(
                              "mb-2 flex items-center gap-1.5 text-xs font-medium",
                              message.flagged
                                ? "text-[var(--warning-text)]"
                                : "text-primary"
                            )}
                          >
                            {message.flagged ? (
                              <ShieldAlert
                                className="size-3.5"
                                aria-hidden="true"
                              />
                            ) : (
                              <ShieldCheck
                                className="size-3.5"
                                aria-hidden="true"
                              />
                            )}
                            {message.flagged
                              ? "Potential bullying"
                              : "No bullying detected"}
                          </span>
                          {content}
                        </button>
                      ) : (
                        <div
                          className={cn(
                            "rounded-lg border px-4 py-3",
                            outgoing
                              ? "border-primary/30 bg-[var(--outgoing-message)]"
                              : "border-border bg-[var(--incoming-message)]"
                          )}
                        >
                          {content}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </ScrollArea>
    </main>
  )
}
