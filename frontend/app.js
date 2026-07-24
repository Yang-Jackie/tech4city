const POLL_INTERVAL_MS = 2000;

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
        "Seed demo data or run the allowlisted Telegram bridge, then refresh.",
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
  if (initial) showChatListSkeletons();
  const query = new URLSearchParams({ telegram_account_id: state.accountId });
  const chats = await fetchJson(`/chats?${query}`);
  state.chats = chats;
  renderChatList();
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
      "Seed sanitized demo data or send a text message in an allowlisted Telegram chat.",
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
  const query = new URLSearchParams({
    telegram_account_id: state.accountId,
    chat_id: state.chatId,
  });
  try {
    const report = await fetchJson(
      `/messages/${encodeURIComponent(message.message_id)}/report?${query}`,
    );
    if (String(message.message_id) === state.selectedMessageId) renderAnalysis(report);
  } catch (error) {
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
  if (initial) showMessageSkeletons();
  const query = new URLSearchParams({ telegram_account_id: state.accountId });
  const messages = await fetchJson(
    `/chats/${encodeURIComponent(state.chatId)}/messages?${query}`,
  );
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
  state.refreshing = true;
  setConnectionState("loading", "Checking the backend");
  try {
    await Promise.all([
      loadChats({ initial }),
      state.chatId ? loadConversation({ initial }) : Promise.resolve(),
    ]);
    setConnectionState("connected", "Backend connected");
  } catch (error) {
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
  state.chatId = nextChatId;
  state.messages = [];
  resetAnalysis();
  workspace.classList.add("has-active-chat");
  conversationContext.textContent = `Telegram account ${state.accountId}`;
  conversationTitle.textContent = chatLabel(nextChatId);
  conversationSummary.replaceChildren();
  refreshButton.disabled = false;
  renderChatList();

  const url = new URL(window.location.href);
  url.searchParams.set("telegram_account_id", state.accountId);
  url.searchParams.set("chat_id", state.chatId);
  window.history.replaceState({}, "", url);

  try {
    await loadConversation({ initial: true });
  } catch (error) {
    showConversationError(error.message);
  }
}

async function loadAccount(accountId, preferredChatId = "") {
  state.accountId = accountId.trim();
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

  window.clearInterval(state.pollTimer);
  setConnectionState("loading", "Loading stored chats");
  try {
    await loadChats({ initial: true });
    setConnectionState("connected", "Backend connected");
    const firstChatId = preferredChatId || (state.chats[0] ? String(state.chats[0].chat_id) : "");
    if (firstChatId) await selectChat(firstChatId);
  } catch (error) {
    setConnectionState("error", "Backend unavailable");
    showChatListError(error.message);
  }
  state.pollTimer = window.setInterval(refreshAll, POLL_INTERVAL_MS);
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

const initialParams = new URLSearchParams(window.location.search);
const initialAccountId = initialParams.get("telegram_account_id");
const initialChatId = initialParams.get("chat_id") || "";
if (initialAccountId) {
  accountInput.value = initialAccountId;
  loadAccount(initialAccountId, initialChatId);
}