"""Unit tests for the AI tool handlers (Phase 3). No AI-provider calls.

Run: bench --site assesment run-tests --module erp_ai_integration.tests.test_tools
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_ai_integration.ai.tools import (
	get_doctype_schema,
	handle_tool_call,
	search_doctypes,
)
from erp_ai_integration.permissions.access import PermissionDenied

ADMIN = "Administrator"
ROLE_USER = "ai-tools-role@example.com"


class TestTools(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("User", ROLE_USER):
			user = frappe.get_doc({
				"doctype": "User",
				"email": ROLE_USER,
				"first_name": "ai-tools-role",
				"send_welcome_email": 0,
			}).insert(ignore_permissions=True)
			user.add_roles("AI Chat User")

		settings = frappe.get_doc("Claude AI Settings")
		if not any(r.user == ROLE_USER for r in settings.allowed_users or []):
			settings.append(
				"allowed_users",
				{"user": ROLE_USER, "access_mode": "Based on Role Permission", "enabled": 1},
			)
			settings.save(ignore_permissions=True)
			frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")

	# ---- search_doctypes ----

	def test_search_finds_exact_name(self):
		results = search_doctypes("sales invoice", ADMIN)
		names = [r["doctype"] for r in results]
		self.assertIn("Sales Invoice", names)
		self.assertEqual(names[0], "Sales Invoice")  # exact match ranks first

	def test_search_synonyms(self):
		names = [r["doctype"] for r in search_doctypes("customer", ADMIN)]
		self.assertIn("Customer", names)
		names = [r["doctype"] for r in search_doctypes("stock", ADMIN)]
		self.assertTrue({"Stock Entry", "Stock Ledger Entry", "Bin"} & set(names))

	def test_search_excludes_child_and_single(self):
		names = [r["doctype"] for r in search_doctypes("sales invoice item", ADMIN)]
		self.assertNotIn("Sales Invoice Item", names)  # istable
		names = [r["doctype"] for r in search_doctypes("system settings", ADMIN)]
		self.assertNotIn("System Settings", names)  # issingle

	def test_search_accessible_flags(self):
		results = search_doctypes("sales invoice", ROLE_USER)
		row = next(r for r in results if r["doctype"] == "Sales Invoice")
		self.assertFalse(row["accessible"])  # role user has no read perm
		results = search_doctypes("sales invoice", ADMIN)
		row = next(r for r in results if r["doctype"] == "Sales Invoice")
		self.assertTrue(row["accessible"])

	def test_search_empty(self):
		self.assertEqual(search_doctypes("", ADMIN), [])

	# ---- get_doctype_schema ----

	def test_schema_contents(self):
		schema = get_doctype_schema("Sales Invoice", ADMIN)
		self.assertEqual(schema["table"], "tabSales Invoice")
		self.assertTrue(schema["is_submittable"])
		columns = {f["column"] for f in schema["fields"]}
		self.assertIn("posting_date", columns)
		self.assertIn("customer", columns)
		child = next(c for c in schema["child_tables"] if c["fieldname"] == "items")
		self.assertEqual(child["child_doctype"], "Sales Invoice Item")
		link = next(l for l in schema["links"] if l["column"] == "customer")
		self.assertEqual(link["links_to_doctype"], "Customer")
		# labels present (they drive SQL quality)
		labelled = next(f for f in schema["fields"] if f["column"] == "posting_date")
		self.assertTrue(labelled["label"])

	def test_schema_permission_denied(self):
		with self.assertRaises(PermissionDenied):
			get_doctype_schema("Sales Invoice", ROLE_USER)

	# ---- handle_tool_call dispatcher ----

	def test_dispatcher_search(self):
		content, is_error = handle_tool_call("search_doctypes", {"keywords": "customer"}, ADMIN)
		self.assertFalse(is_error)
		self.assertIn("Customer", content)

	def test_dispatcher_permission_denied_payload(self):
		content, is_error = handle_tool_call("get_doctype_schema", {"doctype": "Sales Invoice"}, ROLE_USER)
		self.assertTrue(is_error)
		payload = json.loads(content)
		self.assertEqual(payload["error"], "permission_denied")
		self.assertEqual(payload["doctype"], "Sales Invoice")
		self.assertIn("contact your Administrator", payload["instruction"])

	def test_dispatcher_guard_rejection(self):
		content, is_error = handle_tool_call("run_query", {"sql": "DROP TABLE `tabCustomer`"}, ADMIN)
		self.assertTrue(is_error)
		self.assertEqual(json.loads(content)["error"], "query_rejected")

	def test_dispatcher_run_query(self):
		# behaves correctly whether or not the RO user is configured on this site
		content, is_error = handle_tool_call(
			"run_query", {"sql": "SELECT count(*) AS c FROM `tabCustomer`"}, ADMIN
		)
		payload = json.loads(content)
		if frappe.get_cached_doc("Claude AI Settings").db_user_created:
			self.assertFalse(is_error)
			self.assertEqual(payload["columns"], ["c"])
			self.assertIn("LIMIT", payload["executed_sql"])
		else:
			self.assertTrue(is_error)
			self.assertEqual(payload["error"], "tool_failed")

	def test_dispatcher_unknown_tool(self):
		content, is_error = handle_tool_call("nonsense", {}, ADMIN)
		self.assertTrue(is_error)
