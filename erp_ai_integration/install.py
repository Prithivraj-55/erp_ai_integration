import frappe

AI_CHAT_ROLE = "AI Chat User"


def after_install():
	ensure_role()


def after_migrate():
	ensure_role()
	ensure_provider_default()


def ensure_provider_default():
	"""Sites that installed a pre-provider version have provider = NULL on the
	settings single — backfill so the mandatory field never blocks saves."""
	if frappe.db.exists("DocType", "Claude AI Settings") and not frappe.db.get_single_value(
		"Claude AI Settings", "provider"
	):
		frappe.db.set_single_value("Claude AI Settings", "provider", "Claude")
		frappe.db.commit()


def ensure_role():
	"""Create the AI Chat User role (idempotent — runs on every install/migrate
	so the role exists on every site this app ships to)."""
	if not frappe.db.exists("Role", AI_CHAT_ROLE):
		frappe.get_doc({
			"doctype": "Role",
			"role_name": AI_CHAT_ROLE,
			"desk_access": 1,
		}).insert(ignore_permissions=True)
		frappe.db.commit()
