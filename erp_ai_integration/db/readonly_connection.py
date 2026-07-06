"""Separate pymysql connection using the read-only credentials.

Never reuses frappe.db. Opened per request, closed immediately after
(volume is low, no pooling needed). Sets a server-side statement timeout and
a read-only transaction so even a guard bug cannot write.
"""

from contextlib import contextmanager

import frappe
import pymysql
from frappe import _

from erp_ai_integration.db.readonly_user import get_db_connection_params


@contextmanager
def readonly_connection():
	settings = frappe.get_cached_doc("Claude AI Settings")
	username = settings.readonly_db_user
	password = settings.get_password("readonly_db_password", raise_exception=False)
	if not (settings.db_user_created and username and password):
		frappe.throw(_("Read-only database user is not configured in Claude AI Settings."))

	params = get_db_connection_params()
	timeout = settings.query_timeout or 15

	conn = pymysql.connect(
		host=params["host"],
		port=params["port"],
		user=username,
		password=password,
		database=frappe.conf.db_name,
		connect_timeout=10,
		read_timeout=timeout + 5,
		cursorclass=pymysql.cursors.Cursor,
	)
	try:
		with conn.cursor() as cursor:
			# MariaDB: max_statement_time (seconds). MySQL/RDS-MySQL:
			# max_execution_time (milliseconds, SELECT only).
			try:
				cursor.execute("SET SESSION max_statement_time = %s", (timeout,))
			except pymysql.MySQLError:
				try:
					cursor.execute("SET SESSION max_execution_time = %s", (timeout * 1000,))
				except pymysql.MySQLError:
					pass  # variable unsupported — read_timeout still bounds us
			cursor.execute("SET SESSION TRANSACTION READ ONLY")
		yield conn
	finally:
		conn.close()


MAX_RETURNED_ROWS = 100
MAX_CELL_CHARS = 500


def run_readonly_query(sql: str) -> dict:
	"""Execute an already-guard-validated SELECT on the RO connection.

	Returns {"columns": [...], "rows": [...], "row_count": n, "truncated": bool}.
	"""
	with readonly_connection() as conn:
		with conn.cursor() as cursor:
			cursor.execute(sql)
			columns = [d[0] for d in cursor.description] if cursor.description else []
			raw_rows = cursor.fetchmany(MAX_RETURNED_ROWS + 1)

	truncated = len(raw_rows) > MAX_RETURNED_ROWS
	rows = []
	for raw in raw_rows[:MAX_RETURNED_ROWS]:
		row = []
		for cell in raw:
			if isinstance(cell, (bytes, bytearray)):
				cell = cell.decode("utf-8", errors="replace")
			cell = str(cell) if cell is not None else None
			if cell and len(cell) > MAX_CELL_CHARS:
				cell = cell[:MAX_CELL_CHARS] + "…"
			row.append(cell)
		rows.append(row)

	return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated}
