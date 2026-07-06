"""Claude (Anthropic) provider adapter.

Converts between the canonical format (see ai/client.py) and the Anthropic
Messages API. All anthropic SDK usage lives here.
"""

import anthropic


def get_client(api_key: str) -> anthropic.Anthropic:
	return anthropic.Anthropic(api_key=api_key)


def to_wire_messages(messages: list[dict]) -> list[dict]:
	"""Canonical messages -> Anthropic messages array."""
	wire = []
	for msg in messages:
		role = msg["role"]
		if role == "tool_result":
			wire.append({
				"role": "user",
				"content": [{
					"type": "tool_result",
					"tool_use_id": msg["tool_use_id"],
					"content": msg.get("content") or "",
					"is_error": bool(msg.get("is_error")),
				}],
			})
		elif role == "assistant" and msg.get("tool_calls"):
			content = []
			if msg.get("content"):
				content.append({"type": "text", "text": msg["content"]})
			for call in msg["tool_calls"]:
				content.append({
					"type": "tool_use",
					"id": call["id"],
					"name": call["name"],
					"input": call.get("input") or {},
				})
			wire.append({"role": "assistant", "content": content})
		else:
			wire.append({"role": role, "content": msg.get("content") or ""})
	return wire


def create_message(api_key, model, messages, system=None, tools=None, max_tokens=4096) -> dict:
	"""Returns the normalized response dict defined in ai/client.py."""
	kwargs = {
		"model": model,
		"max_tokens": max_tokens,
		"messages": to_wire_messages(messages),
	}
	if system:
		kwargs["system"] = system
	if tools:
		# canonical tool format IS the Anthropic format — pass through
		kwargs["tools"] = tools

	response = get_client(api_key).messages.create(**kwargs)

	text_parts = []
	tool_calls = []
	for block in response.content:
		if block.type == "text":
			text_parts.append(block.text)
		elif block.type == "tool_use":
			tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

	stop_reason = {
		"tool_use": "tool_use",
		"max_tokens": "max_tokens",
	}.get(response.stop_reason, "end_turn")

	return {
		"text": "\n".join(text_parts),
		"tool_calls": tool_calls,
		"stop_reason": stop_reason,
		"model": response.model,
		"usage": {
			"input_tokens": response.usage.input_tokens,
			"output_tokens": response.usage.output_tokens,
		},
		"raw": response,
	}
