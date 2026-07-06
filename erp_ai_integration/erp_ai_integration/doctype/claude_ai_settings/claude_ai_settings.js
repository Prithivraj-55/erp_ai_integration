// Copyright (c) 2026, Craft and contributors
// For license information, please see license.txt

frappe.ui.form.on("Claude AI Settings", {
	refresh(frm) {
		add_api_buttons(frm);
		add_db_user_buttons(frm);
		add_budget_indicator(frm);
	},
});

function add_budget_indicator(frm) {
	frappe.call("erp_ai_integration.api.settings.get_budget_status").then((r) => {
		const res = r.message || {};
		let label, color;
		if (res.percent === null || res.percent === undefined) {
			label = __("This month: {0} tokens used (no monthly budget set)", [
				format_number(res.used),
			]);
			color = "blue";
		} else {
			label = __("Monthly budget: {0}% used ({1} / {2} tokens)", [
				res.percent,
				format_number(res.used),
				format_number(res.budget),
			]);
			color = res.percent >= 90 ? "red" : res.percent >= 70 ? "orange" : "green";
		}
		frm.dashboard.add_indicator(label, color);
	});
}

function format_number(n) {
	return (n || 0).toLocaleString();
}

function add_api_buttons(frm) {
	frm.add_custom_button(__("Test Connection"), () => {
		frappe.show_alert({ message: __("Testing connection..."), indicator: "blue" });
		frappe
			.call("erp_ai_integration.api.settings.test_connection")
			.then((r) => {
				const res = r.message || {};
				if (res.success) {
					frappe.show_alert({
						message: __("Connected — {0}: {1}", [res.provider, res.model]),
						indicator: "green",
					});
				} else {
					frappe.msgprint({
						title: __("Connection Failed"),
						indicator: "red",
						message: frappe.utils.escape_html(res.error || __("Unknown error")),
					});
				}
				frm.reload_doc();
			});
	}, __("AI Provider"));
}

function add_db_user_buttons(frm) {
	const group = __("Database User");

	if (!frm.doc.db_user_created) {
		frm.add_custom_button(__("Create Read-Only DB User"), () => create_db_user_dialog(frm), group);
		frm.add_custom_button(__("Manual Setup / Enter Credentials"), () => manual_setup_dialog(frm), group);
	} else {
		frm.add_custom_button(__("Verify Read-Only Connection"), () => {
			frappe.call("erp_ai_integration.api.settings.verify_readonly_user").then((r) => {
				const res = r.message || {};
				if (res.success) {
					frappe.msgprint({
						title: __("Verified"),
						indicator: "green",
						message:
							__("Connection OK and user is SELECT-only.") +
							"<br><pre>" +
							frappe.utils.escape_html((res.grants || []).join("\n")) +
							"</pre>",
					});
				} else {
					frappe.msgprint({
						title: __("Verification Failed"),
						indicator: "red",
						message: frappe.utils.escape_html(res.error || ""),
					});
				}
			});
		}, group);

		frm.add_custom_button(__("Drop & Recreate DB User"), () => drop_db_user_dialog(frm), group);
	}
}

function create_db_user_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Create Read-Only DB User"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"Enter your database admin credentials (root on self-managed MariaDB, or the master user on managed databases like AWS RDS). They are used once for this operation and never stored."
				)}</p>`,
			},
			{
				label: __("DB Admin Username"),
				fieldname: "admin_user",
				fieldtype: "Data",
				default: "root",
				reqd: 1,
			},
			{
				label: __("DB Admin Password"),
				fieldname: "admin_password",
				fieldtype: "Password",
				reqd: 1,
			},
		],
		primary_action_label: __("Create User"),
		primary_action(values) {
			d.get_primary_btn().prop("disabled", true);
			frappe
				.call("erp_ai_integration.api.settings.create_readonly_db_user", {
					admin_user: values.admin_user,
					admin_password: values.admin_password,
				})
				.then((r) => {
					const res = r.message || {};
					d.hide();
					if (res.success) {
						frappe.msgprint({
							title: __("Read-Only User Created"),
							indicator: "green",
							message: __("User {0} created with SELECT-only access.", [
								frappe.utils.escape_html(res.username),
							]),
						});
						frm.reload_doc();
					} else {
						show_manual_fallback(frm, res);
					}
				})
				.catch(() => d.get_primary_btn().prop("disabled", false));
		},
	});
	d.show();
}

function show_manual_fallback(frm, res) {
	// Auto-creation failed (e.g. RDS / restricted master user). Show the exact
	// error + ready-to-run SQL, then let the admin paste the credentials back.
	const d = new frappe.ui.Dialog({
		title: __("Automatic Creation Failed — Manual Steps"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				options: `
					<div class="alert alert-warning">${frappe.utils.escape_html(res.error || "")}</div>
					<p>${__(
						"Your database did not allow automatic user creation (common on AWS RDS and other managed databases). Run the SQL below on your database server using a client that has admin access, then click <b>I ran the SQL — Save Credentials</b>."
					)}</p>
					<pre style="white-space:pre-wrap">${frappe.utils.escape_html(res.manual_sql || "")}</pre>
					<p class="text-muted">${__(
						"The username and password below match the SQL above. If you change them in the SQL, change them here too."
					)}</p>`,
			},
			{
				label: __("Read-Only Username"),
				fieldname: "username",
				fieldtype: "Data",
				default: res.username,
				reqd: 1,
			},
			{
				label: __("Read-Only Password"),
				fieldname: "password",
				fieldtype: "Data",
				default: res.password,
				reqd: 1,
			},
		],
		primary_action_label: __("I ran the SQL — Save Credentials"),
		primary_action(values) {
			save_manual_credentials(frm, d, values.username, values.password);
		},
	});
	d.show();
}

function manual_setup_dialog(frm) {
	frappe.call("erp_ai_integration.api.settings.get_manual_setup_sql").then((r) => {
		const res = r.message || {};
		const d = new frappe.ui.Dialog({
			title: __("Manual Read-Only User Setup"),
			size: "large",
			fields: [
				{
					fieldtype: "HTML",
					options: `
						<p>${__(
							"If your database does not allow user creation from this server (e.g. AWS RDS or another managed database), run this SQL with your DB admin tool, then save the credentials below. If you already created a read-only user yourself, just enter its credentials."
						)}</p>
						<pre style="white-space:pre-wrap">${frappe.utils.escape_html(res.sql || "")}</pre>`,
				},
				{
					label: __("Read-Only Username"),
					fieldname: "username",
					fieldtype: "Data",
					default: res.username,
					reqd: 1,
				},
				{
					label: __("Read-Only Password"),
					fieldname: "password",
					fieldtype: "Data",
					default: res.password,
					reqd: 1,
				},
			],
			primary_action_label: __("Verify & Save Credentials"),
			primary_action(values) {
				save_manual_credentials(frm, d, values.username, values.password);
			},
		});
		d.show();
	});
}

function save_manual_credentials(frm, dialog, username, password) {
	frappe
		.call("erp_ai_integration.api.settings.set_manual_db_user", {
			username: username,
			password: password,
		})
		.then((r) => {
			const res = r.message || {};
			if (res.success) {
				dialog.hide();
				frappe.msgprint({
					title: __("Credentials Verified & Saved"),
					indicator: "green",
					message: __("Connection OK and user is SELECT-only."),
				});
				frm.reload_doc();
			} else {
				frappe.msgprint({
					title: __("Verification Failed"),
					indicator: "red",
					message: frappe.utils.escape_html(res.error || ""),
				});
			}
		});
}

function drop_db_user_dialog(frm) {
	frappe.confirm(
		__(
			"This will drop the current read-only DB user. AI chat will stop working until a new user is created. Continue?"
		),
		() => {
			const d = new frappe.ui.Dialog({
				title: __("Drop Read-Only DB User"),
				fields: [
					{
						label: __("DB Admin Username"),
						fieldname: "admin_user",
						fieldtype: "Data",
						default: "root",
						reqd: 1,
					},
					{
						label: __("DB Admin Password"),
						fieldname: "admin_password",
						fieldtype: "Password",
						reqd: 1,
					},
				],
				primary_action_label: __("Drop User"),
				primary_action(values) {
					frappe
						.call("erp_ai_integration.api.settings.drop_readonly_db_user", {
							admin_user: values.admin_user,
							admin_password: values.admin_password,
						})
						.then((r) => {
							const res = r.message || {};
							d.hide();
							if (res.success) {
								frappe.show_alert({
									message: __("Read-only user dropped."),
									indicator: "orange",
								});
								frm.reload_doc();
							} else {
								frappe.msgprint({
									title: __("Failed"),
									indicator: "red",
									message: frappe.utils.escape_html(res.error || ""),
								});
							}
						});
				},
			});
			d.show();
		}
	);
}
