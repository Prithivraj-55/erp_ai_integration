# Copyright (c) 2026, Craft and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	return columns, data, None, chart


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": _("User"), "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 180},
		{"label": _("Model"), "fieldname": "model", "fieldtype": "Data", "width": 150},
		{"label": _("Requests"), "fieldname": "requests", "fieldtype": "Int", "width": 90},
		{"label": _("Input Tokens"), "fieldname": "input_tokens", "fieldtype": "Int", "width": 110},
		{"label": _("Output Tokens"), "fieldname": "output_tokens", "fieldtype": "Int", "width": 110},
		{"label": _("Total Tokens"), "fieldname": "total_tokens", "fieldtype": "Int", "width": 110},
		{"label": _("Estimated Cost (USD)"), "fieldname": "estimated_cost", "fieldtype": "Currency", "width": 140},
	]


def get_data(filters):
	conditions, values = build_conditions(filters)
	rows = frappe.db.sql(
		f"""
		select
			DATE(creation) as date,
			user,
			model,
			count(*) as requests,
			sum(input_tokens) as input_tokens,
			sum(output_tokens) as output_tokens,
			sum(input_tokens + output_tokens) as total_tokens,
			sum(estimated_cost) as estimated_cost
		from `tabAI Usage Log`
		where {conditions}
		group by DATE(creation), user, model
		order by date desc, total_tokens desc
		""",
		values,
		as_dict=True,
	)
	for row in rows:
		row.estimated_cost = flt(row.estimated_cost, 6)
	return rows


def build_conditions(filters):
	conditions = ["1=1"]
	values = {}

	from_date = filters.get("from_date") or frappe.utils.get_first_day(frappe.utils.nowdate())
	to_date = filters.get("to_date") or frappe.utils.nowdate()
	conditions.append("DATE(creation) between %(from_date)s and %(to_date)s")
	values["from_date"] = from_date
	values["to_date"] = to_date

	if filters.get("user"):
		conditions.append("user = %(user)s")
		values["user"] = filters["user"]

	if filters.get("model"):
		conditions.append("model = %(model)s")
		values["model"] = filters["model"]

	if filters.get("request_type"):
		conditions.append("request_type = %(request_type)s")
		values["request_type"] = filters["request_type"]

	return " and ".join(conditions), values


def get_chart(data):
	by_date = {}
	for row in data:
		by_date[row.date] = by_date.get(row.date, 0) + (row.total_tokens or 0)
	labels = sorted(by_date.keys())
	return {
		"data": {
			"labels": [frappe.utils.formatdate(d) for d in labels],
			"datasets": [{"name": _("Total Tokens"), "values": [by_date[d] for d in labels]}],
		},
		"type": "bar",
		"fieldtype": "Int",
	}
