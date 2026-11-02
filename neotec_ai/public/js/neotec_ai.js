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

neotec.ai.open = function () {
	const cfg = neotec.ai.config || {};
	const ctx = neotec.ai.current_context();
	const esc = frappe.utils.escape_html;

	if (neotec.ai.dialog) {
		const changed = JSON.stringify(ctx) !== JSON.stringify(neotec.ai.dialog.ctx);
		neotec.ai.dialog.ctx = ctx;
		neotec.ai.render_context();
		if (changed) neotec.ai.load_suggestions();
		neotec.ai.dialog.show();
		return;
	}

	const d = new frappe.ui.Dialog({
		title: esc(cfg.assistant_name || "Neotec AI"),
		size: "extra-large",
		fields: [
			{ fieldname: "context_html", fieldtype: "HTML" },
			{ fieldname: "thread_html", fieldtype: "HTML" },
			{ fieldname: "suggest_html", fieldtype: "HTML" },
			{
				fieldname: "prompt",
				fieldtype: "Small Text",
				label: __("Your question"),
				placeholder: __("e.g. Revenue by month this year as a chart, or which invoices are overdue? (Ctrl+Enter to send)"),
			},
		],
		primary_action_label: __("Send"),
		primary_action: () => neotec.ai.send(),
		secondary_action_label: __("New Chat"),
		secondary_action: () => {
			neotec.ai.history = [];
			neotec.ai.render_thread();
			neotec.ai.load_suggestions();
		},
	});
	d.ctx = ctx;
	d.$wrapper.addClass("neotec-modal");
	neotec.ai.dialog = d;

	d.fields_dict.thread_html.$wrapper.html(`<div class="neotec-thread"></div>`);
	d.fields_dict.suggest_html.$wrapper.html(`<div class="neotec-suggest"></div>`);
	d.fields_dict.prompt.$input.css("min-height", "70px").on("keydown", (e) => {
		if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
			e.preventDefault();
			neotec.ai.send();
		}
	});

	neotec.ai.render_context();
	neotec.ai.render_thread();
	neotec.ai.load_suggestions();
	d.show();
	setTimeout(() => d.fields_dict.prompt.$input.trigger("focus"), 200);
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
	const email = esc(cfg.support_email || "");
	d.fields_dict.context_html.$wrapper.html(`
		<div class="neotec-context">
			<span>${__("Context")}: ${where}</span>
			<span>
				<a href="/app/neotec-ai-report" class="neotec-link">${__("Saved reports")}</a>
				· ${cfg.db_queries ? __("Business data: on") : __("Business data: off")}
				${email ? ` · <a href="mailto:${email}">${email}</a>` : ""}
			</span>
		</div>`);
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
			"Ask about your business: sales, customers, stock, payables, or the document you have open. " +
				"Ask for a report or chart and you can view, export and save it. Answers only use data you are allowed to see."
		)}</div>`);
		return;
	}
	for (const m of neotec.ai.history) {
		if (m.role === "user") {
			$t.append(`<div class="neotec-msg neotec-user">${esc(m.content).replace(/\n/g, "<br>")}</div>`);
			continue;
		}
		const $m = $(`<div class="neotec-msg neotec-bot">${neotec.ai.sanitize(frappe.markdown(m.display || m.content))}</div>`);
		$t.append($m);
		for (const rep of m.reports || []) {
			const $r = $(`<div></div>`).appendTo($m);
			neotec.ai.render_report($r, rep, { prompt: m.prompt });
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
	neotec.ai.render_thread(prompt);

	frappe.call({
		method: "neotec_ai.api.chat",
		type: "POST",
		args: {
			prompt,
			doctype: doc_ctx.doctype || null,
			docname: doc_ctx.docname || null,
			history: JSON.stringify(neotec.ai.history.map(({ role, content }) => ({ role, content }))),
		},
		callback(r) {
			const m = r.message || {};
			if (m.status !== "success") {
				neotec.ai.render_thread();
				neotec.ai.show_error(m.message || __("Something went wrong."));
				d.set_value("prompt", prompt);
				return;
			}
			const reports = m.reports || [];
			// The model sees report definitions in later turns so it can modify them ("make it a line chart").
			const notes = reports
				.map((rep) => `[Report shown: ${rep.title}; spec: ${JSON.stringify({ query: rep.spec.query, chart: rep.spec.chart })}]`)
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

neotec.ai.CHART_TYPES = ["bar", "line", "pie", "donut", "percentage"];
neotec.ai.NUMERIC = ["Int", "Float", "Currency", "Percent", "Duration", "Rating"];

/**
 * Render an interactive report card into $wrap.
 * report: {title, description, columns, rows, chart, truncated, spec}
 * opts: {saved, full, prompt}
 */
neotec.ai.render_report = function ($wrap, report, opts = {}) {
	const esc = frappe.utils.escape_html;
	const state = {
		view: report.chart ? "chart" : "table",
		chart: report.chart ? { ...report.chart } : neotec.ai.default_chart(report),
	};
	const inline_limit = opts.full ? 1000 : 50;

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
					<div class="btn-group btn-group-sm neotec-view-toggle">
						<button class="btn btn-default" data-view="chart">${__("Chart")}</button>
						<button class="btn btn-default" data-view="table">${__("Table")}</button>
					</div>
					<select class="form-control form-control-sm neotec-chart-type"></select>
					<div class="btn-group btn-group-sm">
						<button class="btn btn-default dropdown-toggle" data-toggle="dropdown" data-bs-toggle="dropdown">${__("Export")}</button>
						<div class="dropdown-menu dropdown-menu-right">
							<a class="dropdown-item" data-export="xlsx">${__("Excel (.xlsx)")}</a>
							<a class="dropdown-item" data-export="csv">${__("CSV")}</a>
							<a class="dropdown-item" data-export="image">${__("Chart image")}</a>
							<a class="dropdown-item" data-export="print">${__("Print / PDF")}</a>
						</div>
					</div>
					${opts.saved ? "" : `<button class="btn btn-sm btn-default neotec-save">${__("Save")}</button>`}
					${opts.full ? "" : `<button class="btn btn-sm btn-default neotec-expand" title="${__("Full view")}">⤢</button>`}
				</div>
			</div>
			<div class="neotec-report-chart"></div>
			<div class="neotec-report-table"></div>
		</div>`);
	$wrap.empty().append($card);

	const $type = $card.find(".neotec-chart-type");
	$type.html(neotec.ai.CHART_TYPES.map((t) => `<option value="${t}">${__(frappe.utils.to_title_case(t))}</option>`).join(""));

	const can_chart = !!state.chart;
	if (!can_chart) {
		$card.find(".neotec-view-toggle, .neotec-chart-type").hide();
		$card.find('[data-export="image"]').remove();
	}

	let chart_obj = null;
	const draw = () => {
		$card.find(".neotec-view-toggle .btn").removeClass("active btn-primary");
		$card.find(`.neotec-view-toggle [data-view="${state.view}"]`).addClass("active btn-primary");
		const $chart = $card.find(".neotec-report-chart");
		const $table = $card.find(".neotec-report-table");
		if (state.view === "chart" && can_chart) {
			$table.hide();
			$type.show().val(state.chart.type);
			$chart.show();
			chart_obj = neotec.ai.draw_chart($chart, report, state.chart, opts.full ? 360 : 260);
		} else {
			$chart.hide().empty();
			$type.hide();
			$table.show().html(neotec.ai.table_html(report, inline_limit));
		}
	};

	$card.find(".neotec-view-toggle .btn").on("click", function () {
		state.view = $(this).attr("data-view");
		draw();
	});
	$type.on("change", function () {
		state.chart.type = $(this).val();
		if (["pie", "donut", "percentage"].includes(state.chart.type)) state.chart.y = state.chart.y.slice(0, 1);
		draw();
	});
	$card.find("[data-export]").on("click", function (e) {
		e.preventDefault();
		const fmt = $(this).attr("data-export");
		if (fmt === "image") {
			if (chart_obj && chart_obj.export) chart_obj.export();
			else frappe.msgprint(__("Switch to the chart view first."));
		} else if (fmt === "print") {
			neotec.ai.print_report($card, report);
		} else {
			neotec.ai.export_report(opts.saved && report.name ? { name: report.name } : { spec: neotec.ai.current_spec(report, state) }, fmt);
		}
	});
	$card.find(".neotec-save").on("click", () => neotec.ai.save_report(report, state, opts.prompt));
	$card.find(".neotec-expand").on("click", () => neotec.ai.expand_report(report, state, opts.prompt));

	setTimeout(draw, 0); // chart needs the element in the DOM to size itself
};

neotec.ai.default_chart = function (report) {
	const cols = report.columns || [];
	if (cols.length < 2 || !report.rows.length) return null;
	const x = cols.find((c) => !neotec.ai.NUMERIC.includes(c.fieldtype)) || cols[0];
	const y = cols.find((c) => c !== x && neotec.ai.NUMERIC.includes(c.fieldtype));
	return y ? { type: "bar", x: [x.fieldname], y: [y.fieldname] } : null;
};

neotec.ai.current_spec = function (report, state) {
	return { ...report.spec, chart: state.chart && state.chart.y && state.chart.y.length ? state.chart : report.spec.chart };
};

neotec.ai.draw_chart = function ($el, report, chart, height) {
	$el.empty();
	if (!chart || !chart.y || !chart.y.length) return null;
	const idx = {};
	report.columns.forEach((c, i) => (idx[c.fieldname] = i));
	const label_of = (f) => (report.columns[idx[f]] || {}).label || f;

	let rows = report.rows.slice();
	const single = ["pie", "donut", "percentage"].includes(chart.type);
	if (single && rows.length > 12) {
		const yi = idx[chart.y[0]];
		rows.sort((a, b) => (Number(b[yi]) || 0) - (Number(a[yi]) || 0));
		const other = rows.slice(11).reduce((s, r) => s + (Number(r[yi]) || 0), 0);
		rows = rows.slice(0, 11);
		const o = new Array(report.columns.length).fill(null);
		o[idx[chart.x[0]]] = __("Other");
		o[yi] = other;
		rows.push(o);
	} else if (rows.length > 120) {
		rows = rows.slice(0, 120);
	}

	const labels = rows.map((r) =>
		chart.x
			.map((x, i) => {
				const v = r[idx[x]];
				return i > 0 && typeof v === "number" && v < 10 ? `0${v}` : v ?? "-";
			})
			.join("-")
	);
	const datasets = chart.y.map((y) => ({
		name: label_of(y),
		values: rows.map((r) => Number(r[idx[y]]) || 0),
	}));

	try {
		return new frappe.Chart($el[0], {
			type: chart.type,
			height,
			data: { labels: labels.map(String), datasets },
			axisOptions: { xIsSeries: chart.type === "line", xAxisMode: labels.length > 12 ? "tick" : "span" },
			lineOptions: { regionFill: 1, dotSize: 3 },
			barOptions: { spaceRatio: 0.35 },
			tooltipOptions: { formatTooltipY: (v) => format_number(v, null, Number.isInteger(v) ? 0 : 2) },
		});
	} catch (e) {
		$el.html(`<div class="text-muted small">${__("This data cannot be drawn as a {0} chart.", [chart.type])}</div>`);
		return null;
	}
};

neotec.ai.table_html = function (report, limit) {
	const esc = frappe.utils.escape_html;
	const cols = report.columns;
	const head = cols
		.map((c) => `<th class="${neotec.ai.NUMERIC.includes(c.fieldtype) ? "text-right" : ""}">${esc(c.label)}</th>`)
		.join("");
	const fmt = (v, c) => {
		if (v === null || v === undefined || v === "") return "";
		if (["Currency", "Float", "Percent"].includes(c.fieldtype)) return format_number(v, null, 2);
		if (c.fieldtype === "Int") return format_number(v, null, 0);
		if (c.fieldtype === "Date") return esc(frappe.datetime.str_to_user(String(v)));
		if (c.fieldtype === "Check") return v ? "✓" : "";
		return esc(String(v));
	};
	const body = report.rows
		.slice(0, limit)
		.map(
			(r) =>
				`<tr>${r
					.map((v, i) => `<td class="${neotec.ai.NUMERIC.includes(cols[i].fieldtype) ? "text-right" : ""}">${fmt(v, cols[i])}</td>`)
					.join("")}</tr>`
		)
		.join("");
	const more =
		report.rows.length > limit
			? `<div class="text-muted small mt-1">${__("Showing {0} of {1} rows. Use full view or export for all rows.", [limit, report.rows.length])}</div>`
			: "";
	return `<div class="neotec-table-wrap"><table class="table table-sm table-bordered table-hover neotec-table">
		<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>${more}`;
};

neotec.ai.expand_report = function (report, state, prompt) {
	const d = new frappe.ui.Dialog({ title: frappe.utils.escape_html(report.title), size: "extra-large", fields: [{ fieldname: "body", fieldtype: "HTML" }] });
	d.$wrapper.addClass("neotec-modal");
	d.show();
	neotec.ai.render_report(d.fields_dict.body.$wrapper, { ...report, chart: state.chart || report.chart }, { full: true, prompt });
};

neotec.ai.save_report = function (report, state, prompt) {
	frappe.prompt(
		[
			{ fieldname: "title", fieldtype: "Data", label: __("Report title"), reqd: 1, default: report.title },
			{ fieldname: "open", fieldtype: "Check", label: __("Open after saving"), default: 0 },
		],
		(v) => {
			frappe.call({
				method: "neotec_ai.reports.save_report",
				type: "POST",
				args: { spec: JSON.stringify(neotec.ai.current_spec(report, state)), title: v.title, prompt: prompt || "" },
				freeze: true,
				callback(r) {
					if (!r.message) return;
					frappe.show_alert({
						message: __("Saved as {0}", [`<a href="/app/neotec-ai-report/${encodeURIComponent(r.message.name)}">${frappe.utils.escape_html(r.message.title)}</a>`]),
						indicator: "green",
					}, 7);
					if (v.open) {
						neotec.ai.dialog && neotec.ai.dialog.hide();
						frappe.set_route("Form", "Neotec AI Report", r.message.name);
					}
				},
			});
		},
		__("Save Report"),
		__("Save")
	);
};

// POST a hidden form so the browser downloads the file (re-run live on the server).
neotec.ai.export_report = function (target, fmt) {
	const params = { fmt, csrf_token: frappe.csrf_token };
	if (target.name) params.name = target.name;
	else params.spec = JSON.stringify(target.spec);
	const $form = $("<form>", { method: "POST", action: "/api/method/neotec_ai.reports.export_report", target: "_blank" });
	Object.entries(params).forEach(([k, v]) => $form.append($("<input>", { type: "hidden", name: k, value: v })));
	$form.appendTo("body").trigger("submit").remove();
};

neotec.ai.print_report = function ($card, report) {
	const w = window.open("", "_blank");
	if (!w) return frappe.msgprint(__("Allow pop-ups to print."));
	const chart_svg = $card.find(".neotec-report-chart:visible svg").first().prop("outerHTML") || "";
	w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${frappe.utils.escape_html(report.title)}</title>
		<style>body{font-family:system-ui,sans-serif;margin:24px;color:#111}h2{margin:0 0 4px}p{color:#555;margin:0 0 16px}
		table{border-collapse:collapse;width:100%;font-size:12px}th,td{border:1px solid #ccc;padding:4px 6px}th{background:#f3f4f6}
		.text-right{text-align:right}svg{max-width:100%}</style></head><body>
		<h2>${frappe.utils.escape_html(report.title)}</h2><p>${frappe.utils.escape_html(report.description || "")} · ${frappe.datetime.now_datetime()}</p>
		${chart_svg}${neotec.ai.table_html(report, 100000)}</body></html>`);
	w.document.close();
	w.focus();
	setTimeout(() => w.print(), 300);
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
