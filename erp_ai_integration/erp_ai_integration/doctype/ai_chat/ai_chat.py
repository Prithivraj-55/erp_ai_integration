# Copyright (c) 2026, Craft and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AIChat(Document):
	def before_insert(self):
		if not self.user:
			self.user = frappe.session.user
		if not self.last_message_on:
			self.last_message_on = frappe.utils.now_datetime()

	def on_trash(self):
		# remove messages belonging to this chat
		frappe.db.delete("AI Chat Message", {"chat": self.name})


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return None
	return f"`tabAI Chat`.`user` = {frappe.db.escape(user)}"


def has_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return True
	return doc.user == user
