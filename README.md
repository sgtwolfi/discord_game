# Discord Game + GHOST Assistant (v9.2.0)

This release adds API and Local assistant runtime modes, separate API fallback selection, natural-language GHOST addressing and configurable per-sender spam protection while retaining the existing Discord presence, game, Spotify, voice and reaction sensors and the original `discord_game_message_received` event payload.

## 9.2.0 action verification and 9.1.x reliability updates

- For actions, GHOST first requires Home Assistant's structured target results. If an agent returns `action_done` without target details, GHOST performs a bounded read-after-write check against matching live Home Assistant entities. It only confirms when every unambiguously matched target currently satisfies the requested state; it does not infer success from model speech or unrelated entity changes. Ambiguous targets and unsupported properties remain unconfirmed, and this fallback never replays the action. When it verifies an action this way, GHOST builds its confirmation from the actual matched entity states rather than repeating the model's unverified claim.
- Owner activity questions are resolved before Discord friend matching. The default owner name `Harvey` remains a compatibility alias even if the configurable display name has been changed, and matching is tolerant of punctuation, apostrophes and common spoken variants.
- Local Mode passes deterministic live-state answers through its conversation model for natural, varied phrasing. API Mode uses only the separately configured tool-free group relevance agent for this cosmetic step; it never calls the potentially tool-enabled API agent to reword a status. The verified factual answer must be reproduced verbatim; if the model omits or changes it, GHOST falls back to the deterministic answer. If no safe rephrasing agent is configured, the deterministic answer is retained.

## Setup

The assistant is disabled by default to prevent duplicate replies from existing automations. Open Settings → Devices & services → Discord Game → Configure.

Choose the agents from Home Assistant's conversation-agent dropdowns:
- Conversation agent: local Ollama agent for ordinary chat.
- Operations agent: local agent configured with only the Home Assistant tools/scripts it is allowed to use.
- Memory: deterministic extraction of explicit facts and verified action records; it does not rely on a generative memory model.
- Fallback agent: optional API-backed conversation agent used after repeated local service failures.

Use IDs such as `conversation.my_ollama_agent`. This integration does not store API keys.


## Reliability and live status (9.0.0)

- GHOST reads the **Home Assistant owner's live status/activity** directly from `input_text.ghost_status` by default. It is not GHOST's own internal status. Configure the owner's display name (default `Harvey`) and helper entity in GHOST → Configuration. The integration reads the state itself and injects the current value into both Local and API model context; it does **not** need to be exposed to Assist or enabled as an AI tool.
- Questions such as “what's Harvey doing?”, “what am I doing?” and “what's my status?” are answered deterministically from that helper, before any model or Discord friend lookup. The configured owner name is reserved for this helper, so it cannot accidentally match a Discord friend profile. If the helper is missing or unavailable, GHOST says so rather than inventing an activity.
- Other named contacts (for example, “what's Max doing?”) continue to use their Discord Game presence/activity sensors.
- The typing indicator starts before group relevance checks and model calls, and stays active while GHOST works. This is enabled by default for DMs and configured group channels.
- Friend profile pictures are taken from Discord Game's tracked-user sensor attributes where available, with the same Discord client profile as a fallback. The chat panel uses these avatars and opens each conversation at the newest message automatically.
- The admin chat dashboard displays the current helper value and marks the assistant as needing attention when its latest request failed.

## Runtime modes

Choose **Local Mode** or **API Mode** in the GHOST sidebar under Settings → Assistant behaviour. The mode is saved with the integration options and takes effect after the integration reloads.

### API Mode

- Select one Home Assistant Conversation Agent in Settings → Devices & services → Discord Game → Configure.
- Configure its provider, API credentials, model, system prompt and available tools/functions in that agent's own Home Assistant integration settings.
- GHOST does not overwrite that agent's system prompt or tool configuration. It sends bounded conversation context and the approved contact's private saved facts with each request.
- GHOST still owns Discord queueing, contact isolation, memory extraction/consolidation, audit history and action-result verification. Switching models or changing the agent does not disable or erase memory.
- Group relevance can be inferred by a separately selected local, tool-free conversation agent; untrusted group text is never sent to the tool-enabled API agent just to decide whether GHOST should speak. The optional mention-only setting bypasses inference and requires an explicit mention or reply.
- A bounded continuity window recognises clear same-speaker follow-ups to GHOST's recent group reply, including when mention-only mode is enabled. Unrelated messages remain suppressed, and Home Assistant actions/live-state queries still require a direct mention or reply. Group history is restored from persisted conversation logs after Home Assistant restarts. Continuity only applies to ordinary chat; group Home Assistant actions and live-state queries still require a direct mention or reply.
- Select **API fallback agent** separately from the primary Conversation Agent in Discord Game → Configure. It is used for recoverable primary-model failures on conversation and read-only work. Side-effecting actions are never replayed through fallback after an ambiguous result.
- The Local Operations and Local Fallback selectors are not used by API Mode. The selected API Conversation Agent handles ordinary chat, live-state queries and actions; the API fallback is a separate recovery model.

### Local Mode

- Select separate Conversation and Operations agents, with an optional Fallback agent, in Discord Game → Configure.
- GHOST assigns narrow role-specific prompts and routes Home Assistant work to the Operations Agent. The fallback is for model-call recovery, not a second attempt at an uncertain side effect.
- Simple live lookups are answered directly from Home Assistant state without asking a model to use a tool in either mode: the configured GHOST status helper, Discord presence/activity sensors, lights, current local time and configured weather entities.
- Clear private-DM reminder requests are parsed deterministically and sent directly to the configured reminder script. This avoids relying on a tiny model to discover and call a function. The default script entity is `script.set_timer_alarm_or_reminder`; change it in GHOST → Settings if yours is named differently. The script must return `success: true` before GHOST confirms the reminder. Ambiguous times (for example, “at 7”) trigger a clarification instead of a guess.
- Other device actions still depend on the selected Operations Agent and its Home Assistant tool support. A 0.5B model is not guaranteed to make reliable tool calls merely because prompts are shorter; use the direct handlers where available and test any other action with the Activity panel open.

## Spam protection

Configure the per-sender message threshold and rolling time window in Discord Game → Configure. When a sender exceeds the threshold, choose one policy:
- **Defer to local model**: route that sender to the separately selected `spam_local_agent` for the configured cooldown. Configure this agent as a lightweight local Home Assistant conversation agent; do not give it privileged control tools unless you explicitly intend that.
- **Discord timeout**: request a Discord member timeout for the configured duration. The bot needs the Discord moderation permission and this applies to server members, not direct messages. If Discord rejects the timeout, GHOST still suppresses the sender during the cooldown and logs the failure.
- **Ignore during cooldown**: discard that sender's messages until the cooldown expires.

The default threshold is 8 messages in 30 seconds. The default policy is local deferral for 10 minutes. Queue capacity and duplicate-message protection remain in place independently.


### API fallback and reminder confirmations (8.2.4)

- GHOST makes one attempt with the primary model, then uses the configured fallback instead of repeating the same failing model and spending tokens on an unchanged request.
- A Home Assistant action may move to the API fallback only when the primary agent explicitly reports a function/YAML configuration failure before executing tools. Timeouts and ambiguous failures are never replayed.
- The fallback must be a separate Home Assistant Conversation Agent with the required tools/functions configured in its own settings. For action requests, GHOST requires a structured Home Assistant success result; a spoken "done" is not accepted as proof.
- In both API and Local modes, a clear reminder request or an explicit yes/no response to GHOST's immediately preceding reminder-confirmation question is handled through the configured reminder script. GHOST only confirms after the script returns `success: true`. A decline never creates the reminder.

## Memory ownership and cleanup

Memory is owned by GHOST in both modes, not by the selected model. The Memory panel can run deterministic consolidation/deduplication immediately and independently purge durable facts, unprocessed evidence, raw contact chat history, or all retained data for a contact. Consolidation removes exact duplicates (case/punctuation insensitive) and replaces older work/favourite facts when a newer explicit fact for the same field is recorded. It does not invent facts or decide that arbitrary personal details are stale; review and edit the summary or purge the relevant layer when information should no longer be retained. Full contact purge also removes matching retained DM activity records, queued messages and temporary context, and refuses to race an active private response. Other contacts and group records remain isolated. GHOST adds only the current approved DM contact's saved facts to that contact's request context. Durable memory is extracted deterministically from explicit remember statements, clear first-person preferences/favourites/work facts and structured action outcomes. Assistant replies, jokes, guessed activity and unverified device claims are not memory evidence.

On startup, legacy non-administrator summaries are now allow-listed to evidence-labelled facts only. Old conversational filler and unlabelled generated claims are discarded. Administrator-authored memory corrections are preserved. Recent chat and the bounded audit transcript remain available separately for conversation continuity and administrator diagnostics; they are not promoted to durable facts.


## Behaviour and privacy

- DMs are only processed for users already selected in the existing Discord Game user configuration.
- Server AI is separately opt-in by comma-separated channel IDs.
- Home Assistant actions and live-state queries in group chats require GHOST to be directly mentioned or explicitly replied to; this prevents unrelated group conversation from exposing private house state or triggering actions.
- Approved DM history is persisted per user. Server context is isolated by channel and held in RAM only; strangers are not given persistent memories.
- The oldest pending conversation is processed first. After the configurable debounce period, all currently queued messages for that same conversation are coalesced in chronological order, even if other conversations are interleaved. Different conversations are never combined. Discord message IDs are deduplicated across the pending queue and recent transcript. The pending queue is capped at 200 messages; when full, new messages are rejected with an error event rather than silently deleting older messages.
- Discord typing indicators are enabled by default.
- Context is bounded by a configurable character budget. Token figures are approximate (about four characters per token), not exact provider usage.
- Complex requests use the advanced reasoning instructions with the primary conversation model. The configured fallback is a recovery model used after primary conversation failures and malformed group-relevance decisions. Read-only state queries may recover through fallback. Side-effecting Home Assistant actions are never retried after exceptions, timeouts, missing results or ambiguous outcomes. One controlled retry is permitted only when Home Assistant returns a structured `action_done` result with explicit failed entity IDs and failure reasons; successful targets are excluded, only failed targets are retried, and the retry must itself return a structured result before success is reported.

## Home Assistant

New entity: `sensor.discord_game_assistant`. Attributes include queue state, model agent IDs, recent transcript, context snapshots, estimated token counts, errors and friend-memory counts.

A GHOST entry is added to the Home Assistant sidebar. The admin panel shows the active request and prompt snapshot, pending messages, recent transcript, structured action results, estimated model usage and approved-contact memory. It provides pause/resume, queue editing/cancellation, transcript replay, clear-queue, manual send, temporary context injection and per-contact memory correction/clearing controls. Private diagnostics are delivered through an administrator-only WebSocket command; ordinary sensor attributes contain non-private status/model metadata only, not message contents, transcripts, prompt snapshots or contact memory.

Services:
- `discord_game.send_message`: manually send as the bot; supply `message` and either `user_id` or `channel_id`.
- `discord_game.clear_friend_memory`: clear one friend's persistent DM memory using their Discord user ID.
- `discord_game.set_friend_memory`: replace a contact's durable memory with an administrator correction.
- `discord_game.set_context_note`: inject temporary context for an approved DM or selected server channel; it is not persisted across restarts.
- `discord_game.pause`, `resume`, and `clear_queue`: control pending processing.
- `discord_game.edit_queued_message` and `cancel_queued_message`: edit or cancel an individual pending message by its Discord message ID.
- `discord_game.replay_transcript`: reprocess the original user messages from a retained transcript entry.

Events:
- Existing `discord_game_message_received` remains unchanged.
- `discord_game_server_message_received` is emitted for configured server channels.
- `discord_game_assistant_queued`, `discord_game_assistant_response_sent`, `discord_game_assistant_error`, `discord_game_assistant_updated` and `discord_game_assistant_manual_message` expose assistant activity.


## Memory behaviour

Memory is deliberately conservative and does not ask a small language model to invent a summary. It stores explicit “remember this” statements, clear first-person preferences/favourites/work facts, and structured Home Assistant action records. Ordinary banter, assistant replies, guesses, and unverified device claims are not promoted to durable memory. The unused generative memory-agent selector and memory prompt have been removed from the configuration interface. Existing saved values are ignored; memory no longer consumes a model call.


## Important limitations

Home Assistant conversation agents own their internal tool execution. GHOST distinguishes read-only state queries from side-effecting actions. For actions, it requires a structured `action_done` response with at least one successful target and no failed targets before reporting success. Partial results are reported as partial; plain speech such as “Done” is never proof. This verifies the result reported by Home Assistant's conversation service, not a separate physical-state check. Restrict the operations agent to approved HA tools and expose only the entities it should control.

Token counts are estimates. Test with your existing DM reply automations disabled before enabling this assistant, otherwise both systems may respond.
