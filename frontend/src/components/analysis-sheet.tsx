import { BarChart3, Clock3, Info, ShieldAlert, ShieldCheck } from "lucide-react"

import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { useMediaQuery } from "@/hooks/use-media-query"
import type { Message } from "@/data/models"

type AnalysisSheetProps = {
  open: boolean
  message?: Message
  onOpenChange: (open: boolean) => void
}

type AnalysisRowProps = {
  icon: React.ReactNode
  label: string
  value: string
}

function AnalysisRow({ icon, label, value }: AnalysisRowProps) {
  return (
    <div className="flex items-start gap-3 py-4">
      <span className="mt-0.5 text-muted-foreground" aria-hidden="true">
        {icon}
      </span>
      <div>
        <p className="font-medium text-foreground">{value}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
          {label}
        </p>
      </div>
    </div>
  )
}

export function AnalysisSheet({
  open,
  message,
  onOpenChange,
}: AnalysisSheetProps) {
  const mobile = useMediaQuery("(max-width: 639px)")
  const analysis = message?.analysis
  const harmful = analysis?.harmful === true

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side={mobile ? "bottom" : "right"}
        className="max-h-[92dvh] gap-0 border-border bg-popover p-0 sm:max-h-none sm:max-w-[26rem]"
      >
        <SheetHeader className="border-b px-5 py-4 pr-14 sm:px-6 sm:py-5">
          <SheetTitle className="text-lg font-semibold">Analysis</SheetTitle>
          <SheetDescription className="sr-only">
            Review the analysis for the selected message.
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="min-h-0 flex-1">
          {message && analysis ? (
            <div className="space-y-6 px-5 py-5 sm:px-6">
              <section aria-labelledby="selected-message-heading">
                <h2
                  id="selected-message-heading"
                  className="text-sm font-semibold"
                >
                  Selected message
                </h2>
                <div
                  className={
                    harmful
                      ? "mt-3 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-surface)] p-4"
                      : "mt-3 rounded-lg border border-primary/30 bg-primary/10 p-4"
                  }
                >
                  <div className="flex items-start gap-3">
                    <p className="flex-1 text-sm leading-relaxed text-foreground">
                      {message.text}
                    </p>
                    {harmful ? (
                      <ShieldAlert
                        className="mt-0.5 size-5 shrink-0 text-[var(--warning-icon)]"
                        aria-hidden="true"
                      />
                    ) : (
                      <ShieldCheck
                        className="mt-0.5 size-5 shrink-0 text-primary"
                        aria-hidden="true"
                      />
                    )}
                  </div>
                  <time className="mt-3 block text-xs text-muted-foreground tabular-nums">
                    {message.time}
                  </time>
                </div>
              </section>

              <section aria-label="Analysis result">
                <div className="flex items-center gap-3">
                  <span
                    className={
                      harmful
                        ? "flex size-9 items-center justify-center rounded-full border border-[var(--warning-border)] text-[var(--warning-icon)]"
                        : "flex size-9 items-center justify-center rounded-full border border-primary/40 text-primary"
                    }
                  >
                    {harmful ? (
                      <ShieldAlert className="size-5" aria-hidden="true" />
                    ) : (
                      <ShieldCheck className="size-5" aria-hidden="true" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      className={
                        harmful
                          ? "font-semibold text-[var(--warning-text)]"
                          : "font-semibold text-foreground"
                      }
                    >
                      {analysis.category}
                    </p>
                    <p
                      className={
                        harmful
                          ? "mt-0.5 text-xs text-[var(--warning-text)]/80"
                          : "mt-0.5 text-xs text-muted-foreground"
                      }
                    >
                      {harmful
                        ? `${analysis.severity} severity`
                        : "No harmful content detected"}
                    </p>
                  </div>
                </div>
              </section>

              <section aria-labelledby="analysis-explanation-heading">
                <h2
                  id="analysis-explanation-heading"
                  className="text-sm font-semibold"
                >
                  {harmful ? "Why it may be harmful" : "Why it was not flagged"}
                </h2>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">
                  {analysis.explanation}
                </p>
              </section>

              <Separator />

              <section aria-label="Analysis metadata">
                {analysis.confidence !== undefined ? (
                  <>
                    <AnalysisRow
                      icon={<BarChart3 className="size-5" />}
                      value={`${analysis.confidence}% confidence`}
                      label="Confidence"
                    />
                    <Separator />
                  </>
                ) : null}
                <AnalysisRow
                  icon={<Clock3 className="size-5" />}
                  value={`Analyzed ${analysis.analyzedAt}`}
                  label="Analysis complete"
                />
              </section>

              <div className="flex gap-3 rounded-lg border border-primary/25 bg-primary/10 p-4 text-primary-foreground">
                <Info
                  className="mt-0.5 size-5 shrink-0 text-primary"
                  aria-hidden="true"
                />
                <p className="text-sm leading-relaxed text-foreground">
                  Model output, not a final judgment. A person should review
                  context before taking action.
                </p>
              </div>
            </div>
          ) : (
            <div className="px-6 py-12 text-center">
              <p className="font-medium">No analysis selected</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Select a message with analysis to review its result.
              </p>
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
