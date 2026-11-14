# Discord Game + GHOST Assistant (v7 development)

This branch adds an optional token-conscious assistant runtime while retaining the existing Discord presence, game, Spotify, voice and reaction sensors and the original `discord_game_message_received` event payload.

## Setup

The assistant is disabled by default to prevent duplicate replies from existing automations. Open Settings → Devices & services → Discord Game → Configure.

Choose the agents from Home Assistant's conversation-agent dropdowns:
- Conversation agent: local Ollama agent for ordinary chat.
- Operations agent: local agent configured with only the Home Assistant tools/scripts it is allowed to use.
- Memory agent: optional local agent for periodic private-memory compression.
- Fallback agent: optional API-backed conversation agent used after repeated local service failures.

Use IDs such as `conversation.my_ollama_agent`. This integration does not store API keys.

## Behaviour and privacy

- DMs are only processed for users already selected in the existing Discord Game user configuration.
- Server AI is separately opt-in by comma-separated channel IDs.
- Approved DM history is persisted per user. Server context is isolated by channel and held in RAM only; strangers are not given persistent memories.
- Messages are processed in arrival order. Adjacent messages from the same conversation are grouped during the configurable debounce period. The pending queue is capped at 200 messages; when full, new messages are rejected with an error event rather than silently deleting older messages.
- Discord typing indicators are enabled by default.
- Context is bounded by a configurable character budget. Token figures are approximate (about four characters per token), not exact provider usage.
- The configured API fallback is used after ordinary conversation-agent failures and for requests recognised as complex (research, comparisons, debugging, system design, etc.). For operations, it can retry an incomplete or unconfirmed response only when no target was reported as failed. It does not automatically retry an operations call that failed without returning a result, or a partially failed action, because that could repeat a side effect. The fallback must still return Home Assistant's structured successful-action result before GHOST reports success.

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

## Important limitations

Home Assistant conversation agents own their internal tool execution. For requests routed to the operations agent, the integration now requires a structured `action_done` response with at least one successful target and no failed targets before it sends the agent's success message. Plain speech such as “Done” is not accepted as proof. This verifies the result reported by Home Assistant's conversation service; it is not a separate physical-state check. Restrict the operations agent to approved HA tools and instruct it to report tool failures honestly.

Token counts are estimates. Test with your existing DM reply automations disabled before enabling this assistant, otherwise both systems may respond.
