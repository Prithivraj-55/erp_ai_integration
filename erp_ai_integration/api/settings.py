"""Whitelisted endpoints for the Claude AI Settings form.

All endpoints are System Manager only.
"""

import frappe
from frappe import _

from erp_ai_integration.ai import client as ai_client
from erp_ai_integration.db import readonly_user


def _only_system_manager():
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def test_connection():
	"""Tiny Messages API call; stores the result on the settings doc."""
	_only_system_manager()
	settings = frappe.get_doc("Claude AI Settings")
	try:
		result = ai_client.ping()
		settings.connection_status = _("Connected — {0} ({1})").format(result["provider"], result["model"])
		status = {"success": True, "provider": result["provider"], "model": result["model"]}
		from erp_ai_integration.erp_ai_integration.doctype.ai_usage_log.ai_usage_log import log_usage

		log_usage(
			user=frappe.session.user,
			model=result["model"],
			input_tokens=result["input_tokens"],
			output_tokens=result["output_tokens"],
			request_type="test",
		)
	except Exception as e:
		settings.connection_status = _("Failed: {0}").format(str(e)[:120])
		status = {"success": False, "error": str(e)}

	settings.last_test_on = frappe.utils.now_datetime()
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	return status


@frappe.whitelist()
def create_readonly_db_user(admin_user: str, admin_password: str):
	"""Create the read-only DB user with one-time admin credentials.
	On failure (managed DBs, host restrictions) returns the manual SQL."""
	_only_system_manager()
	settings = frappe.get_doc("Claude AI Settings")
	if settings.db_user_created:
		frappe.throw(_("A read-only DB user already exists. Use Drop & Recreate to rotate it."))
	return readonly_user.create_user(admin_user, admin_password)


@frappe.whitelist()
def set_manual_db_user(username: str, password: str):
	"""Store credentials for a manually-created read-only user (e.g. on RDS or
	other managed databases where auto-creation is restricted). The connection
	is verified and confirmed SELECT-only before anything is stored."""
	_only_system_manager()
	result = readonly_user.verify_user(username, password)
	if not result.get("success"):
		return result
	readonly_user.store_credentials(username, password, mode="Manual")
	return result


@frappe.whitelist()
def get_manual_setup_sql():
	"""Generate fresh credentials + the SQL for fully manual setup (shown when
	the admin chooses manual setup without attempting auto-creation)."""
	_only_system_manager()
	username, password = readonly_user.generate_credentials()
	return {
		"username": username,
		"password": password,
		"sql": readonly_user.get_manual_setup_sql(username, password),
	}


@frappe.whitelist()
def verify_readonly_user():
	"""Re-verify the stored read-only credentials (SELECT works, grants are
	SELECT-only)."""
	_only_system_manager()
	settings = frappe.get_doc("Claude AI Settings")
	if not settings.db_user_created:
		frappe.throw(_("No read-only DB user is configured."))
	password = settings.get_password("readonly_db_password", raise_exception=False)
	return readonly_user.verify_user(settings.readonly_db_user, password)


@frappe.whitelist()
def drop_readonly_db_user(admin_user: str, admin_password: str):
	"""Drop the RO user so it can be recreated (credential rotation)."""
	_only_system_manager()
	return readonly_user.drop_user(admin_user, admin_password)


@frappe.whitelist()
def get_budget_status():
	"""Monthly token usage vs monthly_token_budget, for the settings-page
	indicator. budget=0 means unlimited (percent is None in that case)."""
	_only_system_manager()
	from erp_ai_integration.erp_ai_integration.doctype.ai_usage_log.ai_usage_log import (
		get_tokens_used_this_month,
	)

	settings = frappe.get_cached_doc("Claude AI Settings")
	used = get_tokens_used_this_month()
	budget = settings.monthly_token_budget or 0
	percent = round(min(used / budget, 1.0) * 100, 1) if budget else None
	return {
		"used": used,
		"budget": budget,
		"percent": percent,
		"total_input_tokens": settings.total_input_tokens,
		"total_output_tokens": settings.total_output_tokens,
	}
