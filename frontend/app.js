const POLL_INTERVAL_MS = 2000;
const LOGIN_POLL_INTERVAL_MS = 1000;
const WS_MAX_RECONNECT_MS = 10000;

const accountForm = document.querySelector("#account-form");
const accountInput = document.querySelector("#account-id");
const connectionDot = document.querySelector("#connection-dot");
const connectionStatus = document.querySelector("#connection-status");
const workspace = document.querySelector("#workspace");
const chatCount = document.querySelector("#chat-count");
const chatSearch = document.querySelector("#chat-search");
const chatList = document.querySelector("#chat-list");
const manualChatForm = document.querySelector("#manual-chat-form");
const manualChatInput = document.querySelector("#manual-chat-id");
const backToChatsButton = document.querySelector("#back-to-chats");
const conversationContext = document.querySelector("#conversation-context");
const conversationTitle = document.querySelector("#conversation-title");
const conversationSummary = document.querySelector("#conversation-summary");
const refreshButton = document.querySelector("#refresh-button");
const viewAnalysisButton = document.querySelector("#view-analysis");
const messageList = document.querySelector("#message-list");
const analysisPanel = document.querySelector("#analysis-panel");
const analysisContent = document.querySelector("#analysis-content");
const closeAnalysisButton = document.querySelector("#close-analysis");
const toast = document.querySelector("#toast");
const telegramLoginButton = document.querySelector("#telegram-login-button");
const telegramLoginDialog = document.querySelector("#telegram-login-dialog");
const telegramLoginForm = document.querySelector("#telegram-login-form");
const telegramLoginClose = document.querySelector("#telegram-login-close");
const telegramLoginMessage = document.querySelector("#telegram-login-message");
const telegramLoginLabel = document.querySelector("#telegram-login-label");
const telegramLoginValue = document.querySelector("#telegram-login-value");
const telegramLoginSubmit = document.querySelector("#telegram-login-submit");
const telegramLogoutButton = document.querySelector("#telegram-logout-button");

const state = {
  accountId: "",
  chatId: "",
  chats: [],
  messages: [],
  selectedMessageId: null,
  selectedButton: null,
  pollTimer: null,
  refreshing: false,
  toastTimer: null,
  telegramSessionId: window.localStorage.getItem("tech4cityTelegramSession") || "",
  telegramStatus: null,
  telegramPollTimer: null,
  websocket: null,
  websocketReconnectTimer: null,
  websocketReconnectMs: 500,
  websocketHeartbeatTimer: null,
  websocketLastPongAt: 0,
  chatListRequestId: 0,
  conversationRequestId: 0,
  analysisRequestId: 0,
};

function createElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function setConnectionState(kind, message) {
  connectionDot.className = `state-dot state-dot--${kind}`;
  connectionStatus.textContent = message;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("toast--visible");
  window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => {
    toast.classList.remove("toast--visible");
  }, 3500);
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatPercent(score) {
  return new Intl.NumberFormat(undefined, {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(score);
}

function chatLabel(chatId) {
  return String(chatId) === state.accountId ? "Saved Messages" : `Chat ${chatId}`;
}

function plural(count, singular, pluralValue = `${singular}s`) {
  return count === 1 ? singular : pluralValue;
}

function fetchJson(url) {
  return fetch(url, { headers: { Accept: "application/json" } }).then((response) => {
    if (!response.ok) throw new Error(`Request failed with HTTP ${response.status}.`);
    return response.json();
  });
}

function showChatListSkeletons() {
  const stack = createElement("div", "chat-list-skeletons");
  stack.setAttribute("aria-label", "Loading chats");
  for (let index = 0; index < 4; index += 1) {
    const item = createElement("div", "chat-list-skeleton");
    item.setAttribute("aria-hidden", "true");
    stack.append(item);
  }
  chatList.replaceChildren(stack);
}

function showMessageSkeletons() {
  const stack = createElement("div", "message-skeletons");
  stack.setAttribute("aria-label", "Loading messages");
  for (let index = 0; index < 4; index += 1) {
    const item = createElement("div", "message-skeleton");
    item.setAttribute("aria-hidden", "true");
    stack.append(item);
  }
  messageList.replaceChildren(stack);
}

function renderChatList() {
  const query = chatSearch.value.trim().toLowerCase();
  const visibleChats = state.chats.filter((chat) => {
    const searchable = `${chatLabel(chat.chat_id)} ${chat.chat_id} ${chat.last_message_preview}`;
    return searchable.toLowerCase().includes(query);
  });

  chatCount.textContent = String(state.chats.length);
  chatSearch.disabled = state.chats.length === 0;

  if (state.chats.length === 0) {
    const empty = createElement("div", "compact-empty");
    empty.append(
      createElement("strong", "", "No stored chats yet"),
      createElement(
        "span",
        "",
        "Seed demo data or connect Telegram, then refresh.",
      ),
    );
    chatList.replaceChildren(empty);
    return;
  }

  if (visibleChats.length === 0) {
    const empty = createElement("div", "compact-empty");
    empty.append(
      createElement("strong", "", "No matching chats"),
      createElement("span", "", "Try a chat ID or a word from the latest message."),
    );
    chatList.replaceChildren(empty);
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const chat of visibleChats) {
    const button = createElement("button", "chat-item");
    button.type = "button";
    button.dataset.chatId = String(chat.chat_id);
    if (String(chat.chat_id) === state.chatId) button.setAttribute("aria-current", "page");

    const top = createElement("span", "chat-item-top");
    top.append(
      createElement("strong", "chat-item-title", chatLabel(chat.chat_id)),
      createElement("time", "chat-item-time", formatTime(chat.last_message_at)),
    );
    const preview = createElement("span", "chat-item-preview", chat.last_message_preview);
    const meta = createElement(
      "span",
      "chat-item-meta",
      `${chat.message_count} ${plural(chat.message_count, "message")} · ${chat.participant_count} ${plural(chat.participant_count, "participant")}`,
    );
    button.append(top, preview, meta);
    button.addEventListener("click", () => selectChat(String(chat.chat_id)));
    fragment.append(button);
  }
  chatList.replaceChildren(fragment);
}

function showChatListError(message) {
  const content = createElement("div", "compact-empty compact-empty--error");
  content.append(
    createElement("strong", "", "Could not load chats"),
    createElement("span", "", `${message} Check that the backend is running.`),
  );
  chatList.replaceChildren(content);
}

async function loadChats({ initial = false } = {}) {
  if (!state.accountId) return;
  const requestId = ++state.chatListRequestId;
  const accountId = state.accountId;
  if (initial) showChatListSkeletons();
  const connected = usingConnectedTelegram();
  const sessionId = state.telegramSessionId;
  const query = new URLSearchParams({ telegram_account_id: accountId });
  const chats = await fetchJson(
    connected
      ? `/telegram/login/${encodeURIComponent(sessionId)}/chats`
      : `/chats?${query}`,
  );
  if (
    requestId !== state.chatListRequestId ||
    accountId !== state.accountId ||
    (connected && sessionId !== state.telegramSessionId)
  ) return false;
  state.chats = chats;
  renderChatList();
  return true;
}

function renderConversationSummary(messages) {
  conversationSummary.replaceChildren();
  if (messages.length === 0) return;

  const participants = new Set(messages.map((message) => String(message.sender_id))).size;
  const first = messages[0].sent_at;
  const last = messages[messages.length - 1].sent_at;
  const timeRange = first === last ? formatTime(first) : `${formatTime(first)}–${formatTime(last)}`;
  const facts = [
    `${messages.length} ${plural(messages.length, "message")}`,
    `${participants} ${plural(participants, "participant")}`,
    timeRange,
  ];
  for (const fact of facts) conversationSummary.append(createElement("span", "summary-fact", fact));
}

function showConversationError(message) {
  const content = createElement("div", "error-state");
  content.append(
    createElement("h3", "", "Could not load this conversation"),
    createElement("p", "", `${message} Check that the backend is running, then refresh.`),
  );
  messageList.replaceChildren(content);
}

function showEmptyConversation() {
  const content = createElement("div", "empty-state");
  content.append(
    createElement("h3", "", "No forwarded messages yet"),
    createElement(
      "p",
      "",
      "Seed sanitized demo data or send a text message to connected Saved Messages.",
    ),
  );
  messageList.replaceChildren(content);
}

function renderMessages(messages) {
  state.selectedButton = null;
  renderConversationSummary(messages);
  if (messages.length === 0) {
    showEmptyConversation();
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const message of messages) {
    const outgoing = String(message.sender_id) === state.accountId;
    const button = createElement(
      "button",
      `message-row${outgoing ? " message-row--outgoing" : ""}`,
    );
    button.type = "button";
    button.dataset.messageId = String(message.message_id);
    button.setAttribute(
      "aria-label",
      `${outgoing ? "You" : `Sender ${message.sender_id}`} at ${formatTime(message.sent_at)}: ${message.text}`,
    );
    if (String(message.message_id) === state.selectedMessageId) {
      button.setAttribute("aria-current", "true");
      state.selectedButton = button;
    }

    const bubble = createElement("span", "message-bubble");
    const meta = createElement("span", "message-meta");
    meta.append(
      createElement("span", "message-sender", outgoing ? "You" : `Sender ${message.sender_id}`),
      createElement("time", "", formatTime(message.sent_at)),
    );
    bubble.append(createElement("span", "message-text", message.text), meta);
    button.append(bubble);
    button.addEventListener("click", () => selectMessage(message, button));
    fragment.append(button);
  }
  messageList.replaceChildren(fragment);
}

function resetAnalysis() {
  state.analysisRequestId += 1;
  state.selectedMessageId = null;
  state.selectedButton = null;
  viewAnalysisButton.disabled = true;
  analysisContent.replaceChildren();
  const empty = createElement("div", "analysis-empty");
  const orbit = createElement("span", "analysis-orbit");
  orbit.setAttribute("aria-hidden", "true");
  empty.append(
    orbit,
    createElement("h3", "", "Select a message"),
    createElement("p", "", "Choose a message to inspect its processing state and available output."),
  );
  analysisContent.append(empty);
  closeAnalysisPanel({ restoreFocus: false });
}

function statusDescription(status) {
  const descriptions = {
    pending: ["Waiting for analysis", "The backend accepted this message and queued it."],
    processing: ["Analysis in progress", "The worker is processing this message."],
    completed: ["Analysis completed", "The latest available model output is shown below."],
    failed: ["Analysis failed", "The backend could not analyze this message."],
  };
  return descriptions[status] || [
    "Unknown analysis state",
    "The backend returned an unfamiliar state.",
  ];
}

function detailRow(label, value) {
  const row = createElement("div", "detail-row");
  row.append(createElement("dt", "", label), createElement("dd", "", value));
  return row;
}

function scoreRow(label, score) {
  const row = createElement("div", "score-row");
  const percentage = formatPercent(score);
  const meter = createElement("meter");
  meter.min = 0;
  meter.max = 1;
  meter.value = score;
  meter.textContent = percentage;
  row.append(createElement("label", "", label), createElement("strong", "", percentage), meter);
  return row;
}

function renderAnalysis(report) {
  const { message, analysis, analysis_job: job } = report;
  const [title, description] = statusDescription(job.status);
  const fragment = document.createDocumentFragment();

  const banner = createElement("section", `status-banner status-banner--${job.status}`);
  const symbol = job.status === "completed" ? "✓" : job.status === "failed" ? "!" : "…";
  const statusIcon = createElement("span", "status-icon", symbol);
  statusIcon.setAttribute("aria-hidden", "true");
  const statusCopy = createElement("div", "status-copy");
  statusCopy.append(createElement("h3", "", title), createElement("p", "", description));
  banner.append(statusIcon, statusCopy);
  fragment.append(banner);

  const messageSection = createElement("section", "detail-section");
  messageSection.append(
    createElement("h3", "", "Selected message"),
    createElement("p", "selected-message", message.text),
  );
  fragment.append(messageSection);

  const factsSection = createElement("section", "detail-section");
  const facts = createElement("dl", "detail-list");
  facts.append(
    detailRow("Sender", String(message.sender_id) === state.accountId ? "You" : String(message.sender_id)),
    detailRow("Sent", formatDateTime(message.sent_at)),
    detailRow("Attempts", String(job.attempts)),
  );
  if (analysis?.pipeline_version) facts.append(detailRow("Analyzer version", analysis.pipeline_version));
  factsSection.append(createElement("h3", "", "Processing details"), facts);
  fragment.append(factsSection);

  if (analysis?.layer1) {
    const layerSection = createElement("section", "detail-section");
    const layerFacts = createElement("dl", "detail-list");
    layerFacts.append(
      detailRow("Classifier status", analysis.layer1.status),
      detailRow("Raw label", analysis.layer1.raw_label),
    );
    layerSection.append(
      createElement("h3", "", "Layer 1 output"),
      layerFacts,
      scoreRow("Bully score", analysis.layer1.bully_score),
      scoreRow("Normal score", analysis.layer1.normal_score),
    );
    fragment.append(layerSection);
  }

  const explanationSection = createElement("section", "detail-section");
  explanationSection.append(
    createElement("h3", "", "Model explanation"),
    createElement(
      "p",
      `explanation${analysis?.explanation ? "" : " explanation--unavailable"}`,
      analysis?.explanation || "No approved explanation is available for this output.",
    ),
  );
  fragment.append(explanationSection);

  if (job.error) {
    const errorSection = createElement("section", "detail-section");
    errorSection.append(
      createElement("h3", "", "Failure information"),
      createElement("p", "explanation explanation--unavailable", job.error),
    );
    fragment.append(errorSection);
  }

  analysisContent.replaceChildren(fragment);
}

function showAnalysisLoading(message) {
  const content = createElement("div", "analysis-empty");
  content.append(
    createElement("h3", "", "Loading analysis"),
    createElement("p", "", `Checking the latest result for message ${message.message_id}.`),
  );
  analysisContent.replaceChildren(content);
}

function openAnalysisPanel({ focusClose = false } = {}) {
  if (!state.selectedMessageId) return;
  analysisPanel.hidden = false;
  viewAnalysisButton.setAttribute("aria-expanded", "true");
  document.body.classList.add("analysis-open");
  if (focusClose) closeAnalysisButton.focus();
}

function closeAnalysisPanel({ restoreFocus = true } = {}) {
  analysisPanel.hidden = true;
  viewAnalysisButton.setAttribute("aria-expanded", "false");
  document.body.classList.remove("analysis-open");
  if (restoreFocus && !viewAnalysisButton.disabled) viewAnalysisButton.focus();
}

async function loadAnalysis(message, { announceError = true } = {}) {
  const requestId = ++state.analysisRequestId;
  const accountId = state.accountId;
  const chatId = state.chatId;
  const selectedMessageId = String(message.message_id);
  const sessionId = state.telegramSessionId;
  const connected = usingConnectedTelegram();
  const query = new URLSearchParams({
    telegram_account_id: accountId,
    chat_id: chatId,
  });
  try {
    const report = await fetchJson(connected
      ? `/telegram/login/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(message.message_id)}/report`
      : `/messages/${encodeURIComponent(message.message_id)}/report?${query}`);
    if (
      requestId === state.analysisRequestId &&
      accountId === state.accountId &&
      chatId === state.chatId &&
      (!connected || sessionId === state.telegramSessionId) &&
      selectedMessageId === state.selectedMessageId
    ) renderAnalysis(report);
  } catch (error) {
    if (
      requestId !== state.analysisRequestId ||
      accountId !== state.accountId ||
      chatId !== state.chatId ||
      (connected && sessionId !== state.telegramSessionId) ||
      selectedMessageId !== state.selectedMessageId
    ) return;
    if (announceError) showToast("Could not load the selected message analysis.");
    const content = createElement("div", "error-state");
    content.append(
      createElement("h3", "", "Analysis unavailable"),
      createElement("p", "", `${error.message} Try again after the backend reconnects.`),
    );
    analysisContent.replaceChildren(content);
  }
}

function selectMessage(message, button) {
  state.selectedMessageId = String(message.message_id);
  state.selectedButton?.removeAttribute("aria-current");
  state.selectedButton = button;
  button.setAttribute("aria-current", "true");
  viewAnalysisButton.disabled = false;
  showAnalysisLoading(message);
  openAnalysisPanel();
  loadAnalysis(message);
}

async function loadConversation({ initial = false } = {}) {
  if (!state.accountId || !state.chatId) return;
  const requestId = ++state.conversationRequestId;
  const accountId = state.accountId;
  const chatId = state.chatId;
  const sessionId = state.telegramSessionId;
  if (initial) showMessageSkeletons();
  const query = new URLSearchParams({ telegram_account_id: accountId });
  const connected = usingConnectedTelegram();
  const messages = await fetchJson(connected
    ? `/telegram/login/${encodeURIComponent(sessionId)}/chats/${encodeURIComponent(chatId)}/messages`
    : `/chats/${encodeURIComponent(chatId)}/messages?${query}`);
  if (
    requestId !== state.conversationRequestId ||
    accountId !== state.accountId ||
    chatId !== state.chatId ||
    (connected && sessionId !== state.telegramSessionId)
  ) return false;
  const previousCount = state.messages.length;
  state.messages = messages;
  renderMessages(messages);
  if (messages.length > previousCount && previousCount > 0) {
    messageList.scrollTop = messageList.scrollHeight;
  }
  if (state.selectedMessageId) {
    const selected = messages.find(
      (message) => String(message.message_id) === state.selectedMessageId,
    );
    if (selected) await loadAnalysis(selected, { announceError: false });
  }
}

async function refreshAll({ initial = false } = {}) {
  if (!state.accountId || state.refreshing) return;
  const accountId = state.accountId;
  const chatId = state.chatId;
  state.refreshing = true;
  setConnectionState("loading", "Checking the backend");
  try {
    await Promise.all([
      loadChats({ initial }),
      state.chatId ? loadConversation({ initial }) : Promise.resolve(),
    ]);
    if (accountId !== state.accountId || chatId !== state.chatId) return;
    setConnectionState("connected", "Backend connected");
  } catch (error) {
    if (accountId !== state.accountId || chatId !== state.chatId) return;
    setConnectionState("error", "Backend unavailable");
    if (state.chats.length === 0) showChatListError(error.message);
    if (state.chatId && (initial || state.messages.length === 0)) showConversationError(error.message);
  } finally {
    state.refreshing = false;
  }
}

async function selectChat(chatId) {
  const nextChatId = chatId.trim();
  if (!state.accountId || !nextChatId) return;
  const accountId = state.accountId;
  state.chatId = nextChatId;
  state.messages = [];
  resetAnalysis();
  workspace.classList.add("has-active-chat");
  conversationContext.textContent = `Telegram account ${state.accountId}`;
  conversationTitle.textContent = chatLabel(nextChatId);
  conversationSummary.replaceChildren();
  refreshButton.disabled = false;
  renderChatList();
  sendWebSocketSubscription();

  const url = new URL(window.location.href);
  url.searchParams.set("telegram_account_id", state.accountId);
  url.searchParams.set("chat_id", state.chatId);
  window.history.replaceState({}, "", url);

  try {
    await loadConversation({ initial: true });
  } catch (error) {
    if (accountId !== state.accountId || nextChatId !== state.chatId) return;
    showConversationError(error.message);
  }
}

async function loadAccount(accountId, preferredChatId = "") {
  const nextAccountId = accountId.trim();
  state.accountId = nextAccountId;
  state.chatId = "";
  state.chats = [];
  state.messages = [];
  resetAnalysis();
  workspace.classList.remove("has-active-chat");
  refreshButton.disabled = true;
  chatSearch.value = "";

  const url = new URL(window.location.href);
  url.searchParams.set("telegram_account_id", state.accountId);
  url.searchParams.delete("chat_id");
  window.history.replaceState({}, "", url);

  stopFallbackPolling();
  setConnectionState("loading", "Loading stored chats");
  try {
    const loaded = await loadChats({ initial: true });
    if (!loaded || nextAccountId !== state.accountId) return;
    setConnectionState("connected", "Backend connected");
    const firstChatId = preferredChatId || (state.chats[0] ? String(state.chats[0].chat_id) : "");
    if (firstChatId) await selectChat(firstChatId);
  } catch (error) {
    if (nextAccountId !== state.accountId) return;
    setConnectionState("error", "Backend unavailable");
    showChatListError(error.message);
  }
  sendWebSocketSubscription();
  updatePollingFallback();
  if (websocketIsOpen()) {
    setConnectionState("connected", "Live via WebSocket");
  }
}

accountForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!accountInput.value.trim()) {
    showToast("Enter the Telegram account ID to load its chats.");
    return;
  }
  loadAccount(accountInput.value);
});

manualChatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!state.accountId) {
    showToast("Load a Telegram account before opening a chat ID.");
    accountInput.focus();
    return;
  }
  if (!manualChatInput.value.trim()) {
    showToast("Enter a Telegram chat ID.");
    return;
  }
  selectChat(manualChatInput.value);
});

chatSearch.addEventListener("input", renderChatList);
refreshButton.addEventListener("click", () => refreshAll());
viewAnalysisButton.addEventListener("click", () => openAnalysisPanel({ focusClose: true }));
closeAnalysisButton.addEventListener("click", () => closeAnalysisPanel());
backToChatsButton.addEventListener("click", () => workspace.classList.remove("has-active-chat"));
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !analysisPanel.hidden) closeAnalysisPanel();
});

async function telegramRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return body;
}

function websocketIsOpen() {
  return state.websocket?.readyState === WebSocket.OPEN;
}

function usingConnectedTelegram() {
  return (
    Boolean(state.telegramSessionId) &&
    state.telegramStatus?.status === "ready" &&
    String(state.telegramStatus.telegram_account_id) === state.accountId
  );
}

function startFallbackPolling() {
  if (!state.accountId || state.pollTimer) return;
  state.pollTimer = window.setInterval(refreshAll, POLL_INTERVAL_MS);
}

function stopFallbackPolling() {
  window.clearInterval(state.pollTimer);
  state.pollTimer = null;
}

function updatePollingFallback() {
  if (websocketIsOpen()) stopFallbackPolling();
  else startFallbackPolling();
}

function sendWebSocketSubscription() {
  if (!websocketIsOpen()) return;
  const command = { type: "subscribe" };
  if (
    state.telegramSessionId &&
    (usingConnectedTelegram() || state.telegramStatus?.status !== "ready")
  ) {
    command.telegram_session_id = state.telegramSessionId;
  } else if (state.accountId) {
    command.account_id = Number(state.accountId);
  } else {
    return;
  }
  if (state.chatId) command.chat_id = Number(state.chatId);
  state.websocket.send(JSON.stringify(command));
}

function scheduleWebSocketReconnect() {
  window.clearTimeout(state.websocketReconnectTimer);
  state.websocketReconnectTimer = window.setTimeout(
    connectWebSocket,
    state.websocketReconnectMs,
  );
  state.websocketReconnectMs = Math.min(
    state.websocketReconnectMs * 2,
    WS_MAX_RECONNECT_MS,
  );
}

async function handleWebSocketEvent(event) {
  if (event.type === "connection.ready") {
    state.websocketLastPongAt = Date.now();
    sendWebSocketSubscription();
    if (state.accountId) await refreshAll();
    if (state.accountId) {
      setConnectionState("connected", "Live via WebSocket");
    }
    return;
  }
  if (event.type === "pong") {
    state.websocketLastPongAt = Date.now();
    return;
  }
  if (event.type === "subscription.ready") return;
  if (event.type === "subscription.error") {
    state.websocket?.close();
    return;
  }
  if (event.type === "resync.required") {
    if (state.accountId) await refreshAll();
    if (state.telegramSessionId) await pollTelegramLogin();
    return;
  }
  if (
    event.type === "telegram.authorization.changed" &&
    event.telegram_session_id === state.telegramSessionId
  ) {
    renderTelegramLogin(event.data);
    return;
  }
  if (
    event.type === "telegram.logged_out" &&
    event.telegram_session_id === state.telegramSessionId
  ) {
    window.localStorage.removeItem("tech4cityTelegramSession");
    state.telegramSessionId = "";
    state.telegramStatus = null;
    state.chatListRequestId += 1;
    state.conversationRequestId += 1;
    state.analysisRequestId += 1;
    telegramLoginButton.textContent = "Connect Telegram";
    telegramLoginMessage.textContent = "Telegram was logged out.";
    telegramLoginSubmit.hidden = false;
    telegramLoginSubmit.textContent = "Start login";
    telegramLogoutButton.hidden = true;
    sendWebSocketSubscription();
    return;
  }
  if (event.account_id !== Number(state.accountId)) return;
  if (event.type === "message.created") {
    if (event.chat_id === Number(state.chatId)) await loadConversation();
    return;
  }
  if (event.type === "chat.updated") {
    await loadChats();
    return;
  }
  if (
    event.type === "analysis.updated" &&
    String(event.message_id) === state.selectedMessageId
  ) {
    const selected = state.messages.find(
      (message) => String(message.message_id) === state.selectedMessageId,
    );
    if (selected) await loadAnalysis(selected, { announceError: false });
  }
  return true;
}

function connectWebSocket() {
  if (
    state.websocket &&
    [WebSocket.OPEN, WebSocket.CONNECTING].includes(state.websocket.readyState)
  ) return;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
  state.websocket = socket;
  socket.addEventListener("open", () => {
    state.websocketReconnectMs = 500;
    state.websocketLastPongAt = Date.now();
    stopFallbackPolling();
    window.clearInterval(state.websocketHeartbeatTimer);
    state.websocketHeartbeatTimer = window.setInterval(() => {
      if (!websocketIsOpen()) return;
      if (Date.now() - state.websocketLastPongAt > 60000) {
        state.websocket.close();
        return;
      }
      state.websocket.send(JSON.stringify({ type: "ping" }));
    }, 25000);
  });
  socket.addEventListener("message", (message) => {
    try {
      const event = JSON.parse(message.data);
      handleWebSocketEvent(event).catch(() => {
        updatePollingFallback();
      });
    } catch {
      // A malformed event is ignored; REST resynchronization remains available.
    }
  });
  socket.addEventListener("close", () => {
    window.clearInterval(state.websocketHeartbeatTimer);
    state.websocketHeartbeatTimer = null;
    if (state.websocket === socket) state.websocket = null;
    if (state.accountId) {
      setConnectionState("loading", "WebSocket reconnecting; polling backend");
    }
    updatePollingFallback();
    scheduleWebSocketReconnect();
  });
  socket.addEventListener("error", () => socket.close());
}

function renderTelegramLogin(login) {
  const alreadyLoaded =
    state.telegramStatus?.status === "ready" &&
    state.telegramStatus.session_id === login.session_id &&
    state.accountId === String(login.telegram_account_id);
  state.telegramStatus = login;
  const status = login.status;
  const fields = {
    wait_phone: ["Phone number", "tel", "e.g. +84123456789", "Send code"],
    wait_code: ["Telegram code", "text", "Enter the code Telegram sent", "Verify code"],
    wait_password: ["Two-step verification password", "password", login.password_hint || "", "Verify password"],
  };
  const field = fields[status];
  telegramLoginValue.value = "";
  telegramLoginValue.hidden = !field;
  telegramLoginLabel.hidden = !field;
  telegramLoginSubmit.hidden = !field;
  telegramLogoutButton.hidden = status === "logged_out";
  telegramLogoutButton.textContent = status === "ready" ? "Log out" : "Cancel login";
  if (field) {
    [telegramLoginLabel.textContent, telegramLoginValue.type, telegramLoginValue.placeholder, telegramLoginSubmit.textContent] = field;
    telegramLoginValue.autocomplete = status === "wait_password" ? "current-password" : "one-time-code";
    telegramLoginMessage.textContent =
      status === "wait_phone" ? "Enter the Telegram account phone number in international format." :
      status === "wait_code" ? "Enter the authentication code. Codes are never stored or logged." :
      "Telegram requires your two-step verification password. It is sent once and never stored.";
    telegramLoginValue.focus();
  } else if (status === "ready") {
    telegramLoginMessage.textContent = `${login.display_name || "Telegram"} is connected. Only Saved Messages are imported.`;
    telegramLoginButton.textContent = "Telegram connected";
    state.telegramSessionId = login.session_id;
    window.localStorage.setItem("tech4cityTelegramSession", login.session_id);
    if (!alreadyLoaded) {
      loadAccount(
        String(login.telegram_account_id),
        String(login.saved_messages_chat_id || login.telegram_account_id),
      );
    }
  } else if (status === "registration_required") {
    telegramLoginMessage.textContent =
      "This phone number does not have a Telegram account. Cancel this login and use an existing account.";
  } else if (status === "unsupported") {
    telegramLoginMessage.textContent =
      "Telegram requires an authorization step this app does not support. Cancel this login and use another sign-in method.";
  } else {
    telegramLoginMessage.textContent = login.error || "Waiting for Telegram…";
    telegramLoginSubmit.textContent = "Continue";
  }
  const active = ["starting", "logging_out"].includes(status);
  window.clearTimeout(state.telegramPollTimer);
  if (active && !websocketIsOpen()) {
    state.telegramPollTimer = window.setTimeout(
      pollTelegramLogin,
      LOGIN_POLL_INTERVAL_MS,
    );
  }
}

async function pollTelegramLogin() {
  if (!state.telegramSessionId) return;
  try {
    renderTelegramLogin(await telegramRequest(`/telegram/login/${encodeURIComponent(state.telegramSessionId)}`));
  } catch (error) {
    telegramLoginMessage.textContent = error.message;
    if ([401, 404, 409].includes(error.status)) {
      window.localStorage.removeItem("tech4cityTelegramSession");
      state.telegramSessionId = "";
      state.telegramStatus = null;
      state.chatListRequestId += 1;
      state.conversationRequestId += 1;
      state.analysisRequestId += 1;
      telegramLogoutButton.hidden = true;
      telegramLoginSubmit.hidden = false;
      telegramLoginSubmit.textContent = "Start login";
    } else {
      window.clearTimeout(state.telegramPollTimer);
      state.telegramPollTimer = window.setTimeout(
        pollTelegramLogin,
        LOGIN_POLL_INTERVAL_MS,
      );
    }
  }
}

telegramLoginButton.addEventListener("click", () => {
  telegramLoginDialog.showModal();
  if (state.telegramSessionId) pollTelegramLogin();
});

telegramLoginClose.addEventListener("click", () => telegramLoginDialog.close());

telegramLoginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  telegramLoginSubmit.disabled = true;
  try {
    let login;
    if (!state.telegramSessionId) {
      login = await telegramRequest("/telegram/login", { method: "POST", body: "{}" });
      state.telegramSessionId = login.session_id;
      window.localStorage.setItem("tech4cityTelegramSession", login.session_id);
      // The login response may have just set the HttpOnly ownership cookie.
      // Reconnect so the WebSocket handshake includes that new cookie.
      if (websocketIsOpen()) state.websocket.close();
    } else {
      const action = {
        wait_phone: "phone",
        wait_code: "code",
        wait_password: "password",
      }[state.telegramStatus?.status];
      if (!action) {
        login = await telegramRequest(`/telegram/login/${encodeURIComponent(state.telegramSessionId)}`);
      } else {
        login = await telegramRequest(
          `/telegram/login/${encodeURIComponent(state.telegramSessionId)}/${action}`,
          { method: "POST", body: JSON.stringify({ value: telegramLoginValue.value }) },
        );
      }
    }
    renderTelegramLogin(login);
  } catch (error) {
    telegramLoginMessage.textContent = error.message;
  } finally {
    telegramLoginValue.value = "";
    telegramLoginSubmit.disabled = false;
  }
});

telegramLogoutButton.addEventListener("click", async () => {
  telegramLogoutButton.disabled = true;
  try {
    await telegramRequest(
      `/telegram/login/${encodeURIComponent(state.telegramSessionId)}/logout`,
      { method: "POST", body: "{}" },
    );
    window.localStorage.removeItem("tech4cityTelegramSession");
    state.telegramSessionId = "";
    state.telegramStatus = null;
    state.chatListRequestId += 1;
    state.conversationRequestId += 1;
    state.analysisRequestId += 1;
    telegramLoginButton.textContent = "Connect Telegram";
    sendWebSocketSubscription();
    telegramLoginDialog.close();
  } catch (error) {
    telegramLoginMessage.textContent = error.message;
  } finally {
    telegramLogoutButton.disabled = false;
  }
});

const initialParams = new URLSearchParams(window.location.search);
const initialAccountId = initialParams.get("telegram_account_id");
const initialChatId = initialParams.get("chat_id") || "";
if (initialAccountId) {
  accountInput.value = initialAccountId;
  loadAccount(initialAccountId, initialChatId);
}
if (state.telegramSessionId) pollTelegramLogin();
connectWebSocket();
