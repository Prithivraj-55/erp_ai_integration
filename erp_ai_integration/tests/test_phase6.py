"""Unit tests for Phase 6 polish: usage report query + budget status endpoint.

Run: bench --site assesment run-tests --module erp_ai_integration.tests.test_phase6
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_ai_integration.api.settings import get_budget_status
from erp_ai_integration.erp_ai_integration.report.ai_usage_summary.ai_usage_summary import (
	execute,
)


class TestUsageReport(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.logs = []
		for model, inp, out in (
			("claude-sonnet-4-6", 100, 50),
			("claude-sonnet-4-6", 200, 80),
			("gpt-4o", 40, 20),
		):
			doc = frappe.get_doc({
				"doctype": "AI Usage Log",
				"user": "Administrator",
				"model": model,
				"request_type": "chat",
				"input_tokens": inp,
				"output_tokens": out,
				"estimated_cost": 0.01,
			}).insert(ignore_permissions=True)
			self.logs.append(doc.name)

	def tearDown(self):
		for name in self.logs:
			frappe.delete_doc("AI Usage Log", name, ignore_permissions=True, force=True)
		super().tearDown()

	def test_report_totals_by_model(self):
		today = frappe.utils.nowdate()
		columns, data, _, chart = execute({"from_date": today, "to_date": today})
		self.assertTrue(columns)
		sonnet_rows = [r for r in data if r.model == "claude-sonnet-4-6" and r.user == "Administrator"]
		self.assertEqual(len(sonnet_rows), 1)  # grouped into one row per date+user+model
		self.assertEqual(sonnet_rows[0].requests, 2)
		self.assertEqual(sonnet_rows[0].input_tokens, 300)
		self.assertEqual(sonnet_rows[0].output_tokens, 130)
		self.assertEqual(sonnet_rows[0].total_tokens, 430)

	def test_report_filters_by_model(self):
		today = frappe.utils.nowdate()
		_, data, _, _ = execute({"from_date": today, "to_date": today, "model": "gpt-4o"})
		self.assertTrue(all(r.model == "gpt-4o" for r in data))

	def test_report_date_range_excludes_out_of_range(self):
		yesterday = frappe.utils.add_days(frappe.utils.nowdate(), -1)
		_, data, _, _ = execute({"from_date": yesterday, "to_date": yesterday})
		self.assertEqual(len(data), 0)

	def test_report_chart_shape(self):
		today = frappe.utils.nowdate()
		_, _, _, chart = execute({"from_date": today, "to_date": today})
		self.assertEqual(chart["type"], "bar")
		self.assertIn("labels", chart["data"])


class TestBudgetStatus(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.original_budget = frappe.db.get_single_value("Claude AI Settings", "monthly_token_budget")

	def tearDown(self):
		frappe.db.set_single_value("Claude AI Settings", "monthly_token_budget", self.original_budget or 0)
		frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")
		super().tearDown()

	def test_unlimited_budget_returns_none_percent(self):
		frappe.db.set_single_value("Claude AI Settings", "monthly_token_budget", 0)
		frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")
		result = get_budget_status()
		self.assertIsNone(result["percent"])
		self.assertEqual(result["budget"], 0)

	def test_budget_percent_capped_at_100(self):
		# ensure at least some usage exists this month, then set a tiny budget
		# so usage necessarily exceeds it -> percent must cap at 100, not overshoot
		log = frappe.get_doc({
			"doctype": "AI Usage Log", "user": "Administrator", "model": "claude-sonnet-4-6",
			"request_type": "chat", "input_tokens": 500, "output_tokens": 500,
			"estimated_cost": 0.01,
		}).insert(ignore_permissions=True)
		try:
			frappe.db.set_single_value("Claude AI Settings", "monthly_token_budget", 1)
			frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")
			result = get_budget_status()
			self.assertEqual(result["percent"], 100.0)
		finally:
			frappe.delete_doc("AI Usage Log", log.name, ignore_permissions=True, force=True)

	def test_non_system_manager_blocked(self):
		unlisted = "phase6-nonadmin@example.com"
		if not frappe.db.exists("User", unlisted):
			frappe.get_doc({
				"doctype": "User", "email": unlisted, "first_name": "nonadmin",
				"send_welcome_email": 0,
			}).insert(ignore_permissions=True)
		frappe.set_user(unlisted)
		try:
			with self.assertRaises(frappe.PermissionError):
				get_budget_status()
		finally:
			frappe.set_user("Administrator")
