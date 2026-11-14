# Discord Game + GHOST Assistant (v8 development)

This branch adds an optional token-conscious assistant runtime while retaining the existing Discord presence, game, Spotify, voice and reaction sensors and the original `discord_game_message_received` event payload.

## Setup

The assistant is disabled by default to prevent duplicate replies from existing automations. Open Settings → Devices & services → Discord Game → Configure.

Choose the agents from Home Assistant's conversation-agent dropdowns:
- Conversation agent: local Ollama agent for ordinary chat.
- Operations agent: local agent configured with only the Home Assistant tools/scripts it is allowed to use.
- Memory: deterministic extraction of explicit facts and verified action records; it does not rely on a generative memory model.
- Fallback agent: optional API-backed conversation agent used after repeated local service failures.

Use IDs such as `conversation.my_ollama_agent`. This integration does not store API keys.

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
