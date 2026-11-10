// Neotec AI desk assistant (Frappe v15+)
frappe.provide("neotec.ai");

neotec.ai.history = [];
neotec.ai.config = null;

$(document).on("app_ready", () => neotec.ai.init());

neotec.ai.init = function () {
	if (neotec.ai._initialised || frappe.session.user === "Guest") return;
	neotec.ai._initialised = true;

	frappe.call({
		method: "neotec_ai.api.get_client_settings",
		callback(r) {
			neotec.ai.config = r.message || { enabled: false };
			if (!neotec.ai.config.enabled) return;
			neotec.ai.add_navbar_button();
			frappe.ui.keys.add_shortcut({
				shortcut: "alt+k",
				action: () => neotec.ai.open(),
				description: __("Open {0}", [neotec.ai.config.assistant_name]),
				ignore_inputs: true,
			});
		},
	});
};

neotec.ai.add_navbar_button = function () {
	if ($(".neotec-ai-trigger").length) return;
	const name = frappe.utils.escape_html(neotec.ai.config.assistant_name);
	const $item = $(`
		<li class="nav-item neotec-ai-nav">
			<a class="nav-link neotec-ai-trigger" href="#" title="${name} (Alt+K)">
				<span class="neotec-dot"></span><span class="neotec-ai-label">${name}</span>
			</a>
		</li>`);
	let $nav = $("header.navbar .navbar-collapse .navbar-nav").first();
	if (!$nav.length) $nav = $("header.navbar .navbar-nav").last();
	if (!$nav.length) return;
	$nav.prepend($item);
	$item.on("click", "a", (e) => {
		e.preventDefault();
		neotec.ai.open();
	});
};

// What the user is looking at: a record, a DocType list/report, or a module workspace.
neotec.ai.current_context = function () {
	const route = frappe.get_route() || [];
	const view = route[0];
	if (view === "Form" && window.cur_frm && cur_frm.doctype === route[1]) {
		return cur_frm.is_new() ? { doctype: cur_frm.doctype } : { doctype: cur_frm.doctype, docname: cur_frm.docname };
	}
	if (["List", "Report", "Tree", "Kanban", "Dashboard", "Calendar", "Gantt", "Image"].includes(view) && route[1]) {
		return { doctype: route[1] };
	}
	if (view === "Workspaces" && route[1]) {
		return { workspace: route[route.length - 1] };
	}
	return {};
};

// ------------------------------------------------------------------ dialog

neotec.ai.conversation = null;
neotec.ai.project = null;

neotec.ai.open = function () {
	const cfg = neotec.ai.config || {};
	const ctx = neotec.ai.current_context();
	const esc = frappe.utils.escape_html;

	if (neotec.ai.dialog) {
		const changed = JSON.stringify(ctx) !== JSON.stringify(neotec.ai.dialog.ctx);
		neotec.ai.dialog.ctx = ctx;
		neotec.ai.render_context();
		if (changed) neotec.ai.load_suggestions();
		neotec.ai.load_needs_you();
		neotec.ai.dialog.show();
		return;
	}

	const d = new frappe.ui.Dialog({
		title: esc(cfg.assistant_name || "Neotec AI"),
		size: "extra-large",
		fields: [
			{ fieldname: "context_html", fieldtype: "HTML" },
			{ fieldname: "history_html", fieldtype: "HTML" },
			{ fieldname: "thread_html", fieldtype: "HTML" },
			{ fieldname: "suggest_html", fieldtype: "HTML" },
			{
				fieldname: "prompt",
				fieldtype: "Small Text",
				label: __("Your question"),
				placeholder: __("e.g. Profit and loss this year by month, or which invoices are overdue? (Ctrl+Enter to send)"),
			},
		],
		primary_action_label: __("Send"),
		primary_action: () => neotec.ai.send(),
		secondary_action_label: __("New Chat"),
		secondary_action: () => neotec.ai.new_chat(),
	});
	d.ctx = ctx;
	d.$wrapper.addClass("neotec-modal");
	neotec.ai.dialog = d;

	d.fields_dict.history_html.$wrapper.html(`<div class="neotec-history" style="display:none"></div>`);
	d.fields_dict.thread_html.$wrapper.html(`<div class="neotec-thread"></div>`);
	d.fields_dict.suggest_html.$wrapper.html(`<div class="neotec-needs"></div><div class="neotec-suggest"></div>`);
	d.fields_dict.prompt.$input.css("min-height", "70px").on("keydown", (e) => {
		if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
			e.preventDefault();
			neotec.ai.send();
		}
	});

	neotec.ai.load_projects();
	neotec.ai.render_thread();
	neotec.ai.load_suggestions();
	neotec.ai.load_needs_you();
	d.show();
	setTimeout(() => d.fields_dict.prompt.$input.trigger("focus"), 200);
};

neotec.ai.new_chat = function () {
	neotec.ai.conversation = null;
	neotec.ai.history = [];
	neotec.ai._suggest_open = false;
	neotec.ai.render_context();
	neotec.ai.render_thread();
	neotec.ai.load_suggestions();
	neotec.ai.load_needs_you();
};

neotec.ai.render_context = function () {
	const d = neotec.ai.dialog;
	const cfg = neotec.ai.config || {};
	const esc = frappe.utils.escape_html;
	const ctx = d.ctx || {};
	let where = __("General");
	if (ctx.docname && cfg.doc_context) where = `${esc(__(ctx.doctype))}: <b>${esc(ctx.docname)}</b>`;
	else if (ctx.doctype) where = esc(__(ctx.doctype));
	else if (ctx.workspace) where = esc(__(ctx.workspace));
	const projects = neotec.ai.projects || [];
	const proj_opts = [`<option value="">${__("No project")}</option>`]
		.concat(projects.map((p) => `<option value="${esc(p.name)}" ${neotec.ai.project === p.name ? "selected" : ""}>${esc(p.title)}</option>`))
		.concat([`<option value="__new">${__("+ New project…")}</option>`])
		.concat(neotec.ai.project ? [`<option value="__edit">${__("Edit this project…")}</option>`] : [])
		.join("");
	d.fields_dict.context_html.$wrapper.html(`
		<div class="neotec-context">
			<span class="neotec-context-left">
				<a class="neotec-link neotec-history-toggle">☰ ${__("History")}</a>
				<select class="neotec-project" title="${__("Project: shared instructions for related chats")}">${proj_opts}</select>
				<span>${__("Context")}: ${where}</span>
			</span>
			<span>
				<a href="/app/neotec-bi" class="neotec-link">${__("BI Builder")}</a>
				· <a href="/app/neotec-dashboard" class="neotec-link">${__("Dashboards")}</a>
				· <a href="/app/neotec-ai-report" class="neotec-link">${__("Saved reports")}</a>
			</span>
		</div>`);
	const $c = d.fields_dict.context_html.$wrapper;
	$c.find(".neotec-history-toggle").on("click", () => neotec.ai.toggle_history());
	$c.find(".neotec-project").on("change", function () {
		const v = $(this).val();
		if (v === "__new") return neotec.ai.edit_project();
		if (v === "__edit") return neotec.ai.edit_project(neotec.ai.project);
		neotec.ai.project = v || null;
		if (neotec.ai.conversation) {
			frappe.call({ method: "neotec_ai.conversations.update_conversation", type: "POST", args: { name: neotec.ai.conversation, project: v || "" } });
		}
		neotec.ai.render_context();
		if ($(".neotec-history:visible").length) neotec.ai.load_history();
	});
};

// ------------------------------------------------------------------ projects

neotec.ai.load_projects = function () {
	frappe.call({ method: "neotec_ai.conversations.list_projects" }).then((r) => {
		neotec.ai.projects = r.message || [];
		neotec.ai.render_context();
	});
};

neotec.ai.edit_project = function (name) {
	const p = (neotec.ai.projects || []).find((x) => x.name === name) || {};
	const d = new frappe.ui.Dialog({
		title: name ? __("Edit Project") : __("New Project"),
		fields: [
			{ fieldname: "title", fieldtype: "Data", label: __("Title"), reqd: 1, default: p.title },
			{ fieldname: "instructions", fieldtype: "Small Text", label: __("Instructions for the AI"), default: p.instructions,
				description: __("Added to every chat in this project, e.g. 'Focus on the Riyadh branch; show amounts in SAR thousands; compare with last year.'") },
		],
		primary_action_label: __("Save"),
		primary_action(v) {
			frappe.call({ method: "neotec_ai.conversations.save_project", type: "POST", args: { ...v, name: name || null } }).then((r) => {
				d.hide();
				neotec.ai.project = r.message.name;
				neotec.ai.load_projects();
			});
		},
		secondary_action_label: name ? __("Delete") : null,
		secondary_action: name
			? () => frappe.confirm(__("Delete this project? Its chats are kept."), () =>
				frappe.call({ method: "neotec_ai.conversations.delete_project", type: "POST", args: { name } }).then(() => {
					d.hide();
					neotec.ai.project = null;
					neotec.ai.load_projects();
				}))
			: null,
	});
	d.show();
	d.$wrapper.on("hidden.bs.modal", () => neotec.ai.render_context());
};

// ------------------------------------------------------------------ history

neotec.ai.toggle_history = function () {
	const $h = neotec.ai.dialog.$wrapper.find(".neotec-history");
	if ($h.is(":visible")) return $h.hide();
	$h.show();
	neotec.ai.load_history();
};

neotec.ai.load_history = function (search) {
	const $h = neotec.ai.dialog.$wrapper.find(".neotec-history");
	const esc = frappe.utils.escape_html;
	frappe.call({
		method: "neotec_ai.conversations.list_conversations",
		args: { project: neotec.ai.project || null, search: search || null },
	}).then((r) => {
		const rows = r.message || [];
		$h.html(`
			<div class="neotec-history-head">
				<input class="form-control form-control-sm neotec-history-search" placeholder="${__("Search chats")}" value="${esc(search || "")}">
			</div>
			<div class="neotec-history-list">${rows.length ? rows.map((c) => `
				<div class="neotec-history-row ${c.name === neotec.ai.conversation ? "active" : ""}" data-name="${esc(c.name)}">
					<a class="neotec-history-open">${c.pinned ? "★ " : ""}${esc(c.title)}</a>
					<span class="neotec-history-meta">${frappe.datetime.comment_when ? frappe.datetime.comment_when(c.last_activity) : esc(c.last_activity || "")}</span>
					<span class="neotec-history-tools">
						<a data-act="pin" title="${__("Pin")}">${c.pinned ? "☆" : "★"}</a>
						<a data-act="rename" title="${__("Rename")}">✎</a>
						<a data-act="delete" title="${__("Delete")}">✕</a>
					</span>
				</div>`).join("") : `<div class="neotec-empty">${__("No saved chats yet.")}</div>`}</div>`);
		let t;
		$h.find(".neotec-history-search").on("input", function () {
			clearTimeout(t);
			const v = $(this).val();
			t = setTimeout(() => neotec.ai.load_history(v), 350);
		});
		$h.find(".neotec-history-open").on("click", function () {
			neotec.ai.load_conversation($(this).closest(".neotec-history-row").attr("data-name"));
		});
		$h.find("[data-act]").on("click", function () {
			const name = $(this).closest(".neotec-history-row").attr("data-name");
			const row = rows.find((x) => x.name === name);
			const act = $(this).attr("data-act");
			if (act === "delete") {
				return frappe.confirm(__("Delete this chat?"), () =>
					frappe.call({ method: "neotec_ai.conversations.delete_conversation", type: "POST", args: { name } }).then(() => {
						if (neotec.ai.conversation === name) neotec.ai.new_chat();
						neotec.ai.load_history(search);
					}));
			}
			if (act === "rename") {
				return frappe.prompt({ fieldname: "title", fieldtype: "Data", label: __("Title"), reqd: 1, default: row.title }, (v) =>
					frappe.call({ method: "neotec_ai.conversations.update_conversation", type: "POST", args: { name, title: v.title } })
						.then(() => neotec.ai.load_history(search)), __("Rename Chat"));
			}
			if (act === "pin") {
				frappe.call({ method: "neotec_ai.conversations.update_conversation", type: "POST", args: { name, pinned: row.pinned ? 0 : 1 } })
					.then(() => neotec.ai.load_history(search));
			}
		});
	});
};

neotec.ai.load_conversation = function (name) {
	frappe.call({ method: "neotec_ai.conversations.get_conversation", args: { name } }).then((r) => {
		const c = r.message;
		if (!c) return;
		neotec.ai.conversation = c.name;
		neotec.ai.project = c.project || null;
		neotec.ai.history = c.messages.map((m) => ({
			role: m.role,
			content: m.content,
			display: m.display,
			saved_reports: m.saved_reports || [],
			meta: m.meta ? frappe.utils.escape_html(m.meta) : "",
		}));
		neotec.ai.dialog.$wrapper.find(".neotec-history").hide();
		neotec.ai.render_context();
		neotec.ai.render_thread();
		neotec.ai.render_suggestions();
	});
};

// ------------------------------------------------------------------ needs you

neotec.ai.load_needs_you = function () {
	const cfg = neotec.ai.config || {};
	const $n = neotec.ai.dialog.$wrapper.find(".neotec-needs");
	if (neotec.ai.history.length) return $n.empty();
	frappe.call({ method: "neotec_ai.api.get_needs_you" }).then((r) => {
		const items = r.message || [];
		if (!items.length || neotec.ai.history.length) return $n.empty();
		const esc = frappe.utils.escape_html;
		$n.html(`<div class="neotec-needs-box"><b>${__("Needs you")}</b>
			${items.map((i) => i.question
				? `<button class="neotec-chip neotec-chip-alert" data-q="${esc(i.question)}">${esc(i.label)}</button>`
				: `<a class="neotec-chip neotec-chip-alert" href="${esc(i.url || "#")}">${esc(i.label)}</a>`).join("")}</div>`);
		$n.find("button[data-q]").on("click", function () {
			neotec.ai.dialog.set_value("prompt", $(this).attr("data-q"));
			neotec.ai.send();
		});
	});
};

// ------------------------------------------------------------------ suggestions

neotec.ai.load_suggestions = function (show_all) {
	const d = neotec.ai.dialog;
	const ctx = d.ctx || {};
	frappe.call({
		method: "neotec_ai.api.get_suggestions",
		args: {
			doctype: ctx.doctype || null,
			docname: (neotec.ai.config.doc_context && ctx.docname) || null,
			workspace: ctx.workspace || null,
			show_all: show_all ? 1 : 0,
		},
		callback(r) {
			neotec.ai.suggestions = r.message || [];
			neotec.ai.render_suggestions(!!show_all);
		},
	});
};

neotec.ai.render_suggestions = function (expanded_all) {
	const d = neotec.ai.dialog;
	const $s = d.$wrapper.find(".neotec-suggest");
	const esc = frappe.utils.escape_html;
	const groups = neotec.ai.suggestions || [];
	if (neotec.ai.history.length) d.$wrapper.find(".neotec-needs").empty();
	if (!groups.length) {
		$s.empty();
		return;
	}
	const collapsed = neotec.ai.history.length > 0 && !neotec.ai._suggest_open;
	let html = `<div class="neotec-suggest-head">
		<a class="neotec-link neotec-suggest-toggle">${collapsed ? "▸" : "▾"} ${__("Suggested questions")}</a>
		${!collapsed && !expanded_all ? `<a class="neotec-link neotec-suggest-more">${__("Show more")}</a>` : ""}
	</div>`;
	if (!collapsed) {
		for (const g of groups) {
			html += `<div class="neotec-suggest-group"><div class="neotec-suggest-label">${esc(g.label)}</div><div class="neotec-chips">`;
			html += g.questions.map((q) => `<button class="neotec-chip" data-q="${esc(q)}">${esc(q)}</button>`).join("");
			html += `</div></div>`;
		}
	}
	$s.html(html);
	$s.find(".neotec-chip").on("click", function () {
		d.set_value("prompt", $(this).attr("data-q"));
		neotec.ai._suggest_open = false;
		neotec.ai.send();
	});
	$s.find(".neotec-suggest-toggle").on("click", () => {
		neotec.ai._suggest_open = collapsed;
		neotec.ai.render_suggestions(expanded_all);
	});
	$s.find(".neotec-suggest-more").on("click", () => neotec.ai.load_suggestions(true));
};

// ------------------------------------------------------------------ thread

neotec.ai.render_thread = function (pending) {
	const $t = neotec.ai.dialog.$wrapper.find(".neotec-thread");
	const esc = frappe.utils.escape_html;
	$t.empty();
	if (!neotec.ai.history.length && !pending) {
		$t.html(`<div class="neotec-empty">${__(
			"Ask about your business: sales, profit, receivables, stock, approvals, or the document you have open. " +
				"Ask for a report or chart and you can view, export and save it. Answers only use data you are allowed to see."
		)}</div>`);
		return;
	}
	for (const m of neotec.ai.history) {
		if (m.role === "user") {
			$t.append(`<div class="neotec-msg neotec-user">${esc(m.display || m.content).replace(/\n/g, "<br>")}</div>`);
			continue;
		}
		const $m = $(`<div class="neotec-msg neotec-bot">${neotec.ai.sanitize(frappe.markdown(m.display || m.content))}</div>`);
		$t.append($m);
		for (const rep of m.reports || []) {
			const $r = $(`<div></div>`).appendTo($m);
			neotec.ai.render_report($r, rep, { prompt: m.prompt });
		}
		for (const saved of m.saved_reports || []) {
			const $r = $(`<div class="neotec-saved-report">
				<span>📊 ${esc(saved.title || __("Report"))}</span>
				<button class="btn btn-xs btn-default">${__("Show (live data)")}</button></div>`).appendTo($m);
			$r.find("button").on("click", () => {
				$r.html(`<span class="text-muted small">${__("Running...")}</span>`);
				frappe.call({ method: "neotec_ai.reports.run_report", args: { definition: JSON.stringify(saved.definition) } }).then((res) => {
					const out = res.message || {};
					if (!out.ok) return neotec.bi.render_message($r, out);
					neotec.ai.render_report($r, out.report, {});
				});
			});
		}
		if (m.meta) $m.append(`<div class="neotec-meta">${m.meta}</div>`);
	}
	if (pending) {
		$t.append(`<div class="neotec-msg neotec-user">${esc(pending).replace(/\n/g, "<br>")}</div>
			<div class="neotec-msg neotec-bot neotec-thinking">${__("Thinking and checking your data...")}</div>`);
	}
	$t.scrollTop($t[0].scrollHeight);
};

neotec.ai.send = function () {
	const d = neotec.ai.dialog;
	if (d._busy) return;
	const prompt = (d.get_value("prompt") || "").trim();
	if (!prompt) return;

	const ctx = d.ctx || {};
	const doc_ctx = neotec.ai.config.doc_context && ctx.docname ? ctx : {};
	d._busy = true;
	d.get_primary_btn().prop("disabled", true);
	d.set_value("prompt", "");
	d.$wrapper.find(".neotec-needs").empty();
	neotec.ai.render_thread(prompt);

	frappe.call({
		method: "neotec_ai.api.chat",
		type: "POST",
		args: {
			prompt,
			doctype: doc_ctx.doctype || null,
			docname: doc_ctx.docname || null,
			conversation: neotec.ai.conversation,
			project: neotec.ai.project,
			// Fallback for when saving the conversation is not possible; the server prefers saved history.
			history: neotec.ai.conversation ? null : JSON.stringify(neotec.ai.history.map(({ role, content }) => ({ role, content }))),
		},
		callback(r) {
			const m = r.message || {};
			if (m.status !== "success") {
				neotec.ai.render_thread();
				neotec.ai.show_error(m.message || __("Something went wrong."));
				d.set_value("prompt", prompt);
				return;
			}
			if (m.conversation) neotec.ai.conversation = m.conversation;
			const reports = m.reports || [];
			const notes = reports
				.map((rep) => `[Report shown: ${rep.title}; definition: ${JSON.stringify({ query: rep.definition.query, erp_report: rep.definition.erp_report, viz: rep.viz })}]`)
				.join("\n");
			neotec.ai.history.push({ role: "user", content: prompt });
			neotec.ai.history.push({
				role: "assistant",
				content: notes ? `${m.reply}\n\n${notes}` : m.reply,
				display: m.reply,
				reports,
				prompt,
				meta: neotec.ai.meta_line(m),
			});
			neotec.ai.render_thread();
			neotec.ai.render_suggestions();
		},
		error() {
			neotec.ai.render_thread();
			d.set_value("prompt", prompt);
		},
		always() {
			d._busy = false;
			d.get_primary_btn().prop("disabled", false);
		},
	});
};

neotec.ai.meta_line = function (m) {
	const esc = frappe.utils.escape_html;
	const parts = [];
	const looked = (m.queries || [])
		.filter((q) => q.doctype)
		.map((q) => (q.error ? `${esc(__(q.doctype))} (✕)` : `${esc(__(q.doctype))} (${q.rows ?? 0})`));
	if (looked.length) parts.push(__("Looked up: {0}", [looked.join(", ")]));
	parts.push(`${(m.latency_ms / 1000).toFixed(1)}s · ${m.tokens} ${__("tokens")}`);
	return parts.join(" · ");
};

neotec.ai.show_error = function (msg) {
	const $t = neotec.ai.dialog.$wrapper.find(".neotec-thread");
	$t.append(`<div class="neotec-msg neotec-error">${frappe.utils.escape_html(msg)}</div>`);
	$t.scrollTop($t[0].scrollHeight);
};

// ------------------------------------------------------------------ reports

/**
 * Interactive report card (chat, saved report form).
 * report: {title, description, columns, rows, viz, pivot, truncated, definition, name?}
 * opts: {saved, full, prompt}
 */
neotec.ai.render_report = function ($wrap, report, opts = {}) {
	const esc = neotec.bi.esc;
	const def = report.definition || {};
	let viz = { ...(report.viz || { type: "table" }) };
	const switchable = ["table", "bar", "line", "area", "pie", "donut", "percentage"];
	const num_cols = report.columns.filter((c) => neotec.bi.NUMERIC.includes(c.fieldtype));
	const can_chart = num_cols.length && report.columns.length > 1;
	const options = (can_chart ? switchable : ["table"]).concat(viz.type === "number" ? ["number"] : []).concat(viz.type === "pivot" ? ["pivot"] : []);

	const $card = $(`
		<div class="neotec-report ${opts.full ? "neotec-report-full" : ""}">
			<div class="neotec-report-head">
				<div>
					<div class="neotec-report-title">${esc(report.title)}</div>
					<div class="neotec-report-sub">${esc(report.description || "")}
						${report.description ? " · " : ""}${__("{0} rows", [report.rows.length])}
						${report.truncated ? ` · <span class="text-warning">${__("row limit reached")}</span>` : ""}
					</div>
				</div>
				<div class="neotec-report-tools">
					<select class="form-control form-control-sm neotec-chart-type">${options
						.map((t) => `<option value="${t}">${neotec.bi.VIZ_LABELS[t]}</option>`)
						.join("")}</select>
					<div class="btn-group btn-group-sm">
						<button class="btn btn-default dropdown-toggle" data-toggle="dropdown" data-bs-toggle="dropdown">${__("Export")}</button>
						<div class="dropdown-menu dropdown-menu-right">
							<a class="dropdown-item" data-export="xlsx">${__("Excel (.xlsx)")}</a>
							<a class="dropdown-item" data-export="csv">${__("CSV")}</a>
							<a class="dropdown-item" data-export="pdf">${__("PDF")}</a>
							<a class="dropdown-item" data-export="image">${__("Chart image")}</a>
						</div>
					</div>
					<button class="btn btn-sm btn-default neotec-open-builder" title="${__("Open in BI Builder")}">${__("Edit")}</button>
					${opts.saved ? "" : `<button class="btn btn-sm btn-default neotec-save">${__("Save")}</button>`}
					${opts.full ? "" : `<button class="btn btn-sm btn-default neotec-expand" title="${__("Full view")}">⤢</button>`}
				</div>
			</div>
			${(report.summary || []).length ? `<div class="neotec-report-summary">${report.summary
				.map((x) => `<span class="neotec-kpi"><span class="neotec-kpi-label">${esc(x.label)}</span><b>${
					typeof x.value === "number" ? format_number(x.value, null, Number.isInteger(x.value) ? 0 : 2) : esc(x.value ?? "")
				}</b></span>`).join("")}</div>` : ""}
			<div class="neotec-report-body"></div>
		</div>`);
	$wrap.empty().append($card);

	let chart_obj = null;
	const current = () => ({ ...def, title: report.title, viz });
	const draw = () => {
		$card.find(".neotec-chart-type").val(viz.type);
		chart_obj = neotec.bi.render_viz($card.find(".neotec-report-body"), report, viz, { height: opts.full ? 360 : 260, limit: opts.full ? 1000 : 50 });
	};
	$card.find(".neotec-chart-type").on("change", function () {
		const t = $(this).val();
		if (neotec.bi.CHARTS.includes(t)) {
			const x = (viz.x && viz.x.length ? viz.x : [report.columns.find((c) => !neotec.bi.NUMERIC.includes(c.fieldtype))?.fieldname || report.columns[0].fieldname]);
			const y = (viz.y && viz.y.length ? viz.y : [num_cols[0].fieldname]);
			viz = { ...viz, type: t, x, y: ["pie", "donut", "percentage"].includes(t) ? y.slice(0, 1) : y };
		} else {
			viz = t === "table" ? { type: "table" } : { ...(report.viz || {}), type: t };
		}
		draw();
	});
	$card.find("[data-export]").on("click", function (e) {
		e.preventDefault();
		const fmt = $(this).attr("data-export");
		if (fmt === "image") {
			if (chart_obj && chart_obj.export) chart_obj.export();
			else frappe.msgprint(__("Switch to a chart view first."));
			return;
		}
		neotec.bi.export_report(opts.saved && report.name ? { name: report.name } : { definition: current() }, fmt);
	});
	$card.find(".neotec-open-builder").on("click", () => {
		neotec.ai.dialog && neotec.ai.dialog.hide();
		neotec.bi.open_in_builder(current(), opts.saved ? report.name : null);
	});
	$card.find(".neotec-save").on("click", () => neotec.bi.save_dialog(current(), { prompt: opts.prompt }));
	$card.find(".neotec-expand").on("click", () => {
		const d = new frappe.ui.Dialog({ title: esc(report.title), size: "extra-large", fields: [{ fieldname: "body", fieldtype: "HTML" }] });
		d.$wrapper.addClass("neotec-modal");
		d.show();
		neotec.ai.render_report(d.fields_dict.body.$wrapper, { ...report, viz }, { full: true, prompt: opts.prompt });
	});
	setTimeout(draw, 0); // charts need the element in the DOM to size themselves
};

// ------------------------------------------------------------------ sanitizer

// Allow-list HTML sanitizer for model output (model output may echo database text).
neotec.ai.sanitize = function (html) {
	const ALLOWED = new Set([
		"P", "BR", "HR", "B", "STRONG", "I", "EM", "U", "S", "CODE", "PRE", "BLOCKQUOTE",
		"UL", "OL", "LI", "H1", "H2", "H3", "H4", "H5", "H6",
		"TABLE", "THEAD", "TBODY", "TR", "TH", "TD", "A", "SPAN", "DIV",
	]);
	const DROP = new Set(["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM", "INPUT", "TEXTAREA", "SVG", "MATH", "LINK", "META", "IMG", "VIDEO", "AUDIO"]);
	const doc = new DOMParser().parseFromString(`<div>${html || ""}</div>`, "text/html");
	const root = doc.body.firstChild;

	const walk = (node) => {
		for (const child of Array.from(node.childNodes)) {
			if (child.nodeType === Node.COMMENT_NODE) {
				child.remove();
				continue;
			}
			if (child.nodeType !== Node.ELEMENT_NODE) continue;
			if (DROP.has(child.tagName)) {
				child.remove();
				continue;
			}
			walk(child);
			if (!ALLOWED.has(child.tagName)) {
				child.replaceWith(...Array.from(child.childNodes));
				continue;
			}
			for (const attr of Array.from(child.attributes)) {
				const keep =
					(child.tagName === "A" && attr.name === "href" && /^(https?:|mailto:|\/app\/)/i.test(attr.value.trim())) ||
					((child.tagName === "TD" || child.tagName === "TH") && ["colspan", "rowspan", "align"].includes(attr.name));
				if (!keep) child.removeAttribute(attr.name);
			}
			if (child.tagName === "A") {
				child.setAttribute("target", "_blank");
				child.setAttribute("rel", "noopener noreferrer");
			}
			if (child.tagName === "TABLE") child.classList.add("table", "table-bordered", "table-sm");
		}
	};
	walk(root);
	return root.innerHTML;
};
