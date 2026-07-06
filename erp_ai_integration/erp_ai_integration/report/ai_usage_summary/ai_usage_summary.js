// Copyright (c) 2026, Craft and contributors
// For license information, please see license.txt

frappe.query_reports["AI Usage Summary"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "user",
			label: __("User"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "model",
			label: __("Model"),
			fieldtype: "Data",
		},
		{
			fieldname: "request_type",
			label: __("Request Type"),
			fieldtype: "Select",
			options: "\nchat\ntest\ntitle",
		},
	],
};
