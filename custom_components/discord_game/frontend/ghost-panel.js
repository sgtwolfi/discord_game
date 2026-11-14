class DiscordGameGhostPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = "chats";
    this._selectedConversation = null;
    this._chat = null;
    this._busy = false;
    this._notice = "";
    this._diagnosticsLoaded = false;
    this._diagnosticsLoading = false;
    this._chatLoading = false;
    this._filter = "";
    this._capabilities = null;
    this._capabilitiesLoading = false;
    this._capabilitiesFilter = "";
    this._capabilityDomain = "all";
    this._modeOverride = null;
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states["sensor.discord_game_assistant"];
    const signature = state ? state.state + "|" + state.last_updated + "|" + state.attributes.diagnostics_revision : "missing";
    if (signature !== this._lastSignature) {
      this._lastSignature = signature;
      this._diagnosticsLoaded = false;
      this._loadDiagnostics();
    } else if (!this._diagnosticsLoaded && !this._diagnosticsLoading) {
      this._loadDiagnostics();
    }
  }

  _el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (cls) node.className = cls;
    return node;
  }

  _button(text, fn, secondary) {
    const b = this._el("button", text, secondary ? "btn secondary" : "btn");
    b.type = "button";
    b.disabled = this._busy;
    b.addEventListener("click", fn);
    return b;
  }

  async _loadDiagnostics() {
    if (!this._hass || this._diagnosticsLoading) return;
    this._diagnosticsLoading = true;
    try {
      const raw = await this._hass.connection.sendMessagePromise({ type: "discord_game/assistant/diagnostics" });
      const data = raw && raw.result ? raw.result : raw;
      this._diagnostics = data && data.diagnostics ? data.diagnostics : null;
      this._diagnosticsError = data && data.available === false ? "The assistant is not loaded." : "";
      if (this._diagnostics && !this._selectedConversation) {
        const first = (this._diagnostics.conversations || [])[0];
        if (first) this._selectedConversation = first.key;
      }
      if (this._selectedConversation && this._diagnostics) await this._loadConversation(false);
    } catch (err) {
      this._diagnosticsError = err && err.message ? err.message : String(err);
    } finally {
      this._diagnosticsLoading = false;
      this._diagnosticsLoaded = true;
      this._render();
    }
  }

  async _loadConversation(renderAfter) {
    if (!this._selectedConversation || !this._hass) {
      this._chat = null;
      if (renderAfter) this._render();
      return;
    }
    this._chatLoading = true;
    try {
      const raw = await this._hass.connection.sendMessagePromise({
        type: "discord_game/assistant/conversation",
        conversation: this._selectedConversation
      });
      const data = raw && raw.result ? raw.result : raw;
      this._chat = data && data.available ? data : null;
      this._chatError = data && data.error ? data.error : "";
    } catch (err) {
      this._chat = null;
      this._chatError = err && err.message ? err.message : String(err);
    } finally {
      this._chatLoading = false;
      if (renderAfter !== false) this._render();
    }
  }

  async _selectConversation(key) {
    this._selectedConversation = key;
    this._chat = null;
    await this._loadConversation(true);
  }

  async _service(name, data, reload) {
    if (!this._hass || this._busy) return false;
    this._busy = true;
    this._notice = "Saving…";
    this._render();
    try {
      await this._hass.callService("discord_game", name, data || {});
      if (reload) {
        this._notice = "Saved. Discord Game is reloading with the new settings.";
        this._diagnosticsLoaded = false;
      } else {
        this._notice = "Done.";
        await this._loadDiagnostics();
      }
      return true;
    } catch (err) {
      this._notice = "That did not work: " + (err && err.message ? err.message : String(err));
      return false;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _conversationLabel(item) {
    return item.label || (item.kind === "friend" ? "Discord friend" : "Server group");
  }

  _avatar(label, url, className) {
    const fallback = String(label || "?").trim().slice(0, 1).toUpperCase() || "?";
    const node = this._el("div", fallback, className || "avatar");
    if (url && /^https:\/\/(?:cdn\.discordapp\.com|media\.discordapp\.net)\//i.test(url)) {
      const image = this._el("img");
      image.src = url;
      image.alt = String(label || "Discord user") + " profile picture";
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => { node.textContent = fallback; }, { once: true });
      node.replaceChildren(image);
    }
    return node;
  }

  _render() {
    if (!this._hass) return;
    const root = this.shadowRoot;
    const saved = new Map();
    for (const field of root.querySelectorAll("[data-keep]")) saved.set(field.dataset.keep, field.value);
    const focusKey = root.activeElement && root.activeElement.dataset ? root.activeElement.dataset.keep : null;
    const start = root.activeElement && root.activeElement.selectionStart;
    const end = root.activeElement && root.activeElement.selectionEnd;
    root.replaceChildren();

    const style = this._el("style");
    style.textContent = `
      :host{display:block;color:var(--primary-text-color);--ghost-accent:var(--primary-color)}
      *{box-sizing:border-box}
      .shell{max-width:1700px;margin:0 auto;padding:22px;min-height:calc(100vh - 56px)}
      .top{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}
      .brand{display:flex;align-items:center;gap:13px}
      .mark{width:44px;height:44px;border-radius:14px;background:var(--secondary-background-color);display:grid;place-items:center;font-size:23px}
      h1{font-size:25px;line-height:1.1;margin:0;font-weight:750;letter-spacing:-.5px}
      h2{font-size:17px;margin:0 0 5px}
      h3{font-size:14px;margin:0 0 8px}
      p{margin:5px 0;line-height:1.45}
      .muted{color:var(--secondary-text-color);font-size:12px}
      .status{padding:7px 11px;border:1px solid var(--divider-color);border-radius:20px;font-size:12px;background:var(--card-background-color)}
      .status:before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--success-color,var(--primary-color));margin-right:7px}
      .nav{display:flex;gap:6px;padding:6px;border:1px solid var(--divider-color);background:var(--card-background-color);border-radius:14px;margin-bottom:16px;overflow:auto}
      .nav button{white-space:nowrap;border:0;background:transparent;color:var(--secondary-text-color);padding:10px 15px;border-radius:10px;font:inherit;font-size:13px;cursor:pointer}
      .nav button.active{background:var(--primary-color);color:var(--text-primary-color);font-weight:650}
      .workspace{display:grid;grid-template-columns:290px minmax(0,1fr);gap:15px;min-height:0;align-items:stretch}
      .sidebar,.main,.panel{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:16px;min-width:0}
      .sidebar{padding:13px;display:flex;flex-direction:column;max-height:calc(100vh - 205px);min-height:560px}
      .sidehead{display:flex;justify-content:space-between;align-items:center;padding:5px 5px 12px}
      .sidehead strong{font-size:13px}
      .search{width:100%;margin:0 0 12px}
      input,textarea{font:inherit;color:var(--primary-text-color);background:var(--primary-background-color);border:1px solid var(--divider-color);border-radius:9px;padding:10px 11px;width:100%;outline:none}
      input:focus,textarea:focus{border-color:var(--primary-color);box-shadow:0 0 0 1px var(--primary-color)}
      textarea{resize:vertical;min-height:90px}
      .conversation-list{overflow:auto;display:flex;flex-direction:column;gap:4px}
      .person{display:flex;align-items:flex-start;gap:10px;text-align:left;border:1px solid transparent;border-radius:11px;padding:10px;background:transparent;color:var(--primary-text-color);cursor:pointer;width:100%}
      .person:hover{background:var(--secondary-background-color)}
      .person.selected{background:var(--secondary-background-color);border-color:var(--primary-color)}
      .avatar{width:38px;height:38px;flex:0 0 38px;border-radius:50%;display:grid;place-items:center;background:var(--secondary-background-color);font-size:14px;font-weight:700;overflow:hidden}
      .avatar img{width:100%;height:100%;display:block;object-fit:cover}
      .chatidentity{display:flex;align-items:center;gap:12px;min-width:0}
      .chatavatar{width:42px;height:42px;flex:0 0 42px}
      .personbody{min-width:0;flex:1}
      .personname{font-size:13px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .preview{font-size:11px;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:4px}
      .personmeta{font-size:10px;color:var(--secondary-text-color);margin-top:4px}
      .main{display:flex;flex-direction:column;height:calc(100vh - 245px);min-height:560px;overflow:hidden}
      .chathead{padding:17px 20px;border-bottom:1px solid var(--divider-color);display:flex;align-items:center;justify-content:space-between;gap:12px}
      .chathead strong{font-size:15px}
      .messages{padding:20px;display:flex;flex-direction:column;gap:11px;overflow:auto;overflow-anchor:auto;overscroll-behavior:contain;flex:1;min-height:0;max-height:none;scroll-behavior:auto}
      .message{max-width:min(78%,760px);padding:10px 13px;border-radius:13px;background:var(--secondary-background-color);align-self:flex-start;overflow-wrap:anywhere}
      .message.ghost{align-self:flex-end;background:color-mix(in srgb,var(--primary-color) 16%,var(--card-background-color));border:1px solid color-mix(in srgb,var(--primary-color) 30%,var(--divider-color))}
      .message .who{font-size:10px;color:var(--secondary-text-color);margin-bottom:5px;font-weight:650}
      .message .body{font-size:13px;white-space:pre-wrap;line-height:1.5}
      .message .time{font-size:10px;color:var(--secondary-text-color);margin-top:6px;text-align:right}
      .composer{padding:13px 16px;border-top:1px solid var(--divider-color);display:flex;align-items:flex-end;gap:9px;background:var(--card-background-color);flex:0 0 auto}
      .composer textarea{min-height:48px;max-height:180px;resize:vertical;flex:1}
      .send{height:46px;min-width:84px}
      button{font:inherit}
      .btn{border:0;border-radius:9px;padding:10px 14px;background:var(--primary-color);color:var(--text-primary-color);font-size:12px;font-weight:650;cursor:pointer}
      .btn.secondary{background:var(--secondary-background-color);border:1px solid var(--divider-color);color:var(--primary-text-color)}
      .btn:disabled{opacity:.5;cursor:wait}
      .actions{display:flex;flex-wrap:wrap;gap:8px}
      .empty{margin:auto;text-align:center;max-width:390px;padding:30px;color:var(--secondary-text-color)}
      .empty strong{display:block;color:var(--primary-text-color);font-size:16px;margin-bottom:7px}
      .pagegrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
      .panel{padding:18px;margin-bottom:14px}
      .panelhead{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:13px}
      .fieldgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
      label{display:block;color:var(--secondary-text-color);font-size:12px;margin:10px 0 5px}
      .help{font-size:11px;color:var(--secondary-text-color);margin-top:4px}
      .field{min-width:0}
      .prompt{min-height:150px;width:100%}
      .prompthead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:14px}
      .prompthead label{margin:0}
      .defaultbadge{display:inline-block;border:1px solid var(--divider-color);border-radius:20px;padding:3px 8px;font-size:10px;color:var(--secondary-text-color);letter-spacing:.04em}
      .caprow{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--divider-color)}
      .caprow:last-child{border:0}
      .caprow label{display:flex;align-items:center;gap:7px;white-space:nowrap}
      .caprow input[type=checkbox]{width:18px;height:18px;accent-color:var(--primary-color)}
      .contactrow{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr) auto;gap:8px;align-items:center;padding:9px 0;border-bottom:1px solid var(--divider-color)}
      .contactrow:last-child{border-bottom:0}
      .notice{padding:10px 13px;background:var(--secondary-background-color);border-radius:10px;font-size:12px;margin:0 0 12px}
      .error{color:var(--error-color)}
      .statrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px}
      .stat{padding:14px;border:1px solid var(--divider-color);border-radius:12px;background:var(--card-background-color)}
      .stat b{display:block;font-size:20px;line-height:1.3;margin-top:4px;overflow-wrap:anywhere}
      .list{display:flex;flex-direction:column;gap:8px}
      .activity{padding:12px;border:1px solid var(--divider-color);border-radius:11px}
      .memorybox{padding:12px;border:1px solid var(--divider-color);border-radius:11px;margin:9px 0}
      .memoryline{padding:7px 0;border-bottom:1px solid var(--divider-color);font-size:12px}
      .memoryline:last-child{border:0}
      details summary{cursor:pointer;color:var(--secondary-text-color);font-size:12px;margin:8px 0}
      pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--secondary-background-color);padding:10px;border-radius:9px;max-height:260px;overflow:auto;font-size:11px}
      .footnote{font-size:11px;color:var(--secondary-text-color);margin-top:8px}
      @media(max-width:850px){.workspace{grid-template-columns:1fr}.sidebar{max-height:330px;min-height:220px}.conversation-list{max-height:235px}.main{height:70vh;min-height:540px}.messages{max-height:none}}
      @media(max-width:560px){.shell{padding:10px}.top{align-items:flex-start}.workspace{gap:10px}.message{max-width:92%}.composer{padding:10px}.send{min-width:65px}.contactrow{grid-template-columns:1fr}.nav{margin-bottom:10px}}
    `;
    root.append(style);

    const shell = this._el("main", null, "shell");
    const state = this._hass.states["sensor.discord_game_assistant"];
    const d = this._diagnostics || {};
    const head = this._el("header", null, "top");
    const brand = this._el("div", null, "brand");
    brand.append(this._el("div", "👻", "mark"));
    const title = this._el("div");
    title.append(this._el("h1", "GHOST", ""));
    title.append(this._el("p", "Discord command centre", "muted"));
    brand.append(title);
    head.append(brand);
    head.append(this._el("span", state ? (state.state || "unknown") : "Assistant unavailable", "status"));
    shell.append(head);

    if (this._notice) shell.append(this._el("div", this._notice, "notice"));
    if (this._diagnosticsError) shell.append(this._el("div", "Diagnostics unavailable: " + this._diagnosticsError, "notice error"));

    const nav = this._el("nav", null, "nav");
    const views = [["chats","Messages"],["memories","Memories"],["settings","Configuration"],["activity","Activity"]];
    for (const item of views) {
      const b = this._el("button", item[1], this._view === item[0] ? "active" : "");
      b.addEventListener("click", () => {
        this._view = item[0];
        this._render();
        if (item[0] === "settings" && !this._capabilities && !this._capabilitiesLoading) this._loadCapabilities();
      });
      nav.append(b);
    }
    shell.append(nav);

    if (!this._diagnostics && this._view !== "settings") {
      const loading = this._el("section", null, "panel");
      loading.append(this._el("h2", "Connecting to GHOST"));
      loading.append(this._el("p", this._diagnosticsError || "Waiting for private assistant diagnostics…", "muted"));
      shell.append(loading);
      root.append(shell);
      return;
    }

    if (this._view === "chats") this._renderChats(shell, d);
    if (this._view === "settings") this._renderSettings(shell, d);
    if (this._view === "memories") this._renderMemories(shell, d);
    if (this._view === "activity") this._renderActivity(shell, d);

    root.append(shell);
    for (const field of root.querySelectorAll("[data-keep]")) {
      if (saved.has(field.dataset.keep)) field.value = saved.get(field.dataset.keep);
    }
    if (focusKey) {
      const field = [...root.querySelectorAll("[data-keep]")].find((x) => x.dataset.keep === focusKey);
      if (field) {
        field.focus();
        if (typeof field.setSelectionRange === "function" && start !== undefined) field.setSelectionRange(start, end);
      }
    }
    // Every conversation opens at its newest message; no manual scrolling needed.
    requestAnimationFrame(() => {
      const messages = root.querySelector(".messages");
      if (messages) messages.scrollTop = messages.scrollHeight;
    });
  }

  _renderChats(shell, d) {
    const stat = this._el("div", null, "statrow");
    const queued = this._el("div", null, "stat"); queued.append(this._el("span", "Queued messages", "muted"), this._el("b", d.queue_length || 0));
    const status = this._el("div", null, "stat"); status.append(this._el("span", "Assistant", "muted"), this._el("b", d.processing ? "Working" : d.paused ? "Paused" : d.last_error ? "Needs attention" : d.enabled ? "Ready" : "Disabled"));
    const liveStatus = this._el("div", null, "stat"); liveStatus.append(this._el("span", (d.owner_name || "Harvey") + " live status", "muted"), this._el("b", d.owner_status_value || "Unavailable"));
    const friends = this._el("div", null, "stat"); friends.append(this._el("span", "Approved friends", "muted"), this._el("b", (d.contacts || []).length));
    const groups = this._el("div", null, "stat"); groups.append(this._el("span", "Server chats", "muted"), this._el("b", (d.groups || []).length));
    stat.append(queued, status, liveStatus, friends, groups);
    shell.append(stat);

    if (d.active_request) {
      const active = d.active_request;
      const card = this._el("section", null, "panel");
      card.append(this._el("h2", "Currently processing"));
      card.append(this._el("p", [
        active.sender || "Discord contact",
        active.role || "agent",
        active.request_kind || "",
        active.model || "Model not selected",
        active.stage || "Working"
      ].filter(Boolean).join(" · "), "help"));
      if (active.messages && active.messages.length) {
        card.append(this._el("p", active.messages.join(" | "), "muted"));
      }
      if (active.models_attempted && active.models_attempted.length) {
        card.append(this._el("p", "Models attempted: " + active.models_attempted.join(" → "), "muted"));
      }
      if (active.retry_targets && active.retry_targets.length) {
        card.append(this._el("p", "Retrying failed targets only: " + active.retry_targets.join(", "), "muted"));
      }
      shell.append(card);
    }

    const workspace = this._el("div", null, "workspace");
    const side = this._el("aside", null, "sidebar");
    const sidehead = this._el("div", null, "sidehead");
    sidehead.append(this._el("strong", "CONVERSATIONS"));
    sidehead.append(this._el("span", (d.conversations || []).length, "muted"));
    side.append(sidehead);
    const search = this._el("input", null, "search");
    search.placeholder = "Find a friend or group…";
    search.value = this._filter;
    search.addEventListener("input", () => {
      this._filter = search.value;
      const needle = this._filter.toLowerCase();
      for (const row of side.querySelectorAll(".person")) row.hidden = !row.dataset.search.includes(needle);
    });
    side.append(search);
    const list = this._el("div", null, "conversation-list");
    const conversations = d.conversations || [];
    const ordered = [...conversations].sort((a,b) => (a.kind === b.kind ? 0 : a.kind === "friend" ? -1 : 1));
    for (const item of ordered) {
      const row = this._el("button", null, "person" + (item.key === this._selectedConversation ? " selected" : ""));
      row.dataset.search = (this._conversationLabel(item) + " " + (item.subtitle || "")).toLowerCase();
      const initial = item.kind === "friend"
        ? this._avatar(this._conversationLabel(item), item.avatar_url, "avatar")
        : this._el("div", "#", "avatar");
      const body = this._el("div", null, "personbody");
      body.append(this._el("div", this._conversationLabel(item), "personname"));
      body.append(this._el("div", item.last_message || item.subtitle || (item.kind === "friend" ? "No messages yet" : "Server channel"), "preview"));
      body.append(this._el("div", item.kind === "friend" ? "FRIEND · " + item.message_count + " messages" : "GROUP · " + item.message_count + " messages", "personmeta"));
      row.append(initial, body);
      row.addEventListener("click", () => this._selectConversation(item.key));
      list.append(row);
    }
    if (!list.childElementCount) list.append(this._el("div", "No approved friends or GHOST group channels yet. Add them in Configuration.", "empty"));
    side.append(list);

    const main = this._el("section", null, "main");
    const selected = conversations.find((x) => x.key === this._selectedConversation);
    if (!selected) {
      const empty = this._el("div", null, "empty");
      empty.append(this._el("strong", "Your GHOST inbox"));
      empty.append(this._el("p", "Choose a friend or server group on the left to view its conversation and send a message as GHOST."));
      main.append(empty);
    } else {
      const chathead = this._el("div", null, "chathead");
      const heading = this._el("div", null, "chatidentity");
      if (selected.kind === "friend") heading.append(this._avatar(this._conversationLabel(selected), selected.avatar_url, "avatar chatavatar"));
      const identity = this._el("div");
      identity.append(this._el("strong", this._conversationLabel(selected)));
      identity.append(this._el("p", selected.subtitle || (selected.kind === "friend" ? "Private direct message" : "Server group conversation"), "muted"));
      heading.append(identity);
      chathead.append(heading);
      const actions = this._el("div", null, "actions");
      if (d.paused) actions.append(this._button("Resume", () => this._service("resume", {})));
      else actions.append(this._button("Pause", () => this._service("pause", {}), true));
      chathead.append(actions);
      main.append(chathead);

      const messages = this._el("div", null, "messages");
      if (this._chatLoading) messages.append(this._el("div", "Loading conversation…", "empty"));
      else if (this._chatError) messages.append(this._el("div", this._chatError, "empty error"));
      else {
        const items = this._chat && this._chat.messages ? this._chat.messages : [];
        for (const msg of items) {
          const ghost = msg.role === "assistant";
          const bubble = this._el("article", null, "message" + (ghost ? " ghost" : ""));
          bubble.append(this._el("div", ghost ? "GHOST" : (msg.sender || "Discord user"), "who"));
          bubble.append(this._el("div", msg.content || "", "body"));
          let time = "";
          if (msg.timestamp) {
            const date = new Date(msg.timestamp);
            time = isNaN(date.getTime()) ? msg.timestamp : date.toLocaleString();
          }
          bubble.append(this._el("div", time + (msg.model ? " · " + msg.model : "") + (msg.manual ? " · manual" : ""), "time"));
          messages.append(bubble);
        }
        if (!items.length) messages.append(this._el("div", "No messages recorded yet. Send the first message below, or wait for this contact to message GHOST.", "empty"));
      }
      main.append(messages);

      const composer = this._el("form", null, "composer");
      const input = this._el("textarea");
      input.placeholder = "Message as GHOST… (Enter to send, Shift + Enter for a new line)";
      input.rows = 2;
      input.dataset.keep = "chat-composer";
      const send = this._el("button", this._busy ? "Sending…" : "Send", "btn send");
      send.type = "submit";
      send.disabled = this._busy;
      composer.append(input, send);
      const sendMessage = async (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text || this._busy) return;
        const key = this._selectedConversation;
        const userId = key.startsWith("dm:") ? key.slice(3) : "";
        const channelId = key.startsWith("guild:") ? key.split(":").pop() : "";
        input.value = "";
        const ok = await this._service("send_message", { message: text, ...(userId ? { user_id: userId } : { channel_id: channelId }) });
        if (ok) await this._selectConversation(key);
      };
      composer.addEventListener("submit", sendMessage);
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          composer.requestSubmit();
        }
      });
      main.append(composer);
    }
    workspace.append(side, main);
    shell.append(workspace);
    if (d.last_error) shell.append(this._el("p", "Latest assistant error: " + d.last_error, "muted error"));
  }

  async _loadCapabilities() {
    if (!this._hass || this._capabilitiesLoading) return;
    this._capabilitiesLoading = true;
    try {
      const raw = await this._hass.connection.sendMessagePromise({ type: "discord_game/assistant/capabilities" });
      this._capabilities = raw && raw.result ? raw.result : raw;
    } catch (err) {
      this._capabilities = { available: false, error: err && err.message ? err.message : String(err), entities: [] };
    } finally {
      this._capabilitiesLoading = false;
      if (this._view === "settings") this._render();
    }
  }

  async _setCapability(entity, exposed) {
    if (!this._hass || this._busy) return;
    this._busy = true;
    this._notice = (exposed ? "Exposing " : "Removing access to ") + entity.name + "…";
    this._render();
    try {
      await this._hass.connection.sendMessagePromise({ type: "discord_game/assistant/capability/set", entity_id: entity.entity_id, exposed });
      entity.exposed = exposed;
      this._notice = entity.name + (exposed ? " is now available to Assist." : " is no longer exposed to Assist.");
      this._capabilities.exposed_count = (this._capabilities.entities || []).filter(x => x.exposed).length;
    } catch (err) {
      this._notice = "Could not change access: " + (err && err.message ? err.message : String(err));
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _renderSettings(shell, d) {
    const settings = d.settings || {};
    const defaults = settings.default_prompts || {};
    if (!this._capabilities && !this._capabilitiesLoading) this._loadCapabilities();
    const agentsPanel = this._el("section", null, "panel");
    agentsPanel.append(this._el("h2", "Assigned conversation agents"));
    const agentGrid = this._el("div", null, "fieldgrid");
    const assigned = d.mode === "api"
      ? [["API conversation agent", d.conversation_agent], ["Memory", "GHOST-managed; independent of model"]]
      : [["Conversation", d.conversation_agent], ["Operations", d.operations_agent], ["Memory", "Evidence-only (no model)"], ["Fallback", d.fallback_agent]];
    for (const item of assigned) {
      const cell = this._el("div", null, "field");
      cell.append(this._el("label", item[0]));
      cell.append(this._el("strong", item[1] || "Not selected"));
      agentGrid.append(cell);
    }
    agentsPanel.append(agentGrid);
    agentsPanel.append(this._el("p", d.mode === "api"
      ? "API Mode uses one Home Assistant conversation agent for chat, status questions and actions. Its model, system prompt and tool/function configuration stay in that agent's own settings. GHOST still injects the correct contact's saved memory and records verified outcomes; changing models does not remove memory. For group-chat safety, GHOST only responds when directly mentioned or replied to."
      : "Local Mode splits work between the Conversation, Operations and optional Fallback agents. GHOST supplies short role-specific prompts and keeps memory deterministic, so no memory model is needed.", "help"));
    agentsPanel.append(this._el("p", "Entity exposure and script access are still managed by Home Assistant Assist. The capability manager below lets you expose the exact entities and scripts. Exposing a script makes it available as a tool; it does not automatically explain its arguments or purpose to a weak model, so give scripts clear names and descriptions.", "help"));
    shell.append(agentsPanel);

    const panel = this._el("section", null, "panel");
    panel.append(this._el("h2", "Assistant behaviour"));
    panel.append(this._el("p", "Choose how GHOST uses Home Assistant conversation agents. Memory, contact isolation and action verification remain owned by GHOST in both modes.", "muted"));
    const form = this._el("form");
    const modeWrap = this._el("div", null, "field");
    modeWrap.append(this._el("label", "Assistant mode"));
    const modeSelect = this._el("select");
    for (const [value, label] of [["local", "Local Mode — multi-agent, small-model workflow"], ["api", "API Mode — one native Home Assistant agent"]]) {
      const option = this._el("option", label); option.value = value; modeSelect.append(option);
    }
    modeSelect.name = "assistant_mode"; modeSelect.value = this._modeOverride || settings.assistant_mode || d.mode || "local";
    modeSelect.dataset.keep = "cfg-assistant_mode";
    modeWrap.append(modeSelect);
    modeWrap.append(this._el("p", modeSelect.value === "api"
      ? "Configure the provider, model, system prompt and available tools in the selected Home Assistant conversation agent. GHOST adds private memory and keeps its own conversation records."
      : "Assign separate Conversation, Operations and optional Fallback agents in Discord Game → Configure. Use small local models for narrow tasks; keep tool access restricted.", "help"));
    modeSelect.addEventListener("change", () => {
      this._modeOverride = modeSelect.value;
      this._render();
    });
    form.append(modeWrap);
    const groupWrap = this._el("div", null, "field");
    groupWrap.append(this._el("label", "Group-chat relevance model"));
    const relevanceAgent = this._el("input");
    relevanceAgent.name = "group_relevance_agent";
    relevanceAgent.value = settings.group_relevance_agent || (modeSelect.value === "local" ? d.conversation_agent || "" : "");
    relevanceAgent.placeholder = "conversation.ollama_local";
    relevanceAgent.dataset.keep = "cfg-group_relevance_agent";
    groupWrap.append(relevanceAgent);
    groupWrap.append(this._el("p", "Select a local Home Assistant conversation agent with no HA control tools. It decides whether GHOST should join group conversations. In API Mode this prevents group text being sent to the tool-enabled API agent just for relevance.", "help"));
    const mentionLabel = this._el("label", "Require @mention or reply in group chats");
    const mentionRequired = this._el("input");
    mentionRequired.type = "checkbox";
    mentionRequired.name = "group_require_mention";
    mentionRequired.checked = !!settings.group_require_mention;
    mentionRequired.dataset.keep = "cfg-group_require_mention";
    mentionLabel.prepend(mentionRequired);
    groupWrap.append(mentionLabel);
    groupWrap.append(this._el("p", "When enabled, unaddressed messages are ignored without a model call. When disabled, the local relevance model infers whether GHOST should respond.", "help"));
    form.append(groupWrap);
    const reminderWrap = this._el("div", null, "field");
    reminderWrap.append(this._el("label", "Local Mode reminder script entity"));
    const reminderScript = this._el("input");
    reminderScript.name = "local_reminder_script";
    reminderScript.value = settings.local_reminder_script || "script.set_timer_alarm_or_reminder";
    reminderScript.dataset.keep = "cfg-local_reminder_script";
    if (modeSelect.value === "api") reminderScript.type = "hidden";
    reminderWrap.append(reminderScript);
    if (modeSelect.value !== "api") {
      reminderWrap.append(this._el("p", "Local Mode calls this script directly for clear private-DM reminders, so a tiny model does not have to discover or invoke a tool. It should accept name plus either duration_seconds or alarm_time (and optional date), and return success: true. GHOST does not send announce_message or text fields unless a future explicit option is added.", "help"));
    }
    form.append(reminderWrap);
    const ownerWrap = this._el("div", null, "field");
    ownerWrap.append(this._el("label", "Your name (for personal activity questions)"));
    const ownerName = this._el("input");
    ownerName.name = "owner_name";
    ownerName.value = settings.owner_name || "Harvey";
    ownerName.placeholder = "Harvey";
    ownerName.dataset.keep = "cfg-owner_name";
    ownerWrap.append(ownerName);
    ownerWrap.append(this._el("p", "Questions such as “what's Harvey doing?” read the personal status helper below, not a Discord friend profile.", "help"));
    form.append(ownerWrap);
    const statusWrap = this._el("div", null, "field");
    statusWrap.append(this._el("label", "Personal live status helper"));
    const statusEntity = this._el("input");
    statusEntity.name = "ghost_status_entity";
    statusEntity.value = settings.ghost_status_entity || "input_text.ghost_status";
    statusEntity.placeholder = "input_text.ghost_status";
    statusEntity.dataset.keep = "cfg-ghost_status_entity";
    statusWrap.append(statusEntity);
    statusWrap.append(this._el("p", "GHOST reads this entity directly from Home Assistant as your current activity/status. It is also answered deterministically, so it does not need to be exposed to Assist or enabled as an AI tool.", "help"));
    form.append(statusWrap);

    const grid = this._el("div", null, "fieldgrid");
    const number = (key, title, value, min, max, step, help) => {
      const wrap = this._el("div", null, "field");
      wrap.append(this._el("label", title));
      const input = this._el("input"); input.type = "number"; input.min = min; input.max = max; input.step = step || 1;
      input.name = key; input.value = value; input.dataset.keep = "cfg-" + key;
      wrap.append(input);
      if (help) wrap.append(this._el("p", help, "help"));
      grid.append(wrap);
    };
    number("fallback_after_failures", "Retries after a model call error", settings.fallback_after_failures ?? 2, 1, 5, 1, "This retries a failed model call, not an action. GHOST never blindly repeats an action that may have partially succeeded. Activity records every agent actually attempted.");
    number("queue_debounce_seconds", "Message grouping delay (seconds)", settings.queue_debounce_seconds ?? 2.5, .5, 15, .5, "Briefly groups rapid messages from the same conversation.");
    number("max_context_messages", "Active conversation context messages", settings.max_context_messages ?? 12, 4, 80, 1, "Recent messages from this conversation supplied to the response model.");
    number("memory_idle_seconds", "Idle time before memory consolidation (seconds)", settings.memory_idle_seconds ?? 300, 30, 3600, 30, "GHOST waits this long after the last incoming message and an empty queue before consolidating memories.");
    number("memory_batch_messages", "Messages per person to consolidate", settings.memory_batch_messages ?? 20, 1, 100, 1, "For each approved person who spoke during the active period, use their most recent N messages.");
    number("group_continuity_seconds", "Group conversation follow-up window (seconds)", settings.group_continuity_seconds ?? 300, 0, 1800, 30, "Keeps clear follow-ups connected to GHOST's recent reply. Set to 0 to disable this shortcut; HA actions and live-state queries still require a direct mention or reply.");
    number("history_limit", "Raw messages retained after consolidation", settings.history_limit ?? 8, 1, 200, 1, "Keeps this many recent raw messages available alongside the durable summary.");
    number("conversation_history_limit", "Messages kept in the visible chat history", settings.conversation_history_limit ?? 500, 50, 2000, 10, "Applies to friend DMs and server-group transcripts in the panel.");
    number("context_budget_chars", "Maximum prompt size (characters)", settings.context_budget_chars ?? 10000, 2000, 50000, 500, "Hard limit for the complete prompt sent to an agent.");
    form.append(grid);
    const groupChannelsHidden = this._el("input");
    groupChannelsHidden.type = "hidden";
    groupChannelsHidden.name = "assistant_group_channels";
    groupChannelsHidden.value = settings.assistant_group_channels || "";
    form.append(groupChannelsHidden);

    const typingLabel = this._el("label", "Show Discord typing indicator");
    const typing = this._el("input"); typing.type = "checkbox"; typing.name = "typing_enabled"; typing.checked = settings.typing_enabled !== false;
    typing.dataset.keep = "cfg-typing_enabled"; typingLabel.prepend(typing);
    form.append(typingLabel);

    const apiMode = modeSelect.value === "api";
    if (apiMode) {
      form.append(this._el("h3", "System prompts and functions"));
      form.append(this._el("p", "API Mode deliberately does not override your Home Assistant agent's system prompt or function/tool configuration. Edit those in the selected conversation agent's settings. The saved GHOST prompt overrides below are retained but inactive until you switch back to Local Mode.", "help"));
      for (const key of ["conversation_system_prompt", "operations_system_prompt", "advanced_system_prompt"]) {
        const hidden = this._el("input"); hidden.type = "hidden"; hidden.name = key; hidden.value = settings[key] || ""; hidden.dataset.keep = "cfg-" + key; form.append(hidden);
      }
    } else {
    form.append(this._el("h3", "System prompts"));
    form.append(this._el("p", "These are additional instructions layered onto GHOST's built-in identity, privacy and action-verification rules.", "help"));
    const prompts = [
      ["conversation_system_prompt","Conversation agent",6000],
      ["operations_system_prompt","Operations agent",6000],
      ["advanced_system_prompt","Advanced reasoning instructions",6000]
    ];
    for (const p of prompts) {
      const row = this._el("div", null, "prompthead");
      row.append(this._el("label", p[1] + " instructions"), this._el("span", settings[p[0]] ? "CUSTOM" : "DEFAULT", "defaultbadge"));
      const area = this._el("textarea"); area.className = "prompt"; area.rows = 6; area.maxLength = p[2];
      area.name = p[0]; area.value = settings[p[0]] || defaults[p[0].replace("_system_prompt", "")] || ""; area.dataset.keep = "cfg-" + p[0];
      const reset = this._button("Reset to Default", async () => {
        if (!confirm("Discard your custom " + p[1].toLowerCase() + " instructions and restore GHOST's built-in default?")) return;
        await this._service("reset_prompt", { prompt_key: p[0] }, true);
      }, true);
      reset.disabled = this._busy || !settings[p[0]];
      row.append(reset);
      form.append(row, area);
      form.append(this._el("p", settings[p[0]] ? "Custom instructions are active. Reset restores the built-in northern British default." : "Built-in default is active. Edit this text and save to create your own override.", "help"));
    }
    }
    form.append(this._button("Save assistant settings", async () => {
      const data = {};
      for (const field of form.querySelectorAll("[name]")) {
        data[field.name] = field.type === "checkbox" ? field.checked : field.type === "number" ? Number(field.value) : field.value;
      }
      await this._service("update_settings", data, true);
    }));
    panel.append(form);
    shell.append(panel);

    const capabilitiesPanel = this._el("section", null, "panel");
    const capHead = this._el("div", null, "panelhead");
    const capTitle = this._el("div");
    capTitle.append(this._el("h2", "Home Assistant capabilities"));
    capTitle.append(this._el("p", "Expose entities and scripts so the selected Home Assistant conversation agent can use them.", "muted"));
    capHead.append(capTitle, this._button("Refresh", () => { this._capabilities = null; this._loadCapabilities(); }, true));
    capabilitiesPanel.append(capHead);
    capabilitiesPanel.append(this._el("p", "This controls Home Assistant's Assist exposure list. It does not grant access to arbitrary services. Scripts are the easiest way to give GHOST a named, reusable function such as setting a reminder. In Local Mode, the separately configured reminder script can be called directly by GHOST and does not rely on the model discovering a tool.", "help"));
    capabilitiesPanel.append(this._el("p", "One more required step for Ollama: open Settings → Devices & services → Ollama → Configure and enable the Device control AI tool. This exposure list controls which entities that tool can access. The selected model must support tool calling; very small models can struggle even when everything is configured correctly.", "help"));
    if (this._capabilitiesLoading) {
      capabilitiesPanel.append(this._el("p", "Loading your Home Assistant entities…", "muted"));
    } else if (!this._capabilities || !this._capabilities.available) {
      capabilitiesPanel.append(this._el("p", (this._capabilities && this._capabilities.error) || "Capability list unavailable. Refresh to try again.", "error"));
    } else {
      const entities = this._capabilities.entities || [];
      const scripts = entities.filter(x => x.domain === "script");
      capabilitiesPanel.append(this._el("p", entities.filter(x => x.exposed).length + " entities exposed · " + scripts.length + " scripts found · " + scripts.filter(x => x.exposed).length + " scripts exposed", "help"));
      const search = this._el("input", null, "search");
      search.placeholder = "Search entities and scripts by name or ID…";
      search.value = this._capabilitiesFilter; search.dataset.keep = "capability-search";
      search.addEventListener("input", () => { this._capabilitiesFilter = search.value; this._render(); });
      capabilitiesPanel.append(search);
      const filter = this._el("select", null, "search");
      for (const [value, label] of [["all","All capabilities"],["script","Scripts / functions"],["light","Lights"],["switch","Switches"],["other","Other entities"]]) {
        const option = this._el("option", label); option.value = value; filter.append(option);
      }
      filter.value = this._capabilityDomain; filter.dataset.keep = "capability-domain";
      filter.addEventListener("change", () => { this._capabilityDomain = filter.value; this._render(); });
      capabilitiesPanel.append(filter);
      const query = this._capabilitiesFilter.toLowerCase();
      const filtered = entities.filter(entity => {
        const matchesQuery = !query || (entity.name + " " + entity.entity_id).toLowerCase().includes(query);
        const matchesDomain = this._capabilityDomain === "all" || entity.domain === this._capabilityDomain || (this._capabilityDomain === "other" && !["script","light","switch"].includes(entity.domain));
        return matchesQuery && matchesDomain;
      }).slice(0, 250);
      if (!filtered.length) capabilitiesPanel.append(this._el("p", "No matching entities. Create a Home Assistant script first if you want to add a new function.", "muted"));
      for (const entity of filtered) {
        const row = this._el("div", null, "caprow");
        const details = this._el("div");
        details.append(this._el("strong", entity.name));
        details.append(this._el("p", entity.entity_id + " · " + entity.state, "muted"));
        if (entity.domain === "script") details.append(this._el("span", "SCRIPT / FUNCTION", "defaultbadge"));
        const control = this._el("label", entity.exposed ? "Available to Assist" : "Not exposed");
        const toggle = this._el("input"); toggle.type = "checkbox"; toggle.checked = !!entity.exposed; toggle.disabled = this._busy;
        toggle.addEventListener("change", () => this._setCapability(entity, toggle.checked));
        control.prepend(toggle);
        row.append(details, control);
        capabilitiesPanel.append(row);
      }
      if (entities.length > filtered.length) capabilitiesPanel.append(this._el("p", "Showing " + filtered.length + " matching entities. Narrow the search to find more.", "muted"));
    }
    capabilitiesPanel.append(this._el("p", "To add a function for the model: create a Script in Settings → Automations & Scenes → Scripts. Give it a clear name and a useful Description, and describe each input field so Assist knows what arguments it accepts. Then find it here under Scripts / functions and switch on Available to Assist. In Local Mode, also make sure the selected Operations agent has its Home Assistant control tool enabled. In API Mode, enable the equivalent Home Assistant control tool in the selected native conversation agent. You can expose lights, switches and scripts separately; only expose what GHOST should be allowed to use.", "help"));
    shell.append(capabilitiesPanel);

    const contactsPanel = this._el("section", null, "panel");
    contactsPanel.append(this._el("h2", "GHOST friend access"));
    contactsPanel.append(this._el("p", "By default, GHOST uses the people already tracked by Discord Game. This list is now independently editable and does not change their tracking sensors.", "muted"));
    const contacts = d.contacts || [];
    for (const contact of contacts) {
      const row = this._el("div", null, "contactrow");
      const label = this._el("div");
      label.append(this._el("strong", contact.name || contact.user_id));
      label.append(this._el("p", contact.user_id, "muted"));
      const name = this._el("input"); name.value = contact.name === contact.user_id ? "" : contact.name;
      name.placeholder = "Friendly name"; name.dataset.keep = "contact-name-" + contact.user_id;
      row.append(label, name);
      row.append(this._button("Remove", async () => {
        if (!confirm("Remove " + (contact.name || contact.user_id) + " from GHOST's approved friend list? This does not remove their Discord Game sensors.")) return;
        const updated = contacts.filter((x) => x.user_id !== contact.user_id).map((x) => ({ user_id: x.user_id, name: x.name === x.user_id ? "" : x.name }));
        await this._service("update_contacts", { contacts: updated }, true);
      }, true));
      contactsPanel.append(row);
    }
    if (contacts.length) {
      contactsPanel.append(this._button("Save friendly names", async () => {
        const updated = contacts.map((contact) => {
          const field = this.shadowRoot.querySelector('[data-keep="contact-name-' + contact.user_id + '"]');
          return { user_id: contact.user_id, name: field ? field.value.trim() : contact.name };
        });
        await this._service("update_contacts", { contacts: updated }, true);
      }, true));
    }
    if (!contacts.length) contactsPanel.append(this._el("p", "No approved friends. Add a Discord user ID below.", "muted"));
    const add = this._el("div", null, "fieldgrid");
    const idWrap = this._el("div"); idWrap.append(this._el("label", "Discord user ID"));
    const idInput = this._el("input"); idInput.placeholder = "e.g. 123456789012345678"; idInput.inputMode = "numeric"; idInput.dataset.keep = "new-contact-id"; idWrap.append(idInput);
    const nameWrap = this._el("div"); nameWrap.append(this._el("label", "Friendly name"));
    const nameInput = this._el("input"); nameInput.placeholder = "e.g. Max"; nameInput.dataset.keep = "new-contact-name"; nameWrap.append(nameInput);
    add.append(idWrap, nameWrap);
    contactsPanel.append(add);
    contactsPanel.append(this._button("Add friend", async () => {
      const id = idInput.value.trim();
      const name = nameInput.value.trim();
      if (!/^\d{15,20}$/.test(id)) {
        this._notice = "Enter a valid numeric Discord user ID.";
        this._render(); return;
      }
      if (contacts.some((x) => x.user_id === id)) {
        this._notice = "That Discord user is already approved.";
        this._render(); return;
      }
      const updated = contacts.map((x) => ({ user_id: x.user_id, name: x.name === x.user_id ? "" : x.name }));
      updated.push({ user_id: id, name: name });
      await this._service("update_contacts", { contacts: updated }, true);
    }));
    contactsPanel.append(this._el("p", "Removing someone blocks future GHOST DM replies. It does not delete their old conversation history or tracking entities.", "help"));
    shell.append(contactsPanel);

    const groupsPanel = this._el("section", null, "panel");
    groupsPanel.append(this._el("h2", "Server group chats"));
    groupsPanel.append(this._el("p", "Only these channel IDs are monitored for GHOST replies. Separate IDs with commas. GHOST's relevance gate decides whether to speak; approved friends' own messages can later inform their individual private memories.", "muted"));
    for (const group of d.groups || []) groupsPanel.append(this._el("p", (group.name || "Server channel") + " · " + group.channel_id, "help"));
    const channels = this._el("input");
    channels.value = settings.assistant_group_channels || "";
    channels.dataset.keep = "cfg-assistant_group_channels";
    groupsPanel.append(this._el("label", "Enabled Discord channel IDs"));
    groupsPanel.append(channels);
    groupsPanel.append(this._button("Save group chat channels", async () => {
      const ids = channels.value.split(",").map((x) => x.trim()).filter(Boolean);
      if (!ids.every((x) => /^\d{15,20}$/.test(x))) {
        this._notice = "Each channel ID must be a numeric Discord ID, separated by commas.";
        this._render(); return;
      }
      const data = {};
      data.assistant_mode = modeSelect.value;
      data.local_reminder_script = reminderScript.value || "script.set_timer_alarm_or_reminder";
      data.group_relevance_agent = relevanceAgent.value.trim();
      data.group_require_mention = mentionRequired.checked;
      data.fallback_after_failures = Number(settings.fallback_after_failures ?? 2);
      data.queue_debounce_seconds = Number(settings.queue_debounce_seconds ?? 2.5);
      data.max_context_messages = Number(settings.max_context_messages ?? 12);
      data.history_limit = Number(settings.history_limit ?? 8);
      data.memory_idle_seconds = Number(settings.memory_idle_seconds ?? 300);
      data.memory_batch_messages = Number(settings.memory_batch_messages ?? 20);
      data.group_continuity_seconds = Number(settings.group_continuity_seconds ?? 300);
      data.conversation_history_limit = Number(settings.conversation_history_limit ?? 500);
      data.context_budget_chars = Number(settings.context_budget_chars ?? 10000);
      data.typing_enabled = settings.typing_enabled !== false;
      data.assistant_group_channels = ids.join(",");
      data.conversation_system_prompt = settings.conversation_system_prompt || "";
      data.operations_system_prompt = settings.operations_system_prompt || "";
      data.advanced_system_prompt = settings.advanced_system_prompt || "";
      await this._service("update_settings", data, true);
    }, true));
    shell.append(groupsPanel);
  }

  _renderMemories(shell, d) {
    const panel = this._el("section", null, "panel");
    panel.append(this._el("h2", "Private friend memories"));
    panel.append(this._el("p", "GHOST stores only explicit remember statements, clear first-person preferences/favourites/work facts, and structured Home Assistant action outcomes. Assistant replies, jokes, guesses and unverified device claims are ignored. Group channels have no shared long-term memory; approved friends' own contributions can inform their individual private memories.", "muted"));
    const contacts = d.contacts || [];
    const pendingTotal = Object.values(d.friend_memory || {}).reduce((total, item) => total + (item.pending_messages || 0), 0);
    panel.append(this._el("p", "Pending messages awaiting consolidation: " + pendingTotal + (d.last_memory_consolidation ? " · Last consolidation: " + new Date(d.last_memory_consolidation).toLocaleString() : " · No consolidation has completed yet."), "help"));
    panel.append(this._el("p", "Memory maintenance is deterministic: consolidation extracts supported facts and removes duplicates. It does not invent summaries. Review or edit facts below to remove information that is no longer current.", "muted"));
    panel.append(this._button("Consolidate and deduplicate all contacts now", () => this._service("consolidate_friend_memory", {}), true));
    if (!contacts.length) panel.append(this._el("p", "No approved friends yet. Add people in Configuration.", "muted"));
    for (const contact of contacts) {
      const mem = (d.friend_memory || {})[contact.user_id] || {};
      const box = this._el("article", null, "memorybox");
      const head = this._el("div", null, "panelhead");
      const names = this._el("div");
      names.append(this._el("strong", contact.name || contact.user_id));
      names.append(this._el("p", (mem.messages ?? contact.memory_messages ?? 0) + " recent context messages · " + (mem.pending_messages ?? 0) + " awaiting consolidation" + (mem.last_consolidated ? " · last consolidated " + new Date(mem.last_consolidated).toLocaleString() : ""), "muted"));
      head.append(names);
      box.append(head);
      box.append(this._el("label", "Durable memory summary"));
      const summary = this._el("textarea"); summary.rows = 5; summary.value = mem.summary || contact.summary || "";
      summary.dataset.keep = "memory-summary-" + contact.user_id;
      box.append(summary);
      box.append(this._button("Save memory correction", () => this._service("set_friend_memory", { user_id: contact.user_id, summary: summary.value }), true));
      const recent = mem.recent_messages || [];
      const details = document.createElement("details");
      details.append(this._el("summary", "View recent stored messages (" + recent.length + ")"));
      for (const msg of recent.slice(-30)) {
        details.append(this._el("div", (msg.sender || msg.role || "Message") + ": " + (msg.content || ""), "memoryline"));
      }
      box.append(details);
      box.append(this._button("Remove saved facts", () => {
        if (confirm("Remove all durable facts for " + (contact.name || contact.user_id) + "? Recent chat and pending evidence will remain.")) this._service("purge_friend_memory", { user_id: contact.user_id, scope: "facts" });
      }, true));
      box.append(this._button("Clear pending memory evidence", () => {
        if (confirm("Discard unprocessed memory evidence for " + (contact.name || contact.user_id) + "? Saved facts and chat history will remain.")) this._service("purge_friend_memory", { user_id: contact.user_id, scope: "pending" });
      }, true));
      box.append(this._button("Clear stored chat history", () => {
        if (confirm("Delete stored raw chat history for " + (contact.name || contact.user_id) + "? Durable facts will remain.")) this._service("purge_friend_memory", { user_id: contact.user_id, scope: "history" });
      }, true));
      box.append(this._button("Purge everything for this friend", () => {
        if (confirm("Permanently delete saved facts, pending evidence, raw chat history and retained activity for " + (contact.name || contact.user_id) + "? This cannot be undone.")) this._service("purge_friend_memory", { user_id: contact.user_id, scope: "all" });
      }, true));
      panel.append(box);
    }
    shell.append(panel);
  }

  _renderActivity(shell, d) {
    const controls = this._el("section", null, "panel");
    controls.append(this._el("h2", "Queue controls"));
    controls.append(this._el("p", "Pause prevents new replies from starting; the active response is allowed to finish.", "muted"));
    const buttons = this._el("div", null, "actions");
    buttons.append(this._button(d.paused ? "Resume assistant" : "Pause assistant", () => this._service(d.paused ? "resume" : "pause", {})));
    buttons.append(this._button("Clear pending queue", () => {
      if (confirm("Discard all pending messages?")) this._service("clear_queue", {});
    }, true));
    controls.append(buttons);
    shell.append(controls);

    const relevance = this._el("section", null, "panel");
    relevance.append(this._el("h2", "Group-chat relevance filter"));
    relevance.append(this._el("p", "GHOST uses recent channel history when deciding whether to join in. Clear follow-ups to its own recent replies are treated as part of the same conversation for the configured continuity window. Home Assistant actions and live-state queries still require an explicit mention or reply.", "muted"));
    relevance.append(this._el("p", "Messages deliberately ignored: " + (d.suppressed_group_messages || 0), "help"));
    if (d.last_group_decision) {
      relevance.append(this._el("p", "Last decision: " + d.last_group_decision.decision + " · " + (d.last_group_decision.reason || "") + " · " + (d.last_group_decision.timestamp || ""), "muted"));
    } else {
      relevance.append(this._el("p", "No group relevance decisions recorded yet.", "muted"));
    }
    shell.append(relevance);

    const queue = this._el("section", null, "panel");
    queue.append(this._el("h2", "Waiting messages"));
    for (const item of d.pending_messages || []) {
      const card = this._el("article", null, "activity");
      card.append(this._el("strong", item.sender || "Discord user"));
      card.append(this._el("p", item.message || "", ""));
      card.append(this._el("p", item.timestamp || "", "muted"));
      const edit = this._el("textarea"); edit.value = item.message || ""; edit.dataset.keep = "queue-" + item.id; card.append(edit);
      const actions = this._el("div", null, "actions");
      actions.append(this._button("Save edit", () => this._service("edit_queued_message", { message_id: item.id, message: edit.value }), true));
      actions.append(this._button("Cancel", () => this._service("cancel_queued_message", { message_id: item.id }), true));
      card.append(actions);
      queue.append(card);
    }
    if (!(d.pending_messages || []).length) queue.append(this._el("p", "The queue is empty.", "muted"));
    shell.append(queue);

    const history = this._el("section", null, "panel");
    history.append(this._el("h2", "Recent assistant activity"));
    for (const item of [...(d.transcript || [])].reverse()) {
      const card = this._el("article", null, "activity");
      card.append(this._el("strong", item.sender || item.conversation || "Conversation"));
      card.append(this._el("p", [item.timestamp, item.model, item.role].filter(Boolean).join(" · "), "muted"));
      for (const message of item.user_messages || []) card.append(this._el("p", "Incoming: " + message));
      if (item.assistant) card.append(this._el("p", "GHOST: " + item.assistant));
      if (item.suppressed) card.append(this._el("p", "GHOST stayed quiet: " + (item.suppression_reason || "Not relevant enough to interrupt."), "muted"));
      if (item.error) card.append(this._el("p", item.error, "error"));
      if (item.request_kind) card.append(this._el("p", "Request type: " + item.request_kind, "muted"));
      if (item.models_attempted && item.models_attempted.length) card.append(this._el("p", "Agents attempted: " + item.models_attempted.join(" → "), "muted"));
      if (item.fallback_used) card.append(this._el("p", "Fallback agent was used.", "muted"));
      if (item.action_result) {
        const details = document.createElement("details");
        details.append(this._el("summary", "View Home Assistant action result"));
        details.append(this._el("pre", JSON.stringify(item.action_result, null, 2)));
        card.append(details);
      }
      history.append(card);
    }
    if (!(d.transcript || []).length) history.append(this._el("p", "No activity recorded yet.", "muted"));
    shell.append(history);
  }
}

customElements.define("discord-game-ghost-panel", DiscordGameGhostPanel);
