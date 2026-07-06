"""Unit tests for the SQL guard — the security core of the app.

Run: bench --site assesment run-tests --module erp_ai_integration.tests.test_sql_guard
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_ai_integration.db.sql_guard import GuardError, PermissionDenied, extract_tables, guard_sql
from erp_ai_integration.permissions.access import get_access_mode, user_can_query_doctype

ADMIN = "Administrator"
ROLE_USER = "ai-guard-role@example.com"
ALL_USER = "ai-guard-all@example.com"


class TestSQLGuard(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for email in (ROLE_USER, ALL_USER):
			if not frappe.db.exists("User", email):
				user = frappe.get_doc({
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"send_welcome_email": 0,
				}).insert(ignore_permissions=True)
				user.add_roles("AI Chat User")

		settings = frappe.get_doc("Claude AI Settings")
		settings.set("allowed_users", [])
		settings.append("allowed_users", {"user": ROLE_USER, "access_mode": "Based on Role Permission", "enabled": 1})
		settings.append("allowed_users", {"user": ALL_USER, "access_mode": "Allow All Tables", "enabled": 1})
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")

	# ---- happy path ----

	def test_simple_select_gets_limit(self):
		out = guard_sql("SELECT name FROM `tabCustomer`", ADMIN, row_limit=100)
		self.assertTrue(out.endswith("LIMIT 100"))

	def test_existing_limit_respected(self):
		out = guard_sql("SELECT name FROM `tabCustomer` LIMIT 5", ADMIN, row_limit=100)
		self.assertTrue(out.rstrip().endswith("LIMIT 5"))

	def test_oversized_limit_capped(self):
		out = guard_sql("SELECT name FROM `tabCustomer` LIMIT 5000", ADMIN, row_limit=100)
		self.assertTrue(out.rstrip().endswith("LIMIT 100"))

	def test_offset_limit_capped(self):
		out = guard_sql("SELECT name FROM `tabCustomer` LIMIT 10, 5000", ADMIN, row_limit=100)
		self.assertTrue(out.rstrip().endswith("LIMIT 100"))

	def test_trailing_semicolon_ok(self):
		out = guard_sql("SELECT count(*) FROM `tabItem`;", ADMIN)
		self.assertIn("tabItem", out)

	def test_join_and_aliases(self):
		sql = """SELECT si.name, c.customer_name
			FROM `tabSales Invoice` si
			LEFT JOIN `tabCustomer` c ON c.name = si.customer
			WHERE si.docstatus = 1"""
		out = guard_sql(sql, ADMIN)
		self.assertIn("LIMIT", out)

	def test_subquery_tables_extracted(self):
		sql = """SELECT name FROM `tabCustomer`
			WHERE name IN (SELECT customer FROM `tabSales Invoice` WHERE docstatus = 1)"""
		stmt = __import__("sqlparse").parse(sql)[0]
		tables = extract_tables(stmt)
		self.assertEqual(tables, {"tabCustomer", "tabSales Invoice"})

	def test_derived_table(self):
		sql = """SELECT t.total FROM (SELECT sum(grand_total) total FROM `tabSales Invoice`) t"""
		stmt = __import__("sqlparse").parse(sql)[0]
		self.assertEqual(extract_tables(stmt), {"tabSales Invoice"})

	# ---- structural rejections ----

	def test_multi_statement_rejected(self):
		with self.assertRaises(GuardError):
			guard_sql("SELECT 1; DROP TABLE `tabCustomer`", ADMIN)

	def test_non_select_rejected(self):
		for sql in (
			"UPDATE `tabCustomer` SET customer_name = 'x'",
			"DELETE FROM `tabCustomer`",
			"INSERT INTO `tabCustomer` (name) VALUES ('x')",
			"DROP TABLE `tabCustomer`",
			"TRUNCATE TABLE `tabCustomer`",
			"GRANT ALL ON *.* TO 'x'@'%'",
		):
			with self.assertRaises(GuardError, msg=sql):
				guard_sql(sql, ADMIN)

	def test_cte_rejected(self):
		with self.assertRaises(GuardError):
			guard_sql("WITH x AS (SELECT 1) SELECT * FROM x", ADMIN)

	def test_comment_smuggling_stripped(self):
		# executable comment hiding a second statement
		with self.assertRaises(GuardError):
			guard_sql("SELECT 1 /*! ; DROP TABLE `tabCustomer` */", ADMIN)

	def test_forbidden_functions(self):
		for sql in (
			"SELECT name FROM `tabCustomer` INTO OUTFILE '/tmp/x'",
			"SELECT LOAD_FILE('/etc/passwd')",
			"SELECT SLEEP(10)",
			"SELECT BENCHMARK(1000000, MD5('x'))",
			"SELECT * FROM INFORMATION_SCHEMA.TABLES",
			"SELECT name FROM `tabCustomer` FOR UPDATE",
		):
			with self.assertRaises(GuardError, msg=sql):
				guard_sql(sql, ADMIN)

	def test_schema_qualified_rejected(self):
		with self.assertRaises(GuardError):
			guard_sql("SELECT * FROM mysql.user", ADMIN)

	# ---- permission rejections ----

	def test_raw_denylist_tables(self):
		for table in ("__Auth", "tabSingles", "tabDefaultValue"):
			with self.assertRaises(PermissionDenied, msg=table):
				guard_sql(f"SELECT * FROM `{table}`", ADMIN)

	def test_denylist_doctype_blocked_even_for_admin(self):
		with self.assertRaises(PermissionDenied):
			guard_sql("SELECT * FROM `tabOAuth Bearer Token`", ADMIN)

	def test_non_tab_table_rejected(self):
		with self.assertRaises(PermissionDenied):
			guard_sql("SELECT * FROM secrets", ADMIN)

	def test_join_with_denied_table_rejected(self):
		sql = "SELECT * FROM `tabCustomer` c JOIN `tabSingles` s ON 1=1"
		with self.assertRaises(PermissionDenied):
			guard_sql(sql, ADMIN)

	# ---- access modes ----

	def test_access_modes(self):
		self.assertEqual(get_access_mode(ADMIN), "all")
		self.assertEqual(get_access_mode(ALL_USER), "all")
		self.assertEqual(get_access_mode(ROLE_USER), "role")
		self.assertIsNone(get_access_mode("Guest"))

	def test_all_tables_user(self):
		self.assertTrue(user_can_query_doctype(ALL_USER, "Sales Invoice"))
		self.assertFalse(user_can_query_doctype(ALL_USER, "OAuth Bearer Token"))  # denylist wins

	def test_role_mode_user_restricted(self):
		# AI Chat User role has no read permission on Sales Invoice
		self.assertFalse(user_can_query_doctype(ROLE_USER, "Sales Invoice"))
		with self.assertRaises(PermissionDenied) as ctx:
			guard_sql("SELECT count(*) FROM `tabSales Invoice`", ROLE_USER)
		self.assertEqual(ctx.exception.doctype, "Sales Invoice")

	def test_disabled_row_blocks_access(self):
		settings = frappe.get_doc("Claude AI Settings")
		for row in settings.allowed_users:
			if row.user == ALL_USER:
				row.enabled = 0
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")
		try:
			self.assertIsNone(get_access_mode(ALL_USER))
		finally:
			settings = frappe.get_doc("Claude AI Settings")
			for row in settings.allowed_users:
				if row.user == ALL_USER:
					row.enabled = 1
			settings.save(ignore_permissions=True)
			frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")
