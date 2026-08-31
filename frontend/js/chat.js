/* Chatbot for the results page.
   Grounded entirely on:
     - sessionStorage.ssai_profile  → the applicant's submitted profile
     - sessionStorage.ssai_matches  → the schemes already matched (and
       explained) by the existing rule-based engine on the backend.
   The widget itself never invents anything — it just forwards the
   question, profile and matched scheme ids to /api/chat, and the backend
   answers using only data/schemes.json + the rule engine's own output. */

const SSAI_CHAT = (() => {
  let history = [];
  let panelOpen = false;
  let sending = false;

  function getContext() {
    let profile = null;
    let matches = [];
    try {
      profile = JSON.parse(sessionStorage.getItem("ssai_profile") || "null");
    } catch (e) {
      profile = null;
    }
    try {
      matches = JSON.parse(sessionStorage.getItem("ssai_matches") || "[]");
    } catch (e) {
      matches = [];
    }
    return { profile, matches };
  }

  function scrollToBottom() {
    const list = document.getElementById("chat-messages");
    list.scrollTop = list.scrollHeight;
  }

  function appendMessage(role, text) {
    const list = document.getElementById("chat-messages");
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble chat-bubble--${role}`;
    bubble.textContent = text;
    list.appendChild(bubble);
    scrollToBottom();
  }

  function appendTyping() {
    const list = document.getElementById("chat-messages");
    const bubble = document.createElement("div");
    bubble.id = "chat-typing";
    bubble.className = "chat-bubble chat-bubble--assistant chat-bubble--typing";
    bubble.innerHTML = "<span></span><span></span><span></span>";
    list.appendChild(bubble);
    scrollToBottom();
  }

  function removeTyping() {
    const el = document.getElementById("chat-typing");
    if (el) el.remove();
  }

  function setSending(state) {
    sending = state;
    const btn = document.querySelector("#chat-form button[type=submit]");
    const input = document.getElementById("chat-input");
    if (btn) btn.disabled = state;
    if (input) input.disabled = state;
  }

  async function send(message) {
    const trimmed = (message || "").trim();
    if (!trimmed || sending) return;

    appendMessage("user", trimmed);
    const priorHistory = history.slice();
    history.push({ role: "user", content: trimmed });

    setSending(true);
    appendTyping();

    const { profile, matches } = getContext();
    const scheme_ids = matches.map((m) => m.id).filter(Boolean);

    try {
      const res = await SSAI_API.sendChatMessage({
        message: trimmed,
        profile: profile || {},
        scheme_ids,
        history: priorHistory,
        language: SSAI.getLang(),
      });
      removeTyping();
      const reply = (res && res.reply) || SSAI.t("chat_error");
      appendMessage("assistant", reply);
      history.push({ role: "assistant", content: reply });
    } catch (err) {
      console.error(err);
      removeTyping();
      appendMessage("assistant", SSAI.t("chat_error"));
    } finally {
      setSending(false);
    }
  }

  function togglePanel(forceOpen) {
    const panel = document.getElementById("chat-panel");
    const toggle = document.getElementById("chat-toggle");
    panelOpen = typeof forceOpen === "boolean" ? forceOpen : !panelOpen;
    panel.classList.toggle("chat-panel--open", panelOpen);
    toggle.setAttribute("aria-expanded", String(panelOpen));
    if (panelOpen) {
      const input = document.getElementById("chat-input");
      if (input) input.focus();
    }
  }

  function init() {
    const panel = document.getElementById("chat-panel");
    const toggle = document.getElementById("chat-toggle");
    if (!panel || !toggle) return; // chatbot markup not present on this page

    const { matches } = getContext();
    if (!matches.length) {
      // No matched schemes on this visit — nothing grounded to chat about.
      toggle.style.display = "none";
      return;
    }

    toggle.addEventListener("click", () => togglePanel());
    document.getElementById("chat-close").addEventListener("click", () => togglePanel(false));

    document.getElementById("chat-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const input = document.getElementById("chat-input");
      const value = input.value;
      input.value = "";
      send(value);
    });

    document.querySelectorAll(".chat-suggestion").forEach((btn) => {
      btn.addEventListener("click", () => send(btn.textContent));
    });

    appendMessage("assistant", SSAI.t("chat_greeting"));
  }

  document.addEventListener("DOMContentLoaded", init);

  return { send };
})();
