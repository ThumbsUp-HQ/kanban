# API Specialist Review: KAN-542

Verdict: APPROVED

Verified against commit 9f29c6c1 (clean-room rerun: 18 tests pass, ruff clean, mypy clean):
- base.py: ToolDefinition, ChatToolCall, ChatMessage, ChatTurnRequest, ChatTurnResponse, ToolCallingProvider added; LLMProvider unchanged.
- OllamaProvider.chat_turn: OpenAI-style tools; format omitted on tool turns, set from response_model otherwise; think with HTTP 400 fallback; done_reason=length retry doubles num_predict once; only structured message.tool_calls parsed (text/thinking ignored); max 8 calls; declared-name allowlist; args dict or JSON-object validation.
- 8 MiB STREAM_TOO_LARGE cap on chat_turn and generate_structured; resolve_and_pin, follow_redirects=False, trust_env=False, _verify_model_allowed; error bodies scrubbed and truncated.
- Tests in tests/agent/test_ollama_chat_tools.py cover each behavior.
