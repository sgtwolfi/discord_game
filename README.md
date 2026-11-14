# Discord Game + GHOST Assistant (v8.2.2)

This release adds API and Local assistant runtime modes, separate API fallback selection, natural-language GHOST addressing and configurable per-sender spam protection while retaining the existing Discord presence, game, Spotify, voice and reaction sensors and the original `discord_game_message_received` event payload.

## Setup

The assistant is disabled by default to prevent duplicate replies from existing automations. Open Settings → Devices & services → Discord Game → Configure.

Choose the agents from Home Assistant's conversation-agent dropdowns:
- Conversation agent: local Ollama agent for ordinary chat.
- Operations agent: local agent configured with only the Home Assistant tools/scripts it is allowed to use.
- Memory: deterministic extraction of explicit facts and verified action records; it does not rely on a generative memory model.
- Fallback agent: optional API-backed conversation agent used after repeated local service failures.

Use IDs such as `conversation.my_ollama_agent`. This integration does not store API keys.


## Runtime modes

Choose **Local Mode** or **API Mode** in the GHOST sidebar under Settings → Assistant behaviour. The mode is saved with the integration options and takes effect after the integration reloads.

### API Mode

- Select one Home Assistant Conversation Agent in Settings → Devices & services → Discord Game → Configure.
- Configure its provider, API credentials, model, system prompt and available tools/functions in that agent's own Home Assistant integration settings.
- GHOST does not overwrite that agent's system prompt or tool configuration. It sends bounded conversation context and the approved contact's private saved facts with each request.
- GHOST still owns Discord queueing, contact isolation, memory extraction/consolidation, audit history and action-result verification. Switching models or changing the agent does not disable or erase memory.
- Group relevance can be inferred by a separately selected local, tool-free conversation agent; untrusted group text is never sent to the tool-enabled API agent just to decide whether GHOST should speak. The optional mention-only setting bypasses inference and requires an explicit mention or reply.
- A bounded continuity window recognises clear same-speaker follow-ups to GHOST's recent group reply. Group history is restored from persisted conversation logs after Home Assistant restarts. Continuity only applies to ordinary chat; group Home Assistant actions and live-state queries still require a direct mention or reply.
- Select **API fallback agent** separately from the primary Conversation Agent in Discord Game → Configure. It is used for recoverable primary-model failures on conversation and read-only work. Side-effecting actions are never replayed through fallback after an ambiguous result.
- The Local Operations and Local Fallback selectors are not used by API Mode. The selected API Conversation Agent handles ordinary chat, live-state queries and actions; the API fallback is a separate recovery model.

### Local Mode

- Select separate Conversation and Operations agents, with an optional Fallback agent, in Discord Game → Configure.
- GHOST assigns narrow role-specific prompts and routes Home Assistant work to the Operations Agent. The fallback is for model-call recovery, not a second attempt at an uncertain side effect.
- Simple live lookups are answered directly from Home Assistant state without asking a model to use a tool: Discord presence/activity sensors, lights, current local time and configured weather entities.
- Clear private-DM reminder requests are parsed deterministically and sent directly to the configured reminder script. This avoids relying on a tiny model to discover and call a function. The default script entity is `script.set_timer_alarm_or_reminder`; change it in GHOST → Settings if yours is named differently. The script must return `success: true` before GHOST confirms the reminder. Ambiguous times (for example, “at 7”) trigger a clarification instead of a guess.
- Other device actions still depend on the selected Operations Agent and its Home Assistant tool support. A 0.5B model is not guaranteed to make reliable tool calls merely because prompts are shorter; use the direct handlers where available and test any other action with the Activity panel open.

## Spam protection

Configure the per-sender message threshold and rolling time window in Discord Game → Configure. When a sender exceeds the threshold, choose one policy:
- **Defer to local model**: route that sender to the separately selected `spam_local_agent` for the configured cooldown. Configure this agent as a lightweight local Home Assistant conversation agent; do not give it privileged control tools unless you explicitly intend that.
- **Discord timeout**: request a Discord member timeout for the configured duration. The bot needs the Discord moderation permission and this applies to server members, not direct messages. If Discord rejects the timeout, GHOST still suppresses the sender during the cooldown and logs the failure.
- **Ignore during cooldown**: discard that sender's messages until the cooldown expires.

The default threshold is 8 messages in 30 seconds. The default policy is local deferral for 10 minutes. Queue capacity and duplicate-message protection remain in place independently.

## Memory ownership and cleanup

Memory is owned by GHOST in both modes, not by the selected model. The Memory panel can run deterministic consolidation/deduplication immediately and independently purge durable facts, unprocessed evidence, raw contact chat history, or all retained data for a contact. Consolidation removes exact duplicates (case/punctuation insensitive) and replaces older work/favourite facts when a newer explicit fact for the same field is recorded. It does not invent facts or decide that arbitrary personal details are stale; review and edit the summary or purge the relevant layer when information should no longer be retained. Full contact purge also removes matching retained DM activity records. Other contacts and group records remain isolated. GHOST adds only the current approved DM contact's saved facts to that contact's request context. Durable memory is extracted deterministically from explicit remember statements, clear first-person preferences/favourites/work facts and structured action outcomes. Assistant replies, jokes, guessed activity and unverified device claims are not memory evidence.

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
