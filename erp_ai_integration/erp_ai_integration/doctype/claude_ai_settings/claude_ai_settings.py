# Copyright (c) 2026, Craft and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ClaudeAISettings(Document):
	def validate(self):
		if not self.provider:
			self.provider = "Claude"
		self.max_tokens = max(256, self.max_tokens or 4096)
		self.max_tool_iterations = min(max(1, self.max_tool_iterations or 8), 25)
		self.default_row_limit = min(max(1, self.default_row_limit or 100), 500)
		self.query_timeout = min(max(1, self.query_timeout or 15), 120)
		self.validate_allowed_users()

	def validate_allowed_users(self):
		seen = set()
		for row in self.allowed_users or []:
			if row.user in seen:
				frappe.throw(_("User {0} appears more than once in Allowed Users").format(row.user))
			seen.add(row.user)

	def get_model(self) -> str:
		"""Effective model for the active provider (custom_model overrides)."""
		custom = (self.custom_model or "").strip()
		if custom:
			return custom
		if self.provider == "ChatGPT":
			return self.openai_model or "gpt-4o"
		return self.model or "claude-sonnet-4-6"

	def get_active_api_key(self) -> str | None:
		"""Decrypted API key of the selected provider."""
		field = "openai_api_key" if self.provider == "ChatGPT" else "api_key"
		return self.get_password(field, raise_exception=False)


def get_settings() -> ClaudeAISettings:
	return frappe.get_cached_doc("Claude AI Settings")


def check_enabled():
	"""Raise if the integration is switched off. Called by every endpoint."""
	settings = get_settings()
	if not settings.enabled:
		frappe.throw(_("Claude AI integration is not enabled. Please contact your Administrator."))
	return settings
