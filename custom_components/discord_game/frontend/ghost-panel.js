class DiscordGameGhostPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._notice = "";
    this._busy = false;
    this._activeTab = "overview";
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states["sensor.discord_game_assistant"];
    const signature = state ? state.state + "|" + state.last_updated : "missing";
    if (signature !== this._lastSignature) {
      this._lastSignature = signature;
      this._diagnosticsLoaded = false;
      this._loadDiagnostics();
    } else if (!this._diagnosticsLoaded && !this._diagnosticsLoading) {
      this._loadDiagnostics();
    }
  }

  set narrow(value) {
    this._narrow = value;
    this._render();
  }

  async _loadDiagnostics() {
    if (!this._hass?.connection?.sendMessagePromise || this._diagnosticsLoading) return;
    const requestedSignature = this._lastSignature;
    this._diagnosticsLoading = true;
    try {
      const response = await this._hass.connection.sendMessagePromise({
        type: "discord_game/assistant/diagnostics",
      });
      const payload = response?.result ?? response;
      this._diagnostics = payload?.diagnostics || null;
      this._diagnosticsError = payload?.available === false
        ? "The assistant is not loaded."
        : "";
    } catch (err) {
      this._diagnostics = null;
      this._diagnosticsError = err?.message || String(err);
    } finally {
      this._diagnosticsLoading = false;
      if (requestedSignature !== this._lastSignature) {
        this._diagnosticsLoaded = false;
        this._loadDiagnostics();
      } else {
        this._diagnosticsLoaded = true;
        this._render();
      }
    }
  }

  _node(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined && text !== null) el.textContent = String(text);
    if (className) el.className = className;
    return el;
  }

  _button(label, action, secondary = false) {
    const button = this._node("button", label, secondary ? "secondary" : "");
    button.type = "button";
    button.disabled = this._busy;
    button.addEventListener("click", action);
    return button;
  }

  async _service(name, data = {}) {
    if (!this._hass || this._busy) return;
    this._busy = true;
    this._notice = "Working…";
    this._render();
    try {
      await this._hass.callService("discord_game", name, data);
      this._notice = "Command sent.";
      this._diagnosticsLoaded = false;
      await this._loadDiagnostics();
    } catch (err) {
      this._notice = "Couldn't run " + name + ": " + (err?.message || String(err));
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _section(title, description) {
    const section = this._node("section");
    const heading = this._node("h2", title);
    section.append(heading);
    if (description) section.append(this._node("p", description, "muted"));
    return section;
  }

  _render() {
    if (!this._hass) return;
    const root = this.shadowRoot;
    const preserved = new Map();
    for (const field of root.querySelectorAll("[data-preserve]")) {
      preserved.set(field.dataset.preserve, field.value);
    }
    const focusedField = root.activeElement?.dataset?.preserve;
    const selectionStart = root.activeElement?.selectionStart;
    const selectionEnd = root.activeElement?.selectionEnd;
    const restoreFormState = () => {
      const fields = [...root.querySelectorAll("[data-preserve]")];
      for (const field of fields) {
        if (preserved.has(field.dataset.preserve)) {
          field.value = preserved.get(field.dataset.preserve);
        }
      }
      if (focusedField) {
        const field = fields.find((item) => item.dataset.preserve === focusedField);
        if (field) {
          field.focus();
          if (typeof field.setSelectionRange === "function" && selectionStart !== undefined) {
            field.setSelectionRange(selectionStart, selectionEnd);
          }
        }
      }
    };
    root.replaceChildren();

    const style = this._node("style");
    style.textContent = `
      :host { display:block; color:var(--primary-text-color); }
      .page { box-sizing:border-box; max-width:1500px; margin:0 auto; padding:24px; }
      .tabs { display:flex; gap:7px; flex-wrap:wrap; margin:18px 0 16px; padding:7px; border:1px solid var(--divider-color); border-radius:14px; background:var(--card-background-color); }
      .tabs button { background:transparent; color:var(--secondary-text-color); border:1px solid transparent; padding:9px 13px; }
      .tabs button.active { background:var(--primary-color); color:var(--text-primary-color); }
      [data-tab-panel][hidden] { display:none !important; }
      .setting-help { font-size:12px; color:var(--secondary-text-color); margin-top:3px; }
      .setting-field { min-width:0; }
      header { display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
      h1 { font-size:28px; margin:0; } h2 { font-size:18px; margin:0 0 8px; }
      p { margin:6px 0; line-height:1.45; }
      .muted { color:var(--secondary-text-color); font-size:13px; }
      .status { display:inline-flex; padding:6px 10px; border-radius:16px; background:var(--secondary-background-color); }
      .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:18px 0; }
      .tile, section, .item { background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:12px; padding:16px; }
      .tile strong { display:block; font-size:22px; margin-top:5px; overflow-wrap:anywhere; }
      section { margin:14px 0; }
      .actions { display:flex; flex-wrap:wrap; gap:8px; }
      button { border:0; border-radius:8px; padding:10px 14px; color:var(--text-primary-color); background:var(--primary-color); cursor:pointer; }
      button.secondary { color:var(--primary-text-color); background:var(--secondary-background-color); border:1px solid var(--divider-color); }
      button:disabled { opacity:.55; cursor:wait; }
      .list { display:grid; gap:9px; margin-top:10px; }
      .item { padding:12px; overflow-wrap:anywhere; }
      .item pre { white-space:pre-wrap; overflow-wrap:anywhere; font:12px/1.45 monospace; background:var(--secondary-background-color); padding:10px; border-radius:8px; max-height:260px; overflow:auto; }
      label { display:block; font-size:13px; margin:10px 0 5px; color:var(--secondary-text-color); }
      input, textarea { box-sizing:border-box; width:100%; padding:10px; color:var(--primary-text-color); background:var(--primary-background-color); border:1px solid var(--divider-color); border-radius:8px; font:inherit; }
      textarea { min-height:90px; resize:vertical; }
      .formgrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; }
      .notice { margin:12px 0; color:var(--primary-color); }
      .error { color:var(--error-color); }
      @media(max-width:600px) { .page { padding:14px; } h1 { font-size:23px; } }
    `;
    root.append(style);

    const page = this._node("main", undefined, "page");
    const state = this._hass.states["sensor.discord_game_assistant"];
    const a = this._diagnostics || state?.attributes || {};
    const header = this._node("header");
    const titleWrap = this._node("div");
    titleWrap.append(this._node("h1", "GHOST control room"));
    titleWrap.append(this._node("p", "Discord assistant activity, context, memory and controls.", "muted"));
    header.append(titleWrap);
    header.append(this._node("span", state ? state.state : "sensor unavailable", "status"));
    page.append(header);

    if (this._notice) page.append(this._node("p", this._notice, "notice"));
    if (this._diagnosticsError) page.append(this._node("p", "Private diagnostics unavailable: " + this._diagnosticsError, "error"));

    const controls = this._node("div", undefined, "actions");
    if (a.paused) controls.append(this._button("Resume", () => this._service("resume")));
    else controls.append(this._button("Pause", () => this._service("pause"), true));
    controls.append(this._button("Clear pending queue", () => {
      if (confirm("Discard every pending Discord message?")) this._service("clear_queue");
    }, true));
    page.append(controls);

    const tiles = this._node("div", undefined, "grid");
    const tileData = [
      ["Queue", a.queue_length ?? 0],
      ["Processing", a.processing ? "Yes" : "No"],
      ["Conversation model", a.conversation_agent || "Not configured"],
      ["Operations model", a.operations_agent || "Not configured"],
      ["Advanced fallback", a.fallback_agent || "Not configured"],
      ["Estimated queued tokens", a.estimated_pending_tokens ?? 0],
    ];
    for (const [label, value] of tileData) {
      const tile = this._node("div", undefined, "tile");
      tile.append(this._node("span", label, "muted"), this._node("strong", value));
      tiles.append(tile);
    }
    page.append(tiles);

    const tabs = this._node("nav", undefined, "tabs");
    const tabItems = [
      ["overview", "Overview"], ["config", "Configuration"], ["queue", "Queue"],
      ["history", "History"], ["memory", "Memory"], ["manual", "Manual send"],
    ];
    for (const [key, label] of tabItems) {
      const tab = this._button(label, () => { this._activeTab = key; this._render(); }, key !== this._activeTab);
      if (key === this._activeTab) tab.classList.add("active");
      tabs.append(tab);
    }
    page.append(tabs);

    if (!state) {
      const missing = this._section("Assistant sensor not found", "The integration may still be starting, or the entity may have been renamed. Expected entity: sensor.discord_game_assistant.");
      page.append(missing);
      root.append(page);
      restoreFormState();
      return;
    }

    const settings = a.settings || {};
    const configSection = this._section("Assistant configuration", "Fine-tune behaviour without changing the model assignments in Discord Game integration settings.");
    configSection.dataset.tabPanel = "config";
    const configForm = this._node("form");
    const configGrid = this._node("div", undefined, "formgrid");
    const addNumber = (key, label, value, min, max, step = 1, help = "") => {
      const wrap = this._node("div", undefined, "setting-field");
      wrap.append(this._node("label", label));
      const field = this._node("input"); field.type = "number"; field.min = min; field.max = max; field.step = step;
      field.value = value ?? ""; field.dataset.preserve = "setting-" + key; field.name = key;
      wrap.append(field);
      if (help) wrap.append(this._node("p", help, "setting-help"));
      configGrid.append(wrap);
    };
    addNumber("fallback_after_failures", "Local attempts before API fallback", settings.fallback_after_failures ?? 2, 1, 5, 1, "How many failed local attempts are allowed before the fallback model is tried.");
    addNumber("queue_debounce_seconds", "Message grouping delay (seconds)", settings.queue_debounce_seconds ?? 2.5, 0.5, 15, 0.5, "Wait briefly to combine consecutive messages from the same conversation.");
    addNumber("max_context_messages", "Recent context messages", settings.max_context_messages ?? 20, 4, 80);
    addNumber("context_budget_chars", "Prompt budget (characters)", settings.context_budget_chars ?? 10000, 2000, 50000, 500);
    addNumber("history_limit", "Messages retained before compression", settings.history_limit ?? 60, 10, 200);
    configForm.append(configGrid);
    const typingWrap = this._node("label", "Show Discord typing indicator");
    const typing = this._node("input"); typing.type = "checkbox"; typing.checked = settings.typing_enabled !== false;
    typing.dataset.preserve = "setting-typing_enabled"; typing.name = "typing_enabled";
    typingWrap.prepend(typing); configForm.append(typingWrap);
    const channelsLabel = this._node("label", "Server channels enabled for GHOST (comma-separated channel IDs)");
    const channelsField = this._node("input"); channelsField.value = settings.assistant_group_channels || "";
    channelsField.dataset.preserve = "setting-assistant_group_channels"; channelsField.name = "assistant_group_channels";
    configForm.append(channelsLabel, channelsField);
    const promptFields = [
      ["conversation_system_prompt", "Conversation agent — extra system instructions", 5, 6000],
      ["operations_system_prompt", "Operations agent — extra system instructions", 6, 6000],
      ["advanced_system_prompt", "Advanced fallback — extra system instructions", 6, 6000],
      ["memory_system_prompt", "Memory manager — extra system instructions", 5, 4000],
    ];
    for (const [key, label, rows] of promptFields) {
      configForm.append(this._node("label", label));
      const field = this._node("textarea"); field.rows = rows; field.maxLength = key === "memory_system_prompt" ? 4000 : 6000;
      field.value = settings[key] || ""; field.dataset.preserve = "setting-" + key; field.name = key;
      configForm.append(field);
    }
    configForm.append(this._button("Save assistant configuration", async () => {
      const data = {};
      for (const field of configForm.querySelectorAll("[name]")) {
        data[field.name] = field.type === "checkbox" ? field.checked : field.type === "number" ? Number(field.value) : field.value;
      }
      if (!data.assistant_group_channels.trim().split(",").every((id) => !id.trim() || /^\d+$/.test(id.trim()))) {
        this._notice = "Server channel IDs must be numeric and separated by commas.";
        this._render(); return;
      }
      await this._service("update_settings", data);
    }));
    configSection.append(configForm);
    page.append(configSection);

    const active = this._section("Active request", "The current prompt snapshot is shown here for debugging.");
    active.dataset.tabPanel = "overview";
    if (a.active_request) {
      const current = this._node("div", undefined, "item");
      current.append(this._node("p", a.active_request.sender || a.active_request.conversation));
      current.append(this._node("p", (a.active_request.model || "") + " · " + (a.active_request.role || "" ), "muted"));
      for (const msg of a.active_request.messages || []) current.append(this._node("p", msg));
      if (a.active_request.context_snapshot) current.append(this._node("pre", a.active_request.context_snapshot));
      active.append(current);
    } else active.append(this._node("p", "Nothing is currently being processed.", "muted"));
    page.append(active);

    const contextSection = this._section("Inject temporary conversation context", "This note is held in memory only and is cleared when Home Assistant restarts. Use dm:USER_ID or guild:GUILD_ID:CHANNEL_ID.");
    contextSection.dataset.tabPanel = "overview";
    const contextCard = this._node("div", undefined, "item");
    contextCard.append(this._node("label", "Conversation key"));
    const contextKey = this._node("input");
    contextKey.dataset.preserve = "context-key";
    contextKey.value = a.active_request?.conversation || "";
    contextCard.append(contextKey);
    contextCard.append(this._node("label", "Temporary context note"));
    const contextValue = this._node("textarea");
    contextValue.rows = 4;
    contextValue.dataset.preserve = "context-value";
    contextValue.value = a.context_notes?.[contextKey.value] || "";
    contextKey.addEventListener("change", () => {
      contextValue.value = a.context_notes?.[contextKey.value] || "";
    });
    contextCard.append(contextValue);
    contextCard.append(this._button("Inject or update context", () => {
      const key = contextKey.value.trim();
      if (!key) {
        this._notice = "Enter a conversation key.";
        this._render();
        return;
      }
      this._service("set_context_note", { conversation: key, context: contextValue.value });
    }, true));
    contextSection.append(contextCard);
    page.append(contextSection);

    const queue = this._section("Pending messages", "Messages are processed in chronological order. Clearing the queue does not interrupt an active response.");
    queue.dataset.tabPanel = "queue";
    const queueList = this._node("div", undefined, "list");
    for (const item of a.pending_messages || []) {
      const card = this._node("article", undefined, "item");
      card.append(this._node("p", item.sender + " · " + item.conversation));
      card.append(this._node("p", item.timestamp, "muted"));
      const edit = this._node("textarea");
      edit.value = item.message || "";
      edit.dataset.preserve = "queue-" + item.id;
      edit.rows = 3;
      card.append(edit);
      const queueActions = this._node("div", undefined, "actions");
      queueActions.append(this._button("Save edit", () => {
        this._service("edit_queued_message", { message_id: item.id, message: edit.value });
      }, true));
      queueActions.append(this._button("Cancel message", () => {
        if (confirm("Remove this pending message from the queue?")) {
          this._service("cancel_queued_message", { message_id: item.id });
        }
      }, true));
      card.append(queueActions);
      queueList.append(card);
    }
    if (!queueList.childElementCount) queueList.append(this._node("p", "No messages waiting.", "muted"));
    queue.append(queueList);
    page.append(queue);

    const transcript = this._section("Recent transcript", "Includes model selection, context snapshots, failures and structured action outcomes.");
    transcript.dataset.tabPanel = "history";
    const transcriptList = this._node("div", undefined, "list");
    for (const item of [...(a.transcript || [])].reverse()) {
      const card = this._node("article", undefined, "item");
      card.append(this._node("p", item.sender || item.conversation || "Conversation"));
      card.append(this._node("p", [item.timestamp, item.model, item.role].filter(Boolean).join(" · "), "muted"));
      for (const msg of item.user_messages || []) card.append(this._node("p", "Message: " + msg));
      if (item.assistant) card.append(this._node("p", "GHOST: " + item.assistant));
      if (item.error) card.append(this._node("p", "Error: " + item.error, "error"));
      if (item.action_result) card.append(this._node("pre", JSON.stringify(item.action_result, null, 2)));
      if ((item.user_messages || []).length && item.timestamp && item.conversation) {
        card.append(this._button("Replay these messages", () => {
          if (confirm("Reprocess the original user messages in this conversation?")) {
            this._service("replay_transcript", { timestamp: item.timestamp, conversation: item.conversation });
          }
        }, true));
      }
      if (item.context_snapshot) {
        const details = document.createElement("details");
        details.append(this._node("summary", "View model context"));
        details.append(this._node("pre", item.context_snapshot));
        card.append(details);
      }
      transcriptList.append(card);
    }
    if (!transcriptList.childElementCount) transcriptList.append(this._node("p", "No completed conversations yet.", "muted"));
    transcript.append(transcriptList);
    page.append(transcript);

    const usage = this._section("Estimated model usage", "Calculated from the retained transcript; these are estimates, not provider billing figures.");
    usage.dataset.tabPanel = "overview";
    const usageList = this._node("div", undefined, "list");
    for (const [model, counts] of Object.entries(a.model_usage || {})) {
      const card = this._node("article", undefined, "item");
      card.append(this._node("strong", model));
      card.append(this._node("p", counts.requests + " requests · " + counts.input_tokens + " input tokens · " + counts.output_tokens + " output tokens · " + counts.errors + " errors", "muted"));
      usageList.append(card);
    }
    if (!usageList.childElementCount) usageList.append(this._node("p", "No usage recorded yet.", "muted"));
    usage.append(usageList);
    page.append(usage);

    const memories = this._section("Approved-contact memory", "Persistent memory is isolated by approved Discord user ID. Group-channel context is temporary.");
    memories.dataset.tabPanel = "memory";
    const memoryList = this._node("div", undefined, "list");
    for (const [userId, memory] of Object.entries(a.friend_memory || {})) {
      const card = this._node("article", undefined, "item");
      card.append(this._node("strong", userId));
      card.append(this._node("p", (memory.messages || 0) + " retained messages", "muted"));
      const correctedMemory = this._node("textarea");
      correctedMemory.rows = 5;
      correctedMemory.dataset.preserve = "memory-" + userId;
      correctedMemory.value = memory.summary || "";
      card.append(this._node("label", "Editable durable memory"));
      card.append(correctedMemory);
      card.append(this._button("Save corrected memory", () => {
        this._service("set_friend_memory", { user_id: userId, summary: correctedMemory.value });
      }, true));
      card.append(this._button("Clear this contact's memory", () => {
        if (confirm("Clear persistent memory for Discord user " + userId + "?")) this._service("clear_friend_memory", { user_id: userId });
      }, true));
      memoryList.append(card);
    }
    if (!memoryList.childElementCount) memoryList.append(this._node("p", "No contact memories stored yet.", "muted"));
    memories.append(memoryList);
    const injectWrap = this._node("div", undefined, "item");
    injectWrap.append(this._node("label", "Approved Discord user ID"));
    const injectUser = this._node("input");
    injectUser.dataset.preserve = "inject-memory-user";
    injectUser.inputMode = "numeric";
    injectWrap.append(injectUser);
    injectWrap.append(this._node("label", "Context to inject or correct"));
    const injectSummary = this._node("textarea");
    injectSummary.rows = 4;
    injectSummary.dataset.preserve = "inject-memory-summary";
    injectWrap.append(injectSummary);
    injectWrap.append(this._button("Save contact context", () => {
      const userId = injectUser.value.trim();
      if (!userId) {
        this._notice = "Enter an approved Discord user ID.";
        this._render();
        return;
      }
      this._service("set_friend_memory", { user_id: userId, summary: injectSummary.value });
    }, true));
    memories.append(injectWrap);
    page.append(memories);

    const approvedIds = (a.approved_users || []).join(", ") || "No approved contacts configured";
    const selectedChannels = (a.group_channels || []).join(", ") || "No GHOST server channels selected";
    const manual = this._section("Send a manual Discord message", "Approved DM IDs: " + approvedIds + ". Enabled server channel IDs: " + selectedChannels + ". Fill in one destination ID.");
    manual.dataset.tabPanel = "manual";
    const form = this._node("form");
    const fields = this._node("div", undefined, "formgrid");
    const userWrap = this._node("div");
    userWrap.append(this._node("label", "Discord user ID"));
    const userInput = this._node("input"); userInput.name = "user_id"; userInput.dataset.preserve = "manual-user"; userInput.inputMode = "numeric";
    userWrap.append(userInput);
    const channelWrap = this._node("div");
    channelWrap.append(this._node("label", "Discord channel ID"));
    const channelInput = this._node("input"); channelInput.name = "channel_id"; channelInput.dataset.preserve = "manual-channel"; channelInput.inputMode = "numeric";
    channelWrap.append(channelInput);
    fields.append(userWrap, channelWrap);
    form.append(fields);
    form.append(this._node("label", "Message"));
    const message = this._node("textarea"); message.name = "message"; message.dataset.preserve = "manual-message"; message.required = true;
    form.append(message);
    const send = this._node("button", "Send as GHOST"); send.type = "submit"; send.disabled = this._busy;
    form.append(send);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = message.value.trim();
      const userId = userInput.value.trim();
      const channelId = channelInput.value.trim();
      if (!text || (!userId && !channelId) || (userId && channelId)) {
        this._notice = "Enter a message and exactly one destination ID.";
        this._render();
        return;
      }
      message.value = "";
      await this._service("send_message", { message: text, ...(userId ? { user_id: userId } : { channel_id: channelId }) });
    });
    manual.append(form);
    page.append(manual);

    if (a.last_error) {
      const error = this._section("Latest error");
      error.dataset.tabPanel = "overview";
      error.append(this._node("p", a.last_error, "error"));
      page.append(error);
    }

    for (const panel of page.querySelectorAll("[data-tab-panel]")) {
      panel.hidden = panel.dataset.tabPanel !== this._activeTab;
    }
    root.append(page);
    restoreFormState();
  }
}

customElements.define("discord-game-ghost-panel", DiscordGameGhostPanel);
