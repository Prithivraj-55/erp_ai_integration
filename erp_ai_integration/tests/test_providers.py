"""Unit tests for the multi-provider AI layer (no network calls).

Run: bench --site assesment run-tests --module erp_ai_integration.tests.test_providers
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_ai_integration.ai import anthropic_client, client, openai_client

CANONICAL_MESSAGES = [
	{"role": "user", "content": "How many invoices today?"},
	{
		"role": "assistant",
		"content": "Let me check.",
		"tool_calls": [{"id": "call_1", "name": "run_query", "input": {"sql": "SELECT 1"}}],
	},
	{"role": "tool_result", "tool_use_id": "call_1", "content": "[[5]]", "is_error": False},
]

CANONICAL_TOOLS = [
	{
		"name": "run_query",
		"description": "Run a read-only SELECT query.",
		"input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
	}
]


class TestProviders(FrappeTestCase):
	def tearDown(self):
		self._set_provider("Claude")
		super().tearDown()

	def _set_provider(self, provider):
		frappe.db.set_single_value("Claude AI Settings", "provider", provider)
		frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")

	# ---- provider selection ----

	def test_default_provider_is_claude(self):
		self._set_provider("Claude")
		self.assertEqual(client.get_provider_name(), "Claude")
		self.assertIs(client.get_adapter(), anthropic_client)

	def test_chatgpt_provider_selected(self):
		self._set_provider("ChatGPT")
		self.assertEqual(client.get_provider_name(), "ChatGPT")
		self.assertIs(client.get_adapter(), openai_client)

	def test_get_model_follows_provider(self):
		self._set_provider("Claude")
		settings = frappe.get_cached_doc("Claude AI Settings")
		self.assertTrue(settings.get_model().startswith("claude"))

		self._set_provider("ChatGPT")
		settings = frappe.get_cached_doc("Claude AI Settings")
		self.assertTrue(settings.get_model().startswith("gpt"))

	def test_custom_model_overrides_both(self):
		frappe.db.set_single_value("Claude AI Settings", "custom_model", "my-special-model")
		frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")
		try:
			for provider in ("Claude", "ChatGPT"):
				self._set_provider(provider)
				settings = frappe.get_cached_doc("Claude AI Settings")
				self.assertEqual(settings.get_model(), "my-special-model")
		finally:
			frappe.db.set_single_value("Claude AI Settings", "custom_model", "")
			frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")

	# ---- Anthropic wire conversion ----

	def test_anthropic_messages(self):
		wire = anthropic_client.to_wire_messages(CANONICAL_MESSAGES)
		self.assertEqual(wire[0], {"role": "user", "content": "How many invoices today?"})
		# assistant turn: text block + tool_use block
		blocks = wire[1]["content"]
		self.assertEqual(blocks[0], {"type": "text", "text": "Let me check."})
		self.assertEqual(blocks[1]["type"], "tool_use")
		self.assertEqual(blocks[1]["id"], "call_1")
		self.assertEqual(blocks[1]["input"], {"sql": "SELECT 1"})
		# tool result becomes a user message with tool_result block
		self.assertEqual(wire[2]["role"], "user")
		self.assertEqual(wire[2]["content"][0]["type"], "tool_result")
		self.assertEqual(wire[2]["content"][0]["tool_use_id"], "call_1")

	# ---- OpenAI wire conversion ----

	def test_openai_messages(self):
		wire = openai_client.to_wire_messages(CANONICAL_MESSAGES, system="You are helpful.")
		self.assertEqual(wire[0], {"role": "system", "content": "You are helpful."})
		self.assertEqual(wire[1], {"role": "user", "content": "How many invoices today?"})
		# assistant turn with tool_calls
		self.assertEqual(wire[2]["role"], "assistant")
		call = wire[2]["tool_calls"][0]
		self.assertEqual(call["id"], "call_1")
		self.assertEqual(call["function"]["name"], "run_query")
		self.assertIn("SELECT 1", call["function"]["arguments"])
		# tool result becomes role=tool
		self.assertEqual(wire[3]["role"], "tool")
		self.assertEqual(wire[3]["tool_call_id"], "call_1")

	def test_openai_tool_conversion(self):
		wire = openai_client.to_wire_tools(CANONICAL_TOOLS)
		self.assertEqual(wire[0]["type"], "function")
		fn = wire[0]["function"]
		self.assertEqual(fn["name"], "run_query")
		self.assertEqual(fn["parameters"]["required"], ["sql"])

	def test_openai_error_tool_result_flagged(self):
		msgs = [{"role": "tool_result", "tool_use_id": "x", "content": "boom", "is_error": True}]
		wire = openai_client.to_wire_messages(msgs)
		self.assertTrue(wire[0]["content"].startswith("ERROR:"))
