// AI Chat — custom desk page (plan doc §7). Plain ES6, no build step.

frappe.pages["ai-chat"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AI Chat"),
		single_column: true,
	});
	new AIChatUI(wrapper);
};

const API = "erp_ai_integration.api.chat";

class AIChatUI {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.$main = $(wrapper).find(".layout-main-section");
		this.chats = [];
		this.current_chat = null;
		this.sending = false;
		this.inject_css();
		this.render_layout();
		this.load_chats();
	}

	// ---------- layout ----------

	render_layout() {
		this.$main.html(`
			<div class="aichat">
				<div class="aichat-sidebar">
					<div class="aichat-sidebar-head">
						<button class="btn btn-primary btn-sm aichat-new">${__("New Chat")}</button>
						<input type="search" class="form-control input-sm aichat-search"
							placeholder="${__("Search chats…")}">
					</div>
					<div class="aichat-list"></div>
				</div>
				<div class="aichat-mainpanel">
					<div class="aichat-topbar">
						<button class="btn btn-default btn-sm aichat-toggle-sidebar">☰</button>
						<span class="aichat-current-title text-muted"></span>
					</div>
					<div class="aichat-thread"></div>
					<div class="aichat-inputbar">
						<textarea class="form-control aichat-input" rows="2"
							placeholder="${__("Ask a question about your ERP data… (Enter to send, Shift+Enter for a new line)")}"></textarea>
						<button class="btn btn-primary aichat-send">${__("Send")}</button>
					</div>
				</div>
			</div>
		`);

		this.$list = this.$main.find(".aichat-list");
		this.$thread = this.$main.find(".aichat-thread");
		this.$input = this.$main.find(".aichat-input");
		this.$send = this.$main.find(".aichat-send");
		this.$title = this.$main.find(".aichat-current-title");

		this.$main.find(".aichat-new").on("click", () => this.new_chat());
		this.$send.on("click", () => this.send());
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send();
			}
		});
		this.$main.find(".aichat-search").on("input", (e) => this.filter_chats(e.target.value));
		this.$main.find(".aichat-toggle-sidebar").on("click", () =>
			this.$main.find(".aichat-sidebar").toggleClass("open")
		);
	}

	// ---------- data ----------

	async load_chats() {
		try {
			const r = await frappe.call(`${API}.get_chats`);
			this.chats = r.message || [];
			this.render_chat_list();
			if (this.chats.length) {
				this.select_chat(this.chats[0].name);
			} else {
				this.render_empty_state();
			}
		} catch (e) {
			this.$thread.html(
				`<div class="aichat-blocked">${__(
					"AI Chat is not available. Please contact your Administrator."
				)}</div>`
			);
			this.$input.prop("disabled", true);
			this.$send.prop("disabled", true);
		}
	}

	async new_chat() {
		const r = await frappe.call(`${API}.create_chat`);
		this.chats.unshift({
			name: r.message.name,
			title: r.message.title,
			last_message_on: frappe.datetime.now_datetime(),
		});
		this.render_chat_list();
		this.select_chat(r.message.name);
	}

	async select_chat(name) {
		this.current_chat = name;
		this.$list.find(".aichat-item").removeClass("active");
		this.$list.find(`[data-chat="${name}"]`).addClass("active");
		const chat = this.chats.find((c) => c.name === name);
		this.$title.text(chat ? chat.title : "");
		this.$main.find(".aichat-sidebar").removeClass("open");

		this.$thread.html(`<div class="text-muted aichat-loading">${__("Loading…")}</div>`);
		const r = await frappe.call({ method: `${API}.get_messages`, args: { chat: name } });
		this.$thread.empty();
		const messages = r.message || [];
		if (!messages.length) {
			this.render_empty_state(true);
		} else {
			messages.forEach((m) => this.append_message(m.role, m.content, m));
		}
		this.scroll_down();
		this.$input.trigger("focus");
	}

	// ---------- sidebar ----------

	render_chat_list() {
		this.$list.empty();
		this.chats.forEach((chat) => {
			const $item = $(`
				<div class="aichat-item" data-chat="${chat.name}">
					<div class="aichat-item-body">
						<div class="aichat-item-title">${frappe.utils.escape_html(chat.title || __("New Chat"))}</div>
						<div class="aichat-item-time text-muted">${
							chat.last_message_on ? frappe.datetime.comment_when(chat.last_message_on) : ""
						}</div>
					</div>
					<button class="btn btn-xs aichat-item-menu">⋮</button>
				</div>
			`);
			$item.on("click", () => this.select_chat(chat.name));
			$item.find(".aichat-item-menu").on("click", (e) => {
				e.stopPropagation();
				this.show_chat_menu(chat);
			});
			this.$list.append($item);
		});
	}

	filter_chats(text) {
		const query = (text || "").toLowerCase();
		this.$list.find(".aichat-item").each(function () {
			const title = $(this).find(".aichat-item-title").text().toLowerCase();
			$(this).toggle(title.includes(query));
		});
	}

	show_chat_menu(chat) {
		const me = this;
		const d = new frappe.ui.Dialog({
			title: frappe.utils.escape_html(chat.title || __("Chat")),
			fields: [
				{ fieldtype: "Data", fieldname: "title", label: __("Rename to"), default: chat.title },
			],
			primary_action_label: __("Rename"),
			primary_action(values) {
				frappe
					.call({ method: `${API}.rename_chat`, args: { chat: chat.name, title: values.title } })
					.then(() => {
						chat.title = values.title;
						me.render_chat_list();
						if (me.current_chat === chat.name) me.$title.text(values.title);
						d.hide();
					});
			},
			secondary_action_label: __("Archive"),
			secondary_action() {
				frappe.call({ method: `${API}.archive_chat`, args: { chat: chat.name } }).then(() => {
					me.chats = me.chats.filter((c) => c.name !== chat.name);
					me.render_chat_list();
					d.hide();
					if (me.current_chat === chat.name) {
						me.current_chat = null;
						me.chats.length ? me.select_chat(me.chats[0].name) : me.render_empty_state();
					}
				});
			},
		});
		d.add_custom_action(__("Delete"), () => {
			frappe.confirm(__("Delete this chat and all its messages?"), () => {
				frappe.call({ method: `${API}.delete_chat`, args: { chat: chat.name } }).then(() => {
					me.chats = me.chats.filter((c) => c.name !== chat.name);
					me.render_chat_list();
					d.hide();
					if (me.current_chat === chat.name) {
						me.current_chat = null;
						me.chats.length ? me.select_chat(me.chats[0].name) : me.render_empty_state();
					}
				});
			});
		}, "btn-danger");
		d.show();
	}

	// ---------- thread ----------

	render_empty_state(keep_chat) {
		if (!keep_chat) this.$title.text("");
		const starters = [
			__("How many sales invoices were created today?"),
			__("Top 5 customers by sales this month"),
			__("How many new customers in the last week?"),
			__("Which items are low on stock?"),
		];
		const $empty = $(`
			<div class="aichat-empty">
				<div class="aichat-empty-icon">💬</div>
				<div class="aichat-empty-title">${__("Ask anything about your ERP data")}</div>
				<div class="aichat-starters"></div>
			</div>
		`);
		const $starters = $empty.find(".aichat-starters");
		starters.forEach((s) => {
			$(`<button class="btn btn-default btn-sm aichat-starter">${s}</button>`)
				.on("click", () => {
					this.$input.val(s);
					this.send();
				})
				.appendTo($starters);
		});
		this.$thread.html($empty);
	}

	append_message(role, content, meta = {}) {
		this.$thread.find(".aichat-empty").remove();
		if (role === "system_note") {
			this.$thread.append(
				`<div class="aichat-note text-muted">${frappe.utils.escape_html(content || "")}</div>`
			);
			return;
		}
		const is_user = role === "user";
		const body = is_user
			? frappe.utils.escape_html(content || "").replace(/\n/g, "<br>")
			: frappe.markdown(content || "");
		const $msg = $(`
			<div class="aichat-msg ${is_user ? "aichat-msg-user" : "aichat-msg-ai"}">
				<div class="aichat-bubble">${body}</div>
			</div>
		`);
		if (!is_user && meta.generated_sql) {
			$msg.find(".aichat-bubble").append(`
				<details class="aichat-sql">
					<summary>${__("View SQL")}</summary>
					<pre>${frappe.utils.escape_html(meta.generated_sql)}</pre>
				</details>
			`);
		}
		if (!is_user && (meta.message || meta.name)) {
			this.render_feedback(
				$msg.find(".aichat-bubble"),
				meta.message || meta.name,
				meta.feedback || ""
			);
		}
		this.$thread.append($msg);
	}

	render_feedback($bubble, message_name, current) {
		const $fb = $(`
			<div class="aichat-feedback">
				<button class="aichat-fb-btn aichat-fb-up" title="${__("Good answer")}">👍</button>
				<button class="aichat-fb-btn aichat-fb-down" title="${__("Bad answer")}">👎</button>
			</div>
		`);
		const mark_active = (value) => {
			$fb.find(".aichat-fb-up").toggleClass("active", value === "Up");
			$fb.find(".aichat-fb-down").toggleClass("active", value === "Down");
		};
		mark_active(current);

		const toggle = (value) => {
			const next = current === value ? "" : value; // click again to clear
			frappe
				.call({
					method: `${API}.set_message_feedback`,
					args: { message: message_name, feedback: next },
				})
				.then(() => {
					current = next;
					mark_active(current);
				});
		};
		$fb.find(".aichat-fb-up").on("click", () => toggle("Up"));
		$fb.find(".aichat-fb-down").on("click", () => toggle("Down"));
		$bubble.append($fb);
	}

	show_thinking() {
		this.$thread.append(`
			<div class="aichat-msg aichat-msg-ai aichat-thinking">
				<div class="aichat-bubble text-muted">${__("Thinking…")}</div>
			</div>
		`);
		this.scroll_down();
	}

	show_error(text, retry_text) {
		const $err = $(`
			<div class="aichat-msg aichat-msg-ai">
				<div class="aichat-bubble aichat-error">
					${frappe.utils.escape_html(text)}
					<div><button class="btn btn-xs btn-default aichat-retry">${__("Retry")}</button></div>
				</div>
			</div>
		`);
		$err.find(".aichat-retry").on("click", () => {
			$err.remove();
			this.$input.val(retry_text);
			this.send();
		});
		this.$thread.append($err);
		this.scroll_down();
	}

	scroll_down() {
		this.$thread.scrollTop(this.$thread[0].scrollHeight);
	}

	// ---------- send ----------

	async send() {
		if (this.sending) return;
		const text = (this.$input.val() || "").trim();
		if (!text) return;

		if (!this.current_chat) {
			await this.new_chat();
		}

		this.sending = true;
		this.$input.val("").prop("disabled", true);
		this.$send.prop("disabled", true);
		this.append_message("user", text);
		this.show_thinking();

		try {
			const r = await frappe.call({
				method: `${API}.send_message`,
				args: { chat: this.current_chat, message: text },
			});
			this.$thread.find(".aichat-thinking").remove();
			const res = r.message || {};
			this.append_message("assistant", res.answer, {
				generated_sql: res.generated_sql,
				message: res.message_name,
			});

			const chat = this.chats.find((c) => c.name === this.current_chat);
			if (chat) {
				chat.last_message_on = frappe.datetime.now_datetime();
				if (res.chat_title) {
					chat.title = res.chat_title;
					this.$title.text(res.chat_title);
				}
				this.chats = [chat, ...this.chats.filter((c) => c.name !== chat.name)];
				this.render_chat_list();
				this.$list.find(`[data-chat="${chat.name}"]`).addClass("active");
			}
		} catch (e) {
			this.$thread.find(".aichat-thinking").remove();
			const server_msg =
				(e && e._server_messages && JSON.parse(JSON.parse(e._server_messages)[0]).message) ||
				__("The request failed. Please try again.");
			this.show_error(frappe.utils.strip_html(server_msg), text);
		} finally {
			this.sending = false;
			this.$input.prop("disabled", false).trigger("focus");
			this.$send.prop("disabled", false);
			this.scroll_down();
		}
	}

	// ---------- css ----------

	inject_css() {
		if (document.getElementById("aichat-css")) return;
		const css = `
		.aichat { display: flex; height: calc(100vh - 140px); border: 1px solid var(--border-color); border-radius: var(--border-radius-md); overflow: hidden; background: var(--card-bg); }
		.aichat-sidebar { width: 280px; min-width: 280px; border-right: 1px solid var(--border-color); display: flex; flex-direction: column; background: var(--subtle-fg, var(--fg-color)); }
		.aichat-sidebar-head { padding: 10px; display: flex; flex-direction: column; gap: 8px; border-bottom: 1px solid var(--border-color); }
		.aichat-list { overflow-y: auto; flex: 1; }
		.aichat-item { display: flex; align-items: center; padding: 8px 10px; cursor: pointer; border-bottom: 1px solid var(--border-color); }
		.aichat-item:hover { background: var(--bg-light-gray, var(--control-bg)); }
		.aichat-item.active { background: var(--control-bg); }
		.aichat-item-body { flex: 1; min-width: 0; }
		.aichat-item-title { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.aichat-item-time { font-size: 11px; }
		.aichat-item-menu { visibility: hidden; }
		.aichat-item:hover .aichat-item-menu { visibility: visible; }
		.aichat-mainpanel { flex: 1; display: flex; flex-direction: column; min-width: 0; }
		.aichat-topbar { padding: 8px 12px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; gap: 10px; }
		.aichat-toggle-sidebar { display: none; }
		.aichat-thread { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
		.aichat-msg { display: flex; }
		.aichat-msg-user { justify-content: flex-end; }
		.aichat-msg-ai { justify-content: flex-start; }
		.aichat-bubble { max-width: 78%; padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.5; }
		.aichat-msg-user .aichat-bubble { background: var(--primary); color: #fff; border-bottom-right-radius: 4px; }
		.aichat-msg-ai .aichat-bubble { background: var(--control-bg); border-bottom-left-radius: 4px; }
		.aichat-msg-ai .aichat-bubble table { border-collapse: collapse; margin: 6px 0; }
		.aichat-msg-ai .aichat-bubble th, .aichat-msg-ai .aichat-bubble td { border: 1px solid var(--border-color); padding: 4px 8px; font-size: 12px; }
		.aichat-sql { margin-top: 8px; font-size: 12px; }
		.aichat-sql summary { cursor: pointer; color: var(--text-muted); }
		.aichat-sql pre { margin: 6px 0 0; padding: 8px; background: var(--bg-color); border-radius: 6px; white-space: pre-wrap; font-size: 11px; }
		.aichat-feedback { margin-top: 6px; display: flex; gap: 4px; }
		.aichat-fb-btn { background: none; border: none; cursor: pointer; font-size: 13px; opacity: .45; padding: 2px 4px; border-radius: 4px; line-height: 1; }
		.aichat-fb-btn:hover { opacity: .8; background: var(--bg-color); }
		.aichat-fb-btn.active { opacity: 1; background: var(--bg-color); }
		.aichat-error { background: var(--bg-red, #fceae9) !important; color: var(--text-color); }
		.aichat-note { text-align: center; font-size: 12px; }
		.aichat-inputbar { display: flex; gap: 8px; padding: 10px; border-top: 1px solid var(--border-color); }
		.aichat-input { resize: none; }
		.aichat-empty { margin: auto; text-align: center; padding: 24px; }
		.aichat-empty-icon { font-size: 34px; }
		.aichat-empty-title { font-size: 15px; margin: 8px 0 16px; color: var(--text-muted); }
		.aichat-starters { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; max-width: 460px; }
		.aichat-blocked { margin: auto; color: var(--text-muted); }
		@media (max-width: 768px) {
			.aichat-sidebar { position: absolute; z-index: 5; height: 100%; left: -290px; transition: left .2s; }
			.aichat-sidebar.open { left: 0; }
			.aichat-toggle-sidebar { display: inline-block; }
			.aichat { position: relative; }
			.aichat-bubble { max-width: 92%; }
		}
		`;
		const style = document.createElement("style");
		style.id = "aichat-css";
		style.textContent = css;
		document.head.appendChild(style);
	}
}
