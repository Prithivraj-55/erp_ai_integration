# Copyright (c) 2026, Craft and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AIChatMessage(Document):
	pass


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return None
	return f"`tabAI Chat Message`.`owner` = {frappe.db.escape(user)}"
