import { RefreshCw, Search, ShieldAlert } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Conversation } from "@/data/models";
import { cn } from "@/lib/utils";

type ChatListProps = {
  conversations: Conversation[];
  activeId: string;
  query: string;
  flaggedOnly: boolean;
  loading: boolean;
  error?: string;
  onQueryChange: (query: string) => void;
  onFlaggedOnlyChange: (active: boolean) => void;
  onSelect: (id: string) => void;
  onRetry: () => void;
};

function ChatListSkeleton() {
  return (
    <div className="space-y-2 p-2" aria-label="Loading conversations">
      {Array.from({ length: 5 }, (_, index) => (
        <div
          key={index}
          className="flex min-h-20 items-center gap-3 px-3 py-2.5"
        >
          <Skeleton className="size-10 shrink-0 rounded-full bg-muted" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-2/3 bg-muted" />
            <Skeleton className="h-3 w-full bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ChatList({
  conversations,
  activeId,
  query,
  flaggedOnly,
  loading,
  error,
  onQueryChange,
  onFlaggedOnlyChange,
  onSelect,
  onRetry,
}: ChatListProps) {
  return (
    <aside
      className="flex h-full min-h-0 w-full flex-col overflow-hidden border-r bg-sidebar text-sidebar-foreground"
      aria-label="Conversations"
    >
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <div className="relative min-w-0 flex-1">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            className="h-10 border-sidebar-border bg-background/60 pl-9 placeholder:text-muted-foreground focus-visible:border-primary"
            placeholder="Search conversations"
            aria-label="Search conversations"
            disabled={loading || Boolean(error)}
          />
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                "shrink-0 text-muted-foreground hover:bg-sidebar-accent hover:text-foreground",
                flaggedOnly && "bg-sidebar-accent text-primary",
              )}
              aria-label={
                flaggedOnly
                  ? "Show all conversations"
                  : "Show conversations with flagged messages"
              }
              aria-pressed={flaggedOnly}
              disabled={loading || Boolean(error)}
              onClick={() => onFlaggedOnlyChange(!flaggedOnly)}
            >
              <ShieldAlert className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {flaggedOnly ? "Show all conversations" : "Show flagged only"}
          </TooltipContent>
        </Tooltip>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        {loading ? (
          <ChatListSkeleton />
        ) : error ? (
          <div className="px-5 py-12 text-center">
            <p className="font-medium text-foreground">Could not load chats</p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {error}
            </p>
            <div className="mt-5 flex justify-center gap-2">
              <Button size="sm" onClick={onRetry}>
                <RefreshCw className="size-4" />
                Retry
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-1 p-2" role="list">
            {conversations.length > 0 ? (
              conversations.map((conversation) => {
                const active = conversation.id === activeId;

                return (
                  <button
                    key={conversation.id}
                    type="button"
                    className={cn(
                      "flex min-h-20 w-full items-center gap-3 rounded-lg border border-transparent px-3 py-2.5 text-left transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                      active
                        ? "border-primary/25 bg-sidebar-accent text-foreground"
                        : "hover:bg-sidebar-accent/55",
                    )}
                    onClick={() => onSelect(conversation.id)}
                    aria-current={active ? "page" : undefined}
                    role="listitem"
                  >
                    <Avatar size="lg">
                      <AvatarFallback className={conversation.avatarClass}>
                        {conversation.initials}
                      </AvatarFallback>
                    </Avatar>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline justify-between gap-2">
                        <strong className="truncate text-sm font-semibold">
                          {conversation.name}
                        </strong>
                        <time className="shrink-0 text-xs text-muted-foreground tabular-nums">
                          {conversation.lastActive}
                        </time>
                      </span>
                      <span className="mt-1 flex items-center gap-2">
                        <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                          {conversation.preview}
                        </span>
                        {conversation.unread ? (
                          <Badge className="size-5 justify-center rounded-full bg-primary p-0 text-[0.7rem] text-primary-foreground">
                            {conversation.unread}
                          </Badge>
                        ) : null}
                      </span>
                      {conversation.flaggedCount ? (
                        <span className="mt-1.5 flex items-center gap-1.5 text-xs font-medium text-[var(--warning-text)]">
                          <ShieldAlert
                            className="size-3.5"
                            aria-hidden="true"
                          />
                          Potential bullying
                        </span>
                      ) : null}
                    </span>
                  </button>
                );
              })
            ) : (
              <div className="px-4 py-12 text-center">
                <p className="font-medium text-foreground">
                  No conversations found
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Try another name or show all conversations.
                </p>
              </div>
            )}
          </div>
        )}
      </ScrollArea>

      <div className="border-t px-4 py-3 text-xs text-muted-foreground">
        Telegram conversations
      </div>
    </aside>
  );
}
