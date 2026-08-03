import * as React from "react";
import { Send, ShieldCheck } from "lucide-react";

import { AnalysisSheet } from "@/components/analysis-sheet";
import { ChatList } from "@/components/chat-list";
import { ConversationView } from "@/components/conversation-view";
import { TelegramLoginDialog } from "@/components/telegram-login-dialog";
import { TelegramOnboarding } from "@/components/telegram-onboarding";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  BackendApiError,
  listTelegramConversations,
  loadTelegramConversation,
  openTelegramConversation,
} from "@/data/backend-api";
import type { Conversation, Message } from "@/data/models";
import { cn } from "@/lib/utils";
import {
  createTelegramLogin,
  getTelegramLogin,
  logoutTelegram,
  submitTelegramLoginValue,
  type TelegramLoginAction,
  type TelegramLoginStatus,
} from "@/data/telegram-api";

const TELEGRAM_SESSION_KEY = "detectivesTelegramSession";
const LEGACY_TELEGRAM_SESSION_KEY = "tech4cityTelegramSession";

function restoreTelegramSession(): string | undefined {
  const sessionId =
    window.localStorage.getItem(TELEGRAM_SESSION_KEY) ??
    window.localStorage.getItem(LEGACY_TELEGRAM_SESSION_KEY) ??
    undefined;
  if (sessionId) {
    window.localStorage.setItem(TELEGRAM_SESSION_KEY, sessionId);
    window.localStorage.removeItem(LEGACY_TELEGRAM_SESSION_KEY);
  }
  return sessionId;
}
type DataState = "idle" | "loading" | "connected" | "error";

const STATUS_COPY: Record<DataState, string> = {
  idle: "Telegram not connected",
  loading: "Connecting",
  connected: "Backend connected",
  error: "Backend unavailable",
};

export function App() {
  const savedTelegramSessionId = React.useMemo(
    () => restoreTelegramSession(),
    [],
  );
  const [conversations, setConversations] = React.useState<Conversation[]>([]);
  const [activeId, setActiveId] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [flaggedOnly, setFlaggedOnly] = React.useState(false);
  const [mobileConversationOpen, setMobileConversationOpen] =
    React.useState(false);
  const [analysisOpen, setAnalysisOpen] = React.useState(false);
  const [selectedMessage, setSelectedMessage] = React.useState<Message>();
  const [dataState, setDataState] = React.useState<DataState>(
    savedTelegramSessionId ? "loading" : "idle",
  );
  const [listError, setListError] = React.useState<string>();
  const [conversationLoading, setConversationLoading] = React.useState(false);
  const [conversationError, setConversationError] = React.useState<string>();
  const activeTelegramLoad = React.useRef("");
  const openedTelegramChatId = React.useRef<number | undefined>(undefined);
  const loadedTelegramChatIds = React.useRef(new Set<number>());
  const conversationsRef = React.useRef(conversations);

  const [telegramDialogOpen, setTelegramDialogOpen] = React.useState(false);
  const [telegramSessionId, setTelegramSessionId] = React.useState(
    savedTelegramSessionId,
  );
  const [telegramStatus, setTelegramStatus] =
    React.useState<TelegramLoginStatus>();
  const [telegramBusy, setTelegramBusy] = React.useState(false);
  const [telegramError, setTelegramError] = React.useState<string>();
  const [telegramStatusReload, setTelegramStatusReload] = React.useState(0);
  const [telegramDataReload, setTelegramDataReload] = React.useState(0);

  const telegramAccountId = telegramStatus?.telegram_account_id ?? undefined;
  const telegramReady =
    telegramStatus?.status === "ready" &&
    Boolean(telegramSessionId) &&
    telegramAccountId !== undefined;

  const filteredConversations = React.useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return conversations.filter((conversation) => {
      if (flaggedOnly && !conversation.flaggedCount) return false;
      if (!normalizedQuery) return true;

      return `${conversation.name} ${conversation.preview}`
        .toLowerCase()
        .includes(normalizedQuery);
    });
  }, [conversations, flaggedOnly, query]);

  const activeConversation = conversations.find(
    (conversation) => conversation.id === activeId,
  );

  React.useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  const clearTelegramSession = React.useCallback(() => {
    window.localStorage.removeItem(TELEGRAM_SESSION_KEY);
    window.localStorage.removeItem(LEGACY_TELEGRAM_SESSION_KEY);
    openedTelegramChatId.current = undefined;
    loadedTelegramChatIds.current.clear();
    setTelegramSessionId(undefined);
    setTelegramStatus(undefined);
  }, []);

  const showDisconnectedView = React.useCallback(() => {
    clearTelegramSession();
    setConversations([]);
    setActiveId("");
    setSelectedMessage(undefined);
    setAnalysisOpen(false);
    setMobileConversationOpen(false);
    setListError(undefined);
    setDataState("idle");
  }, [clearTelegramSession]);

  const applyTelegramStatus = React.useCallback(
    (nextStatus: TelegramLoginStatus) => {
      if (nextStatus.status === "logged_out") {
        showDisconnectedView();
        return;
      }

      window.localStorage.setItem(TELEGRAM_SESSION_KEY, nextStatus.session_id);
      setTelegramSessionId(nextStatus.session_id);
      setTelegramStatus(nextStatus);
      setTelegramError(nextStatus.error ?? undefined);

      if (nextStatus.status === "ready") {
        setDataState("loading");
        setListError(undefined);
      }
    },
    [showDisconnectedView],
  );

  React.useEffect(() => {
    if (!telegramSessionId) return;

    const controller = new AbortController();

    void getTelegramLogin(telegramSessionId, controller.signal)
      .then(applyTelegramStatus)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;

        if (
          error instanceof BackendApiError &&
          [401, 404, 409].includes(error.status ?? 0)
        ) {
          showDisconnectedView();
          setTelegramError("Telegram session expired. Connect Telegram again.");
          return;
        }

        setTelegramError(
          error instanceof Error ? error.message : "Could not restore login.",
        );
        setDataState("error");
      });

    return () => controller.abort();
  }, [
    applyTelegramStatus,
    showDisconnectedView,
    telegramSessionId,
    telegramStatusReload,
  ]);

  React.useEffect(() => {
    if (
      !telegramSessionId ||
      !["starting", "logging_out"].includes(telegramStatus?.status ?? "")
    ) {
      return;
    }

    const timer = window.setTimeout(
      () => setTelegramStatusReload((value) => value + 1),
      1000,
    );
    return () => window.clearTimeout(timer);
  }, [telegramSessionId, telegramStatus?.status, telegramStatusReload]);

  React.useEffect(() => {
    openedTelegramChatId.current = telegramReady
      ? (telegramStatus?.selected_chat_id ?? undefined)
      : undefined;
  }, [telegramReady, telegramSessionId, telegramStatus?.selected_chat_id]);

  React.useEffect(() => {
    if (
      !telegramReady ||
      !telegramSessionId ||
      telegramAccountId === undefined
    ) {
      return;
    }

    const controller = new AbortController();

    void listTelegramConversations(
      telegramSessionId,
      telegramAccountId,
      controller.signal,
    )
      .then((items) => {
        if (controller.signal.aborted) return;
        setConversations((current) =>
          items.map((item) => {
            const existing = current.find((entry) => entry.id === item.id);
            if (!existing) return item;
            return {
              ...item,
              messages: existing.messages,
              flaggedCount: existing.flaggedCount,
            };
          }),
        );
        setActiveId((current) =>
          items.some((item) => item.id === current)
            ? current
            : (items[0]?.id ?? ""),
        );
        setListError(undefined);
        setDataState("connected");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setListError(
          error instanceof Error
            ? error.message
            : "Telegram messages are unavailable.",
        );
        setDataState("error");
      });

    return () => controller.abort();
  }, [telegramAccountId, telegramDataReload, telegramReady, telegramSessionId]);

  React.useEffect(() => {
    if (
      !telegramReady ||
      !telegramSessionId ||
      telegramAccountId === undefined ||
      !activeId
    ) {
      return;
    }

    const conversation = conversationsRef.current.find(
      (item) => item.id === activeId,
    );
    if (!conversation) return;

    const requestKey = `${telegramDataReload}:${activeId}`;
    if (activeTelegramLoad.current === requestKey) return;
    activeTelegramLoad.current = requestKey;

    const controller = new AbortController();
    const chatId = Number(conversation.id);
    const initialLoad = !loadedTelegramChatIds.current.has(chatId);
    setConversationLoading(initialLoad);
    setConversationError(undefined);

    void (async () => {
      if (openedTelegramChatId.current !== chatId) {
        await openTelegramConversation(
          telegramSessionId,
          chatId,
          controller.signal,
        );
        openedTelegramChatId.current = chatId;
      }
      return loadTelegramConversation(
        conversation,
        telegramSessionId,
        telegramAccountId,
        controller.signal,
      );
    })()
      .then((loaded) => {
        if (controller.signal.aborted) return;
        loadedTelegramChatIds.current.add(chatId);
        setConversations((current) =>
          current.map((item) =>
            item.id === loaded.id
              ? {
                  ...item,
                  messages: loaded.messages,
                  flaggedCount: loaded.flaggedCount,
                }
              : item,
          ),
        );
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        if (initialLoad) {
          setConversationError(
            error instanceof Error
              ? error.message
              : "This conversation is temporarily unavailable.",
          );
        }
      })
      .finally(() => {
        if (
          !controller.signal.aborted &&
          activeTelegramLoad.current === requestKey
        ) {
          setConversationLoading(false);
        }
      });

    return () => {
      controller.abort();
      if (activeTelegramLoad.current === requestKey) {
        activeTelegramLoad.current = "";
      }
    };
  }, [
    activeId,
    telegramAccountId,
    telegramDataReload,
    telegramReady,
    telegramSessionId,
  ]);

  React.useEffect(() => {
    if (!telegramReady) return;
    const timer = window.setInterval(
      () => setTelegramDataReload((value) => value + 1),
      5000,
    );
    return () => window.clearInterval(timer);
  }, [telegramReady]);

  function selectConversation(id: string) {
    setActiveId(id);
    setSelectedMessage(undefined);
    setAnalysisOpen(false);
    setMobileConversationOpen(true);
  }

  function selectMessage(message: Message) {
    if (!message.analysis) return;
    setSelectedMessage(message);
    setAnalysisOpen(true);
  }

  function retryConversation() {
    activeTelegramLoad.current = "";
    setTelegramDataReload((value) => value + 1);
  }

  function retryTelegram() {
    setDataState("loading");
    setListError(undefined);
    if (telegramReady) {
      setTelegramDataReload((value) => value + 1);
    } else {
      setTelegramStatusReload((value) => value + 1);
    }
  }

  async function startTelegramLogin() {
    setTelegramBusy(true);
    setTelegramError(undefined);
    try {
      applyTelegramStatus(await createTelegramLogin());
    } catch (error) {
      setTelegramError(
        error instanceof Error ? error.message : "Could not start login.",
      );
    } finally {
      setTelegramBusy(false);
    }
  }

  async function submitTelegramLogin(
    action: TelegramLoginAction,
    value: string,
  ) {
    if (!telegramSessionId) return;
    setTelegramBusy(true);
    setTelegramError(undefined);
    try {
      applyTelegramStatus(
        await submitTelegramLoginValue(telegramSessionId, action, value),
      );
    } catch (error) {
      setTelegramError(
        error instanceof Error ? error.message : "Telegram rejected the value.",
      );
    } finally {
      setTelegramBusy(false);
    }
  }

  async function endTelegramLogin() {
    if (!telegramSessionId) {
      showDisconnectedView();
      setTelegramDialogOpen(false);
      return;
    }

    setTelegramBusy(true);
    setTelegramError(undefined);
    try {
      await logoutTelegram(telegramSessionId);
      showDisconnectedView();
      setTelegramDialogOpen(false);
    } catch (error) {
      setTelegramError(
        error instanceof Error ? error.message : "Could not log out.",
      );
    } finally {
      setTelegramBusy(false);
    }
  }

  const connectionLabel = telegramReady
    ? dataState === "connected"
      ? "Telegram connected"
      : dataState === "loading"
        ? "Loading Telegram"
        : "Telegram unavailable"
    : telegramSessionId
      ? "Telegram login"
      : STATUS_COPY[dataState];
  const firstUse = !telegramSessionId && dataState === "idle";

  return (
    <TooltipProvider delayDuration={250}>
      <a
        href="#conversation"
        className="fixed top-3 left-3 z-[60] -translate-y-20 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-transform focus:translate-y-0"
      >
        Skip to conversation
      </a>

      <div className="flex h-dvh h-screen min-w-80 flex-col overflow-hidden bg-background text-foreground">
        <header className="flex h-[3.75rem] shrink-0 items-center gap-3 border-b bg-sidebar px-4 sm:px-5">
          <span className="flex size-8 items-center justify-center rounded-lg border border-primary/35 bg-primary/15 text-primary">
            <ShieldCheck className="size-[1.125rem]" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold sm:text-base">
              Detectives
            </p>
          </div>
          <div className="hidden items-center gap-2 text-xs text-muted-foreground md:flex">
            <span
              className={cn(
                "size-2 rounded-full",
                dataState === "connected"
                  ? "bg-emerald-400"
                  : dataState === "error"
                    ? "bg-rose-400"
                    : dataState === "loading"
                      ? "bg-amber-400"
                      : "bg-muted-foreground",
              )}
              aria-hidden="true"
            />
            <span>{connectionLabel}</span>
          </div>
          <Button
            variant={telegramReady ? "ghost" : "outline"}
            size="sm"
            onClick={() => setTelegramDialogOpen(true)}
          >
            <Send aria-hidden="true" />
            <span className="hidden sm:inline">
              {telegramReady ? "Telegram" : "Connect Telegram"}
            </span>
          </Button>
          {telegramReady ? (
            <Avatar>
              <AvatarFallback className="bg-secondary text-xs font-semibold text-foreground">
                TG
              </AvatarFallback>
            </Avatar>
          ) : null}
        </header>

        {firstUse ? (
          <TelegramOnboarding onConnect={() => setTelegramDialogOpen(true)} />
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[20rem_minmax(0,1fr)]">
            <div
              className={cn(
                "h-full min-h-0 overflow-hidden",
                mobileConversationOpen ? "hidden lg:block" : "block",
              )}
            >
              <ChatList
                conversations={filteredConversations}
                activeId={activeId}
                query={query}
                flaggedOnly={flaggedOnly}
                loading={dataState === "loading"}
                error={listError}
                onQueryChange={setQuery}
                onFlaggedOnlyChange={setFlaggedOnly}
                onSelect={selectConversation}
                onRetry={retryTelegram}
              />
            </div>

            <div
              className={cn(
                "h-full min-h-0 min-w-0 overflow-hidden",
                mobileConversationOpen ? "flex" : "hidden lg:flex",
              )}
            >
              {activeConversation ? (
                <ConversationView
                  conversation={activeConversation}
                  selectedMessageId={selectedMessage?.id}
                  loading={conversationLoading}
                  error={conversationError}
                  onRetry={retryConversation}
                  onBack={() => setMobileConversationOpen(false)}
                  onSelectMessage={selectMessage}
                />
              ) : (
                <main
                  id="conversation"
                  className="flex h-full min-h-0 flex-1 items-center justify-center bg-background px-6 text-center"
                >
                  <div>
                    <p className="font-medium">No conversation selected</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {telegramReady
                        ? "Telegram is connected. Waiting for text messages."
                        : "Choose a conversation from the list."}
                    </p>
                  </div>
                </main>
              )}
            </div>
          </div>
        )}

        <AnalysisSheet
          open={analysisOpen}
          message={selectedMessage}
          onOpenChange={setAnalysisOpen}
        />
      </div>
      <TelegramLoginDialog
        open={telegramDialogOpen}
        status={telegramStatus}
        busy={telegramBusy}
        error={telegramError}
        onOpenChange={setTelegramDialogOpen}
        onStart={() => void startTelegramLogin()}
        onSubmit={(action, value) => void submitTelegramLogin(action, value)}
        onLogout={() => void endTelegramLogin()}
      />
    </TooltipProvider>
  );
}

export default App;
