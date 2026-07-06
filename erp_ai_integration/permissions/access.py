"""Access-mode resolution and DocType-level permission checks.

Two gates (both must pass — see plan doc §3.2):
1. The 'AI Chat User' role (managed via Role Permission Manager) gates the
   chat page and endpoints.
2. The allowed_users child table in Claude AI Settings sets each user's data
   scope: 'Allow All Tables' or 'Based on Role Permission'.
"""

import frappe

AI_CHAT_ROLE = "AI Chat User"

# DocTypes nobody may query through the AI, in any access mode.
SYSTEM_DENYLIST = {
	"User",  # password hashes live in __Auth but emails/keys live here
	"DefaultValue",  # raw table tabDefaultValue is denied — keep doctype consistent
	"Sessions",
	"OAuth Bearer Token",
	"OAuth Client",
	"OAuth Authorization Code",
	"Token Cache",
	"Connected App",
	"Email Account",
	"Email Domain",
	"Social Login Key",
	"Webhook",
	"Integration Request",
	"S3 Backup Settings",
	"Dropbox Settings",
	"LDAP Settings",
	"OAuth Settings",
	"Push Notification Settings",
	"API Key",  # if any app defines one
	"Personal Data Download Request",
	"Personal Data Deletion Request",
}

# Raw tables (not DocType-shaped) that must never appear in SQL.
RAW_TABLE_DENYLIST = {
	"__Auth",
	"__global_search",
	"__UserSettings",
	"tabSingles",          # other Single settings can hold credentials
	"tabDefaultValue",     # holds user defaults incl. sensitive values
	"tabSessions",
	"tab__Auth",
}


class PermissionDenied(Exception):
	"""Raised by the SQL guard / tool handlers when the asking user may not
	query a DocType. Carries the doctype so Claude can name it in the standard
	'contact your Administrator' message."""

	def __init__(self, doctype: str):
		self.doctype = doctype
		super().__init__(f"Permission denied for DocType: {doctype}")


def get_access_mode(user: str | None = None) -> str | None:
	"""Returns 'all' | 'role' | None (no access)."""
	user = user or frappe.session.user
	if user == "Administrator":
		return "all"

	roles = frappe.get_roles(user)
	settings = frappe.get_cached_doc("Claude AI Settings")

	row = next((r for r in (settings.allowed_users or []) if r.user == user), None)
	if row:
		if not row.enabled:
			return None
		if AI_CHAT_ROLE not in roles and "System Manager" not in roles:
			return None
		return "all" if row.access_mode == "Allow All Tables" else "role"

	# not listed: System Managers get full access by default
	if "System Manager" in roles:
		return "all"
	return None


def user_can_query_doctype(user: str, doctype: str) -> bool:
	if doctype in SYSTEM_DENYLIST:
		return False
	mode = get_access_mode(user)
	if mode == "all":
		return True
	if mode == "role":
		return bool(frappe.has_permission(doctype, ptype="read", user=user))
	return False


def table_to_doctype(table_name: str) -> str | None:
	"""`tabSales Invoice` -> 'Sales Invoice'. Returns None for non-tab tables."""
	if table_name.startswith("tab"):
		return table_name[3:]
	return None


def check_table_allowed(user: str, table_name: str):
	"""Raise PermissionDenied unless the user may query this raw table name."""
	if table_name in RAW_TABLE_DENYLIST:
		raise PermissionDenied(table_name)
	doctype = table_to_doctype(table_name)
	if not doctype:
		raise PermissionDenied(table_name)
	if not user_can_query_doctype(user, doctype):
		raise PermissionDenied(doctype)
