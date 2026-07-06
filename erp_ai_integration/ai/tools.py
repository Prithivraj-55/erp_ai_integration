"""Tool definitions + handlers for the AI agent loop.

Definitions use the canonical (Anthropic-style) schema — ai/client.py adapters
convert for other providers automatically.

Every handler is permission-checked for the *asking* user. Errors are returned
to the model as tool errors (is_error=True) so it can self-correct or deliver
the standard permission-denied message.
"""

import json
import re

import frappe

from erp_ai_integration.db.readonly_connection import run_readonly_query
from erp_ai_integration.db.sql_guard import GuardError, guard_sql
from erp_ai_integration.permissions.access import (
	SYSTEM_DENYLIST,
	PermissionDenied,
	user_can_query_doctype,
)

TOOL_DEFINITIONS = [
	{
		"name": "search_doctypes",
		"description": (
			"Search available DocTypes by keywords. Returns matching DocType names with "
			"module, description and whether the current user may query them. "
			"Use this FIRST to find which DocType holds the data for the user's question."
		),
		"input_schema": {
			"type": "object",
			"properties": {
				"keywords": {
					"type": "string",
					"description": "Search words, e.g. 'sales invoice' or 'stock balance'",
				}
			},
			"required": ["keywords"],
		},
	},
	{
		"name": "get_doctype_schema",
		"description": (
			"Get the SQL table name, columns (name, type, label), child tables and link "
			"relationships for a DocType. Only works for DocTypes the current user is "
			"permitted to query."
		),
		"input_schema": {
			"type": "object",
			"properties": {"doctype": {"type": "string", "description": "Exact DocType name"}},
			"required": ["doctype"],
		},
	},
	{
		"name": "run_query",
		"description": (
			"Run a read-only SQL SELECT query. Single statement only, no CTEs. "
			"Tables must be `tab<DocType>` and are permission-checked; results are capped."
		),
		"input_schema": {
			"type": "object",
			"properties": {"sql": {"type": "string", "description": "The SELECT statement"}},
			"required": ["sql"],
		},
	},
]

# term -> DocType names. Seeded with ERPNext vocabulary; extend freely.
SYNONYM_MAP = {
	"sales": ["Sales Invoice", "Sales Order"],
	"invoice": ["Sales Invoice", "Purchase Invoice"],
	"bill": ["Purchase Invoice"],
	"order": ["Sales Order", "Purchase Order"],
	"purchase": ["Purchase Order", "Purchase Invoice", "Purchase Receipt"],
	"customer": ["Customer"],
	"client": ["Customer"],
	"supplier": ["Supplier"],
	"vendor": ["Supplier"],
	"item": ["Item"],
	"product": ["Item"],
	"stock": ["Stock Entry", "Bin", "Stock Ledger Entry"],
	"inventory": ["Bin", "Stock Ledger Entry"],
	"warehouse": ["Warehouse", "Bin"],
	"payment": ["Payment Entry"],
	"receipt": ["Purchase Receipt", "Payment Entry"],
	"delivery": ["Delivery Note"],
	"quotation": ["Quotation", "Supplier Quotation"],
	"quote": ["Quotation"],
	"lead": ["Lead"],
	"opportunity": ["Opportunity"],
	"employee": ["Employee"],
	"staff": ["Employee"],
	"attendance": ["Attendance"],
	"leave": ["Leave Application"],
	"salary": ["Salary Slip"],
	"payroll": ["Salary Slip"],
	"expense": ["Expense Claim"],
	"journal": ["Journal Entry"],
	"ledger": ["GL Entry", "Stock Ledger Entry"],
	"account": ["Account", "GL Entry"],
	"company": ["Company"],
	"project": ["Project", "Task"],
	"task": ["Task"],
	"bom": ["BOM"],
	"production": ["Work Order"],
	"manufacturing": ["Work Order", "BOM"],
	"asset": ["Asset"],
	"material": ["Material Request", "Stock Entry"],
}

MAX_CANDIDATES = 15

FIELDTYPE_TO_SQL = {
	"Data": "varchar", "Select": "varchar", "Link": "varchar", "Dynamic Link": "varchar",
	"Small Text": "text", "Text": "text", "Long Text": "longtext",
	"Text Editor": "longtext", "Code": "longtext", "Markdown Editor": "longtext",
	"HTML Editor": "longtext", "JSON": "json",
	"Int": "int", "Check": "int(1)", "Long Int": "bigint",
	"Float": "decimal", "Currency": "decimal", "Percent": "decimal", "Rating": "decimal",
	"Date": "date", "Datetime": "datetime", "Time": "time", "Duration": "decimal",
	"Attach": "text", "Attach Image": "text", "Barcode": "longtext",
	"Color": "varchar", "Phone": "varchar", "Autocomplete": "varchar",
	"Read Only": "varchar", "Signature": "longtext", "Geolocation": "longtext",
}

LAYOUT_FIELDTYPES = {
	"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading",
	"Fold", "Image", "Table", "Table MultiSelect",
}


def search_doctypes(keywords: str, user: str) -> list[dict]:
	terms = [t for t in re.split(r"[,\s]+", (keywords or "").strip().lower()) if t]
	if not terms:
		return []

	scores: dict[str, int] = {}

	def bump(doctype: str, score: int):
		if doctype in SYSTEM_DENYLIST:
			return
		scores[doctype] = max(scores.get(doctype, 0), score)

	full_phrase = " ".join(terms)

	# 1. synonym hits (high confidence)
	for term in terms + [full_phrase]:
		for doctype in SYNONYM_MAP.get(term, []):
			if frappe.db.exists("DocType", doctype):
				bump(doctype, 80)

	# 2. LIKE search on name / module / description
	seen_rows = {}
	for term in {full_phrase, *terms}:
		rows = frappe.db.sql(
			"""select name, module, description from `tabDocType`
			where istable = 0 and issingle = 0 and is_virtual = 0
			and (name like %(t)s or module like %(t)s or description like %(t)s)
			limit 60""",
			{"t": f"%{term}%"},
			as_dict=True,
		)
		for row in rows:
			seen_rows[row.name] = row
			lowered = row.name.lower()
			if lowered == full_phrase or lowered == term:
				bump(row.name, 100)
			elif lowered.startswith(term):
				bump(row.name, 60)
			elif term in lowered:
				bump(row.name, 50)
			else:
				bump(row.name, 30)  # matched module/description only

	ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_CANDIDATES]

	results = []
	for doctype, score in ranked:
		row = seen_rows.get(doctype) or frappe.db.get_value(
			"DocType", doctype, ["name", "module", "description"], as_dict=True
		)
		if not row:
			continue
		results.append({
			"doctype": doctype,
			"module": row.module,
			"description": (row.description or "")[:140],
			"accessible": user_can_query_doctype(user, doctype),
		})
	return results


def get_doctype_schema(doctype: str, user: str) -> dict:
	if not frappe.db.exists("DocType", doctype):
		raise GuardError(f"DocType '{doctype}' does not exist. Use search_doctypes to find the right name.")
	if not user_can_query_doctype(user, doctype):
		raise PermissionDenied(doctype)

	meta = frappe.get_meta(doctype)
	fields, child_tables, links = [], [], []

	for df in meta.fields:
		if df.fieldtype in ("Table", "Table MultiSelect"):
			child_tables.append({
				"fieldname": df.fieldname,
				"child_doctype": df.options,
				"child_table": f"tab{df.options}",
				"note": "join via child.parent = parent.name and child.parenttype = %s" % doctype,
			})
			continue
		if df.fieldtype in LAYOUT_FIELDTYPES:
			continue
		fields.append({
			"column": df.fieldname,
			"type": FIELDTYPE_TO_SQL.get(df.fieldtype, "varchar"),
			"label": df.label or df.fieldname,
		})
		if df.fieldtype == "Link" and df.options:
			links.append({"column": df.fieldname, "links_to_doctype": df.options})

	return {
		"doctype": doctype,
		"table": f"tab{doctype}",
		"is_submittable": bool(meta.is_submittable),
		"standard_columns": [
			{"column": "name", "type": "varchar", "label": "ID (primary key)"},
			{"column": "creation", "type": "datetime", "label": "Created On"},
			{"column": "modified", "type": "datetime", "label": "Last Modified"},
			{"column": "owner", "type": "varchar", "label": "Created By (user email)"},
			{"column": "docstatus", "type": "int", "label": "Document Status (0=Draft, 1=Submitted, 2=Cancelled)"},
		],
		"fields": fields,
		"child_tables": child_tables,
		"links": links,
	}


def run_query(sql: str, user: str) -> dict:
	settings = frappe.get_cached_doc("Claude AI Settings")
	safe_sql = guard_sql(sql, user, row_limit=settings.default_row_limit or 100)
	result = run_readonly_query(safe_sql)
	result["executed_sql"] = safe_sql
	return result


def permission_denied_payload(doctype: str) -> str:
	return json.dumps({
		"error": "permission_denied",
		"doctype": doctype,
		"instruction": (
			f"Tell the user: This data needs to be checked in **{doctype}**, but you are "
			"not allowed to access it. Please contact your Administrator to get the "
			"desired report or to update your permission. Do not attempt workarounds."
		),
	})


def handle_tool_call(name: str, args: dict, user: str) -> tuple[str, bool]:
	"""Execute one tool call. Returns (content_json, is_error) for the
	tool_result message."""
	try:
		if name == "search_doctypes":
			return json.dumps({"candidates": search_doctypes(args.get("keywords") or "", user)}, default=str), False
		if name == "get_doctype_schema":
			return json.dumps(get_doctype_schema(args.get("doctype") or "", user), default=str), False
		if name == "run_query":
			return json.dumps(run_query(args.get("sql") or "", user), default=str), False
		return json.dumps({"error": f"Unknown tool: {name}"}), True
	except PermissionDenied as e:
		return permission_denied_payload(e.doctype), True
	except GuardError as e:
		return json.dumps({"error": "query_rejected", "reason": str(e)}), True
	except Exception as e:
		frappe.log_error(title="AI tool error", message=frappe.get_traceback())
		return json.dumps({"error": "tool_failed", "reason": str(e)[:300]}), True
