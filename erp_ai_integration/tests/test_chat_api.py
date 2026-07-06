"""Unit tests for the chat endpoints (Phase 4). No AI-provider calls —
send_message is tested up to the provider boundary (no API key configured).

Run: bench --site assesment run-tests --module erp_ai_integration.tests.test_chat_api
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_ai_integration.api import chat as chat_api

CHAT_USER = "ai-chat-user@example.com"
OTHER_USER = "ai-chat-other@example.com"


class TestChatAPI(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for email in (CHAT_USER, OTHER_USER):
			if not frappe.db.exists("User", email):
				user = frappe.get_doc({
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"send_welcome_email": 0,
				}).insert(ignore_permissions=True)
				user.add_roles("AI Chat User")

		settings = frappe.get_doc("Claude AI Settings")
		existing = {r.user for r in settings.allowed_users or []}
		for email in (CHAT_USER, OTHER_USER):
			if email not in existing:
				settings.append(
					"allowed_users",
					{"user": email, "access_mode": "Allow All Tables", "enabled": 1},
				)
		settings.save(ignore_permissions=True)

	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("Claude AI Settings", "enabled", 1)
		frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")
		frappe.set_user(CHAT_USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Claude AI Settings", "enabled", 0)
		frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")
		super().tearDown()

	def _new_chat(self):
		return chat_api.create_chat()["name"]

	def test_disabled_integration_blocks(self):
		frappe.db.set_single_value("Claude AI Settings", "enabled", 0)
		frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")
		with self.assertRaises(frappe.ValidationError):
			chat_api.create_chat()

	def test_unlisted_user_blocked(self):
		unlisted = "ai-chat-unlisted@example.com"
		if not frappe.db.exists("User", unlisted):
			frappe.get_doc({
				"doctype": "User",
				"email": unlisted,
				"first_name": "unlisted",
				"send_welcome_email": 0,
			}).insert(ignore_permissions=True)
		frappe.set_user(unlisted)
		with self.assertRaises(frappe.PermissionError):
			chat_api.create_chat()

	def test_chat_lifecycle(self):
		name = self._new_chat()
		chats = chat_api.get_chats()
		self.assertIn(name, [c.name for c in chats])

		chat_api.rename_chat(name, "My revenue questions")
		self.assertEqual(frappe.db.get_value("AI Chat", name, "title"), "My revenue questions")

		chat_api.archive_chat(name)
		self.assertNotIn(name, [c.name for c in chat_api.get_chats()])
		self.assertIn(name, [c.name for c in chat_api.get_chats(include_archived=1)])

		chat_api.unarchive_chat(name)
		chat_api.delete_chat(name)
		self.assertFalse(frappe.db.exists("AI Chat", name))

	def test_ownership_enforced(self):
		name = self._new_chat()
		frappe.set_user(OTHER_USER)
		with self.assertRaises(frappe.PermissionError):
			chat_api.get_messages(name)
		with self.assertRaises(frappe.PermissionError):
			chat_api.rename_chat(name, "hijack")
		frappe.set_user(CHAT_USER)
		chat_api.delete_chat(name)

	def test_send_message_fails_gracefully_without_api_key(self):
		# no provider API key is configured -> the turn fails, the user message
		# and a system_note are persisted, and a clean error is raised
		name = self._new_chat()
		with self.assertRaises(frappe.ValidationError):
			chat_api.send_message(name, "How many customers do we have?")
		roles = [m.role for m in frappe.get_all(
			"AI Chat Message", filters={"chat": name}, fields=["role"]
		)]
		self.assertIn("user", roles)
		self.assertIn("system_note", roles)
		chat_api.delete_chat(name)

	def test_empty_message_rejected(self):
		name = self._new_chat()
		with self.assertRaises(frappe.ValidationError):
			chat_api.send_message(name, "   ")
		chat_api.delete_chat(name)

	def test_rate_limit(self):
		key = f"ai_chat_rate:{CHAT_USER}:{frappe.utils.now_datetime().strftime('%Y%m%d%H')}"
		frappe.cache().set_value(key, chat_api.RATE_LIMIT_PER_HOUR, expires_in_sec=60)
		try:
			name = self._new_chat()
			with self.assertRaises(frappe.ValidationError):
				chat_api.send_message(name, "hello")
			chat_api.delete_chat(name)
		finally:
			frappe.cache().delete_value(key)

	def test_deleting_chat_removes_messages(self):
		name = self._new_chat()
		frappe.get_doc({
			"doctype": "AI Chat Message", "chat": name, "role": "user", "content": "hi",
		}).insert(ignore_permissions=True)
		chat_api.delete_chat(name)
		self.assertFalse(frappe.db.exists("AI Chat Message", {"chat": name}))

	# ---- Phase 6: feedback ----

	def test_set_feedback_up_and_down(self):
		name = self._new_chat()
		msg = frappe.get_doc({
			"doctype": "AI Chat Message", "chat": name, "role": "assistant", "content": "42",
		}).insert(ignore_permissions=True)

		chat_api.set_message_feedback(msg.name, "Up")
		self.assertEqual(frappe.db.get_value("AI Chat Message", msg.name, "feedback"), "Up")

		chat_api.set_message_feedback(msg.name, "Down")
		self.assertEqual(frappe.db.get_value("AI Chat Message", msg.name, "feedback"), "Down")

		chat_api.set_message_feedback(msg.name, "")
		self.assertEqual(frappe.db.get_value("AI Chat Message", msg.name, "feedback"), "")
		chat_api.delete_chat(name)

	def test_feedback_rejects_invalid_value(self):
		name = self._new_chat()
		msg = frappe.get_doc({
			"doctype": "AI Chat Message", "chat": name, "role": "assistant", "content": "42",
		}).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			chat_api.set_message_feedback(msg.name, "Sideways")
		chat_api.delete_chat(name)

	def test_feedback_rejects_user_message(self):
		name = self._new_chat()
		msg = frappe.get_doc({
			"doctype": "AI Chat Message", "chat": name, "role": "user", "content": "hi",
		}).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			chat_api.set_message_feedback(msg.name, "Up")
		chat_api.delete_chat(name)

	def test_feedback_ownership_enforced(self):
		name = self._new_chat()
		msg = frappe.get_doc({
			"doctype": "AI Chat Message", "chat": name, "role": "assistant", "content": "42",
		}).insert(ignore_permissions=True)
		frappe.set_user(OTHER_USER)
		with self.assertRaises(frappe.PermissionError):
			chat_api.set_message_feedback(msg.name, "Up")
		frappe.set_user(CHAT_USER)
		chat_api.delete_chat(name)
