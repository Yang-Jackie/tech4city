import type { AnalysisResult, Conversation, Message } from "@/data/models";

const DEFAULT_API_BASE_URL = import.meta.env.DEV ? "/api" : "";
const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL
).replace(/\/$/, "");

const AVATAR_CLASSES = [
  "bg-violet-400/20 text-violet-200",
  "bg-emerald-400/15 text-emerald-200",
  "bg-amber-400/15 text-amber-200",
  "bg-sky-400/15 text-sky-200",
  "bg-rose-400/15 text-rose-200",
  "bg-teal-400/15 text-teal-200",
] as const;

type ChatSummary = {
  chat_id: number;
  message_count?: number;
  participant_count?: number;
  first_message_at?: string;
  last_message_at: string | null;
  last_message_preview: string;
  title?: string;
  chat_type?: string;
  is_saved_messages?: boolean;
};

type StoredMessage = {
  telegram_account_id: number;
  chat_id: number;
  message_id: number;
  sender_id: number;
  text: string;
  sent_at: string;
  received_at: string;
};

type Layer3Category = {
  label: string;
};

type Layer3Analysis = {
  is_suspected_cyberbullying: boolean;
  confidence: number;
  severity: "none" | "low" | "medium" | "high" | "urgent";
  categories: Layer3Category[];
};

type BackendAnalysis = {
  harmful: boolean | null;
  severity: "none" | "low" | "medium" | "high" | "urgent" | null;
  categories: string[] | null;
  explanation: string | null;
  pipeline_version: string;
  layer3: {
    explanation: string;
    analysis: Layer3Analysis;
  } | null;
};

function readableLabel(value: string): string {
  return value
    .split("_")
    .map((part, index) =>
      index === 0 ? `${part.charAt(0).toUpperCase()}${part.slice(1)}` : part,
    )
    .join(" ");
}

type MessageReport = {
  message: StoredMessage;
  analysis: BackendAnalysis | null;
  analysis_job: {
    status: "pending" | "processing" | "completed" | "failed";
  } | null;
};

export class BackendApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "BackendApiError";
    this.status = status;
  }
}

export async function requestBackend<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new BackendApiError("The backend is unavailable.");
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      // The status-based fallback remains safe for non-JSON errors.
    }

    throw new BackendApiError(
      detail ??
        (response.status === 404
          ? "The requested backend data was not found."
          : `The backend returned HTTP ${response.status}.`),
      response.status,
    );
  }

  return (await response.json()) as T;
}

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return requestBackend<T>(path, { signal });
}

function formatTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const today = new Date();

  if (date.toDateString() === today.toDateString()) {
    return new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }

  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date);
}

function titleInitials(title: string, fallback: string): string {
  const parts = title.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return fallback;
  return parts
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function chatName(chatId: number, accountId: number): string {
  return chatId === accountId ? "Saved Messages" : `Chat ${chatId}`;
}

function initials(chatId: number, accountId: number): string {
  return chatId === accountId ? "SM" : `C${String(chatId).slice(-1)}`;
}

function avatarClass(chatId: number): string {
  return AVATAR_CLASSES[Math.abs(chatId) % AVATAR_CLASSES.length];
}

function titleCase(
  value: "none" | "low" | "medium" | "high" | "urgent",
): AnalysisResult["severity"] {
  return `${value.charAt(0).toUpperCase()}${value.slice(1)}` as AnalysisResult["severity"];
}

function mapAnalysis(
  report: MessageReport,
  analyzedAt: string,
): AnalysisResult | undefined {
  const analysis = report.analysis;
  if (!analysis) return undefined;

  const layer3 = analysis.layer3?.analysis;
  if (!layer3) return undefined;
  const harmful =
    analysis.harmful === true || layer3?.is_suspected_cyberbullying === true;

  const category = harmful
    ? readableLabel(
        analysis.categories?.[0] ??
          layer3?.categories[0]?.label ??
          "Potential bullying",
      )
    : "No bullying detected";
  const severity = analysis.severity ?? layer3?.severity ?? "none";

  return {
    harmful,
    category,
    severity: titleCase(severity),
    confidence:
      layer3?.confidence === undefined
        ? undefined
        : Math.round(layer3.confidence * 100),
    explanation:
      analysis.explanation ??
      analysis.layer3?.explanation ??
      (harmful
        ? "No approved explanation is available for this output."
        : "The analysis completed without identifying suspected cyberbullying in this message."),
    analyzedAt: formatTime(analyzedAt),
    pipelineVersion: analysis.pipeline_version,
  };
}

function mapConversations(
  chats: ChatSummary[],
  accountId: number,
): Conversation[] {
  return chats.map((chat) => {
    const savedMessages =
      chat.is_saved_messages === true || chat.chat_id === accountId;
    const name = savedMessages
      ? "Saved Messages"
      : (chat.title ?? chatName(chat.chat_id, accountId));

    return {
      id: String(chat.chat_id),
      name,
      initials: savedMessages
        ? "SM"
        : titleInitials(name, initials(chat.chat_id, accountId)),
      avatarClass: avatarClass(chat.chat_id),
      lastActive: formatTime(chat.last_message_at),
      preview: chat.last_message_preview || "No recent text messages",
      messages: [],
    };
  });
}

export async function listTelegramConversations(
  sessionId: string,
  accountId: number,
  signal?: AbortSignal,
): Promise<Conversation[]> {
  const chats = await fetchJson<ChatSummary[]>(
    `/telegram/login/${encodeURIComponent(sessionId)}/chats`,
    signal,
  );
  return mapConversations(chats, accountId);
}

type TelegramChatOpenStatus = {
  session_id: string;
  chat_id: number;
  history_message_count: number;
  message_count: number;
  new_message_count: number;
};

export function openTelegramConversation(
  sessionId: string,
  chatId: number,
  signal?: AbortSignal,
): Promise<TelegramChatOpenStatus> {
  return requestBackend<TelegramChatOpenStatus>(
    `/telegram/login/${encodeURIComponent(sessionId)}/chats/${encodeURIComponent(chatId)}/open`,
    {
      method: "POST",
      signal,
    },
  );
}

export async function loadTelegramConversation(
  conversation: Conversation,
  sessionId: string,
  accountId: number,
  signal?: AbortSignal,
): Promise<Conversation> {
  const chatId = Number(conversation.id);
  const reports = await fetchJson<MessageReport[]>(
    `/telegram/login/${encodeURIComponent(sessionId)}/chats/${encodeURIComponent(chatId)}/reports`,
    signal,
  );

  const messages: Message[] = reports.map((report) => {
    const analysis = mapAnalysis(report, report.message.received_at);
    return {
      id: String(report.message.message_id),
      direction:
        report.message.sender_id === accountId ? "outgoing" : "incoming",
      text: report.message.text,
      time: formatTime(report.message.sent_at),
      flagged: analysis?.harmful === true,
      analysis,
      analysisState: report.analysis_job?.status,
    };
  });

  return {
    ...conversation,
    messages,
    flaggedCount: messages.filter((message) => message.flagged).length,
  };
}
