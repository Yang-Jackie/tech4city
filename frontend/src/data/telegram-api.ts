import { requestBackend } from "@/data/backend-api"

export type TelegramLoginStatus = {
  session_id: string
  status: string
  telegram_account_id: number | null
  saved_messages_chat_id: number | null
  selected_chat_id: number | null
  display_name: string | null
  error: string | null
  password_hint: string | null
  code_type: string | null
}

export type TelegramLoginAction = "phone" | "code" | "password"

export function createTelegramLogin(): Promise<TelegramLoginStatus> {
  return requestBackend<TelegramLoginStatus>("/telegram/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  })
}

export function getTelegramLogin(
  sessionId: string,
  signal?: AbortSignal
): Promise<TelegramLoginStatus> {
  return requestBackend<TelegramLoginStatus>(
    `/telegram/login/${encodeURIComponent(sessionId)}`,
    { signal }
  )
}

export function submitTelegramLoginValue(
  sessionId: string,
  action: TelegramLoginAction,
  value: string
): Promise<TelegramLoginStatus> {
  return requestBackend<TelegramLoginStatus>(
    `/telegram/login/${encodeURIComponent(sessionId)}/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    }
  )
}

export function logoutTelegram(
  sessionId: string
): Promise<{ session_id: string; status: string }> {
  return requestBackend<{ session_id: string; status: string }>(
    `/telegram/login/${encodeURIComponent(sessionId)}/logout`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }
  )
}
