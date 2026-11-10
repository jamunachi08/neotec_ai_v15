// Copyright (c) 2026, Neotec Integrated Solutions
// Neotec AI — chat workspace.

(() => {
frappe.pages["coworker"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Neotec AI"), single_column: true });
	wrapper.ntc = new NTCChat(wrapper);
};

frappe.pages["coworker"].on_page_show = function (wrapper) {
	if (wrapper.ntc) wrapper.ntc.apply_route();
};

const NTC_API = "neotec_ai.agents.api.";
const ntcEsc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
const ntcIsAr = () => (frappe.boot.lang || "en").startsWith("ar");

// Safe mini-markdown: escape first, then a small set of formats. No raw HTML from the model ever renders.
function ntcMarkdown(src) {
	if (!src) return "";
	const blocks = [];
	let text = ntcEsc(src).replace(/```([\s\S]*?)```/g, (m, code) => {
		blocks.push(`<pre class="ntc-code">${code.replace(/^\w*\n/, "")}</pre>`);
		return `\u0000${blocks.length - 1}\u0000`;
	});
	const inline = (t) =>
		t
			.replace(/`([^`]+)`/g, "<code>$1</code>")
			.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
			.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
			.replace(/\[([^\]]+)\]\(((?:https?:\/\/|\/app\/)[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
	const lines = text.split("\n");
	const out = [];
	let list = null;
	let table = null;
	const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
	const closeTable = () => {
		if (!table) return;
		const [head, ...rows] = table.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r));
		const cells = (r) => r.replace(/^\s*\||\|\s*$/g, "").split("|").map((c) => inline(c.trim()));
		out.push('<div class="ntc-table-wrap"><table class="ntc-table"><thead><tr>' +
			cells(head).map((c) => `<th>${c}</th>`).join("") + "</tr></thead><tbody>" +
			rows.map((r) => "<tr>" + cells(r).map((c) => `<td>${c}</td>`).join("") + "</tr>").join("") +
			"</tbody></table></div>");
		table = null;
	};
	for (const raw of lines) {
		const line = raw.trimEnd();
		if (/^\s*\|.*\|\s*$/.test(line)) { closeList(); (table = table || []).push(line); continue; }
		closeTable();
		let m;
		if ((m = line.match(/^\s*[-*•]\s+(.*)/))) {
			if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
			out.push(`<li>${inline(m[1])}</li>`);
		} else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) {
			if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; }
			out.push(`<li>${inline(m[1])}</li>`);
		} else if ((m = line.match(/^(#{1,4})\s+(.*)/))) {
			closeList();
			out.push(`<h${m[1].length + 3} class="ntc-h">${inline(m[2])}</h${m[1].length + 3}>`);
		} else if (!line.trim()) {
			closeList();
			out.push("");
		} else {
			closeList();
			out.push(`<p>${inline(line)}</p>`);
		}
	}
	closeList();
	closeTable();
	return out.join("\n").replace(/\u0000(\d+)\u0000/g, (m, i) => blocks[+i]);
}

class NTCChat {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = wrapper.page;
		this.state = { coworkers: [], conversations: [], current: null, coworker: null, context: null, data: null };
		this.poll = null;
		this.charts = [];
		this.render_shell();
		this.load().then(() => this.apply_route());
		frappe.realtime.on("neotec_ai_agents", (msg) => {
			if (msg && this.state.current && msg.conversation === this.state.current) this.refresh_conversation();
			else this.refresh_list();
		});
	}

	render_shell() {
		const $body = $(this.page.body).empty().addClass("ntc-page");
		this.$root = $(`
			<div class="ntc-shell">
				<aside class="ntc-side">
					<button class="ntc-new btn btn-default btn-sm">${__("New conversation")}</button>
					<div class="ntc-side-label">${__("Coworkers")}</div>
					<div class="ntc-team"></div>
					<a class="ntc-inbox hidden" href="/app/coworker-approval?status=Pending"></a>
					<div class="ntc-side-label">${__("Recent")}</div>
					<div class="ntc-history"></div>
				</aside>
				<main class="ntc-main">
					<header class="ntc-head"></header>
					<div class="ntc-thread" aria-live="polite"></div>
					<div class="ntc-composer">
						<div class="ntc-context"></div>
						<div class="ntc-input-row">
							<textarea class="ntc-input" rows="1" dir="auto" placeholder="${__("Ask your coworker…")}"></textarea>
							<button class="ntc-send btn btn-primary btn-sm">${__("Send")}</button>
						</div>
						<div class="ntc-foot">${__("Every action is checked against company policy and recorded.")}</div>
					</div>
				</main>
				<aside class="ntc-activity hidden">
					<div class="ntc-activity-head">
						<strong>${__("Activity")}</strong>
						<button class="btn btn-xs btn-default ntc-activity-close">${__("Close")}</button>
					</div>
					<div class="ntc-activity-body"></div>
				</aside>
			</div>`).appendTo($body);

		this.$team = this.$root.find(".ntc-team");
		this.$history = this.$root.find(".ntc-history");
		this.$head = this.$root.find(".ntc-head");
		this.$thread = this.$root.find(".ntc-thread");
		this.$input = this.$root.find(".ntc-input");
		this.$send = this.$root.find(".ntc-send");
		this.$context = this.$root.find(".ntc-context");
		this.$activity = this.$root.find(".ntc-activity");

		this.$root.find(".ntc-new").on("click", () => this.new_conversation(this.state.coworker));
		this.$send.on("click", () => this.send());
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); this.send(); }
		});
		this.$input.on("input", () => this.autosize());
		this.$root.find(".ntc-activity-close").on("click", () => this.$activity.addClass("hidden"));
	}

	autosize() {
		const el = this.$input.get(0);
		el.style.height = "auto";
		el.style.height = Math.min(el.scrollHeight, 220) + "px";
	}

	async load() {
		const r = await frappe.call({ method: NTC_API + "bootstrap" });
		const b = r.message || {};
		this.state.coworkers = b.coworkers || [];
		this.state.conversations = b.conversations || [];
		this.state.is_admin = b.is_admin;
		if (!b.setup_completed && b.is_admin) {
			this.page.set_primary_action(__("Finish setup"), () => frappe.set_route("coworker-setup"));
		} else if (b.is_admin) {
			this.page.add_menu_item(__("Setup wizard"), () => frappe.set_route("coworker-setup"));
		}
		if (b.is_admin) {
			this.page.add_menu_item(__("Audit trail"), () => frappe.set_route("List", "Coworker Action Log"));
			this.page.add_menu_item(__("Policies"), () => frappe.set_route("List", "Coworker Policy Rule"));
		}
		this.page.add_menu_item(__("My routines"), () => frappe.set_route("List", "Coworker Routine"));
		this.page.add_menu_item(__("My memory"), () => frappe.set_route("List", "Coworker Memory"));
		if (b.pending_approvals) {
			this.$root.find(".ntc-inbox").removeClass("hidden")
				.text(__("{0} action(s) waiting for approval", [b.pending_approvals]));
		}
		if (!this.state.coworker && this.state.coworkers.length) this.state.coworker = this.state.coworkers[0].name;
		this.render_team();
		this.render_history();
		if (!b.enabled) {
			this.$thread.html(`<div class="ntc-empty"><p>${__("Neotec AI is switched off by the administrator.")}</p></div>`);
		}
	}

	apply_route() {
		const opts = Object.assign({}, frappe.utils.get_query_params ? frappe.utils.get_query_params() : {}, frappe.route_options || {});
		frappe.route_options = null;
		if (opts.coworker && this.state.coworkers.some((c) => c.name === opts.coworker)) this.state.coworker = opts.coworker;
		if (opts.doctype && opts.name) this.state.context = { doctype: opts.doctype, name: opts.name };
		if (opts.conversation) return this.open_conversation(opts.conversation);
		if (!this.state.current) this.new_conversation(this.state.coworker);
		if (opts.prompt) { this.$input.val(opts.prompt); this.autosize(); }
	}

	cw(name) {
		return this.state.coworkers.find((c) => c.name === name) || { name, title: "", icon: "🤖" };
	}

	cw_title(c) {
		return ntcIsAr() && c.title_ar ? c.title_ar : c.title || "";
	}

	render_team() {
		this.$team.empty();
		if (!this.state.coworkers.length) {
			this.$team.html(`<div class="ntc-muted">${this.state.is_admin
				? __("No coworkers yet. Run the setup wizard.")
				: __("No coworker is available to you yet. Ask your administrator.")}</div>`);
			return;
		}
		for (const c of this.state.coworkers) {
			const $b = $(`<button class="ntc-mate" type="button">
					<span class="ntc-avatar" style="--mate:${ntcEsc(c.color || "var(--primary)")}">${ntcEsc(c.icon)}</span>
					<span class="ntc-mate-text"><span class="ntc-mate-name">${ntcEsc(c.name)}</span>
					<span class="ntc-mate-title">${ntcEsc(this.cw_title(c))}</span></span>
				</button>`);
			$b.toggleClass("active", c.name === this.state.coworker);
			$b.on("click", () => this.new_conversation(c.name));
			this.$team.append($b);
		}
	}

	render_history() {
		this.$history.empty();
		const list = this.state.conversations || [];
		if (!list.length) {
			this.$history.html(`<div class="ntc-muted">${__("Conversations appear here.")}</div>`);
			return;
		}
		for (const conv of list) {
			const c = this.cw(conv.coworker);
			const $row = $(`<div class="ntc-conv" role="button" tabindex="0">
				<span class="ntc-conv-icon">${ntcEsc(c.icon || "🤖")}</span>
				<span class="ntc-conv-title" dir="auto">${ntcEsc(conv.title || __("Untitled"))}</span>
				<span class="ntc-conv-dot ${conv.status === "Waiting Approval" ? "wait" : conv.status === "Running" ? "run" : ""}"></span>
			</div>`);
			$row.toggleClass("active", conv.name === this.state.current);
			$row.on("click keypress", () => this.open_conversation(conv.name));
			this.$history.append($row);
		}
	}

	async refresh_list() {
		const r = await frappe.call({ method: NTC_API + "list_conversations" });
		this.state.conversations = r.message || [];
		this.render_history();
	}

	new_conversation(coworker) {
		this.stop_poll();
		this.state.current = null;
		this.state.data = null;
		if (coworker) this.state.coworker = coworker;
		this.render_team();
		this.render_history();
		this.render_head();
		this.render_context();
		const c = this.cw(this.state.coworker);
		const desc = ntcIsAr() && c.description_ar ? c.description_ar : c.description;
		const $empty = $(`<div class="ntc-empty">
				<div class="ntc-empty-avatar" style="--mate:${ntcEsc(c.color || "var(--primary)")}">${ntcEsc(c.icon || "🤖")}</div>
				<h3>${ntcEsc(c.name || __("Coworker"))}</h3>
				<p class="ntc-muted" dir="auto">${ntcEsc(desc || "")}</p>
				<div class="ntc-starters"></div>
			</div>`);
		for (const s of c.starters || []) {
			$(`<button class="ntc-chip" type="button" dir="auto">${ntcEsc(s)}</button>`)
				.on("click", () => { this.$input.val(s); this.send(); })
				.appendTo($empty.find(".ntc-starters"));
		}
		this.$thread.empty().append($empty);
		this.set_busy(false);
		this.$input.trigger("focus");
	}

	render_context() {
		this.$context.empty();
		const ctx = this.state.data ? (this.state.data.context_doctype
			? { doctype: this.state.data.context_doctype, name: this.state.data.context_name } : null) : this.state.context;
		if (!ctx) return;
		const $chip = $(`<span class="ntc-context-chip">${__("About")} <a href="${frappe.utils.get_form_link(ctx.doctype, ctx.name)}">${ntcEsc(__(ctx.doctype))} ${ntcEsc(ctx.name)}</a></span>`);
		if (!this.state.data) {
			$(`<button class="ntc-context-x" type="button" aria-label="${__("Remove")}">×</button>`)
				.on("click", () => { this.state.context = null; this.render_context(); }).appendTo($chip);
		}
		this.$context.append($chip);
	}

	render_head() {
		const d = this.state.data;
		const c = this.cw(d ? d.coworker : this.state.coworker);
		const status = d ? d.status : "Idle";
		const label = { Running: __("Working"), Stopping: __("Stopping"), "Waiting Approval": __("Waiting for approval"),
			Error: __("Error"), Idle: "" }[status] || "";
		this.$head.html(`
			<span class="ntc-avatar sm" style="--mate:${ntcEsc(c.color || "var(--primary)")}">${ntcEsc(c.icon || "🤖")}</span>
			<div class="ntc-head-text"><div class="ntc-head-name">${ntcEsc(c.name || "")}</div>
			<div class="ntc-head-sub" dir="auto">${ntcEsc(d ? d.title || "" : this.cw_title(c))}</div></div>
			<span class="ntc-status ${status.replace(/\s/g, "-").toLowerCase()}">${label}</span>
			<div class="ntc-head-actions"></div>`);
		const $a = this.$head.find(".ntc-head-actions");
		if (d) {
			const modes = { Standard: __("Standard"), "Read Only": __("Read only"), "Plan First": __("Plan first") };
			const $mode = $(`<select class="form-control input-xs ntc-mode" title="${__("What the coworker may do in this chat")}"></select>`);
			Object.keys(modes).forEach((k) => $mode.append(`<option value="${k}">${modes[k]}</option>`));
			$mode.val(d.permission_mode || "Standard").on("change", () =>
				frappe.call({ method: NTC_API + "set_mode", args: { conversation: d.name, mode: $mode.val() } })
					.then(() => { d.permission_mode = $mode.val(); frappe.show_alert({ message: __("Mode: {0}", [modes[$mode.val()]]), indicator: "blue" }); }));
			$mode.appendTo($a);
			if ((d.allowed_tools || []).length) {
				$(`<button class="btn btn-xs btn-default" title="${ntcEsc(d.allowed_tools.join(", "))}">${__("Always allowed: {0}", [d.allowed_tools.length])}</button>`)
					.on("click", () => frappe.confirm(__("Ask again before every change in this chat?"), () =>
						frappe.call({ method: NTC_API + "forget_allowed_tools", args: { conversation: d.name } }).then(() => this.refresh_conversation(true))))
					.appendTo($a);
			}
			$(`<button class="btn btn-xs btn-default">${__("Activity")}</button>`).on("click", () => this.show_activity()).appendTo($a);
			if (status === "Running") {
				$(`<button class="btn btn-xs btn-default">${__("Stop")}</button>`).on("click", () =>
					frappe.call({ method: NTC_API + "stop", args: { conversation: d.name } })).appendTo($a);
			}
			if (d.stale) {
				$(`<button class="btn btn-xs btn-warning">${__("Unstick")}</button>`).on("click", () =>
					frappe.call({ method: NTC_API + "reset", args: { conversation: d.name } }).then(() => this.refresh_conversation())).appendTo($a);
			}
			$(`<button class="btn btn-xs btn-default">${__("Delete")}</button>`).on("click", () =>
				frappe.confirm(__("Delete this conversation? The audit trail is kept."), () =>
					frappe.call({ method: NTC_API + "delete_conversation", args: { conversation: d.name } }).then(() => {
						this.new_conversation(d.coworker);
						this.refresh_list();
					}))).appendTo($a);
		}
	}

	async open_conversation(name) {
		this.state.current = name;
		this.state.context = null;
		await this.refresh_conversation(true);
		this.render_history();
	}

	async refresh_conversation(scroll) {
		if (!this.state.current) return;
		const name = this.state.current;
		const r = await frappe.call({ method: NTC_API + "get_conversation", args: { name } });
		if (name !== this.state.current) return;
		const prevCount = this.state.data && this.state.data.name === name ? this.state.data.messages.length : -1;
		const prevStatus = this.state.data && this.state.data.status;
		this.state.data = r.message;
		this.state.coworker = r.message.coworker;
		this.render_team();
		this.render_head();
		this.render_context();
		this.render_thread(scroll || prevCount !== this.state.data.messages.length);
		const busy = ["Running", "Stopping"].includes(this.state.data.status);
		this.set_busy(busy || this.state.data.status === "Waiting Approval");
		if (busy) this.start_poll(); else this.stop_poll();
		if (prevStatus && prevStatus !== this.state.data.status) this.refresh_list();
	}

	start_poll() {
		if (this.poll) return;
		this.poll = setInterval(() => this.refresh_conversation(), 2000);
	}

	stop_poll() {
		if (this.poll) clearInterval(this.poll);
		this.poll = null;
	}

	set_busy(busy) {
		this.$input.prop("disabled", busy);
		this.$send.prop("disabled", busy);
		this.$input.attr("placeholder", busy ? __("Working… you can watch the activity.") : __("Ask your coworker…"));
	}

	render_thread(scroll) {
		this.charts = [];
		const d = this.state.data;
		const results = {};
		for (const m of d.messages) if (m.role === "tool") results[m.tool_call_id] = m;
		const $t = this.$thread.empty();
		for (const m of d.messages) {
			if (m.role === "user") {
				$(`<div class="ntc-msg user"><div class="ntc-bubble" dir="auto">${ntcMarkdown(m.content)}</div></div>`).appendTo($t);
			} else if (m.role === "assistant") {
				if (m.status === "error") {
					$(`<div class="ntc-msg"><div class="ntc-callout danger" dir="auto">${ntcEsc(m.content)}</div></div>`).appendTo($t);
					continue;
				}
				const $m = $(`<div class="ntc-msg bot"></div>`);
				if (m.content) $m.append(`<div class="ntc-text" dir="auto">${ntcMarkdown(m.content)}</div>`);
				if (m.tool_calls && m.tool_calls.length) {
					const $ledger = $(`<div class="ntc-ledger"></div>`);
					for (const c of m.tool_calls) {
						const res = results[c.id];
						const st = res ? res.status || "running" : "running";
						const word = { ok: __("done"), pending: __("waiting for approval"), refused: __("refused by policy"),
							error: __("failed"), rejected: __("rejected"), expired: __("expired"), running: __("working") }[st] || st;
						$ledger.append(`<div class="ntc-step ${st}" title="${ntcEsc(res && res.note ? res.note : "")}">
							<span class="ntc-step-mark"></span><span class="ntc-step-label">${ntcEsc(c.label || c.name)}</span>
							<span class="ntc-step-state">${word}</span></div>`);
						if (res && ["refused", "error"].includes(st) && res.note) {
							$ledger.append(`<div class="ntc-step-note" dir="auto">${ntcEsc(res.note)}</div>`);
						}
					}
					$m.append($ledger);
				}
				$t.append($m);
			} else if (m.role === "tool") {
				if (m.blocks) $t.append(this.render_blocks(m.blocks));
				if (m.approval && d.approvals[m.approval]) $t.append(this.render_approval(d.approvals[m.approval]));
			}
		}
		if (["Running", "Stopping"].includes(d.status)) {
			$t.append(`<div class="ntc-thinking"><span></span><span></span><span></span></div>`);
		}
		if (scroll) $t.scrollTop($t.get(0).scrollHeight);
	}

	render_approval(a) {
		const done = a.status !== "Pending";
		const $card = $(`<div class="ntc-approval ${a.status.toLowerCase()}">
			<div class="ntc-approval-stamp">${ntcEsc(__(a.status === "Pending" ? "Needs approval" : a.status))}</div>
			<div class="ntc-approval-summary" dir="auto">${ntcEsc(a.summary)}</div>
			<details class="ntc-approval-args"><summary>${__("Details")}</summary><pre>${ntcEsc(a.arguments)}</pre></details>
			<div class="ntc-approval-foot"></div></div>`);
		const $f = $card.find(".ntc-approval-foot");
		if (done) {
			$f.text(a.decided_by ? __("{0} by {1}", [__(a.status), a.decided_by]) + (a.comment ? ` — ${a.comment}` : "") : "");
		} else if (a.can_decide) {
			const decide = (approve, remember) =>
				frappe.call({ method: NTC_API + "decide_approval", args: { approval: a.name, approve: approve ? 1 : 0, remember: remember ? 1 : 0 },
					freeze: true, freeze_message: approve ? __("Running the approved action…") : __("Rejecting…") })
					.then(() => this.refresh_conversation(true));
			$(`<button class="btn btn-primary btn-xs">${__("Approve and run")}</button>`).on("click", () => decide(true)).appendTo($f);
			if (a.can_remember) {
				$(`<button class="btn btn-default btn-xs" title="${__("Run it, and do not ask again for this tool in this chat")}">${__("Approve, always in this chat")}</button>`)
					.on("click", () => decide(true, true)).appendTo($f);
			}
			$(`<button class="btn btn-default btn-xs">${__("Reject")}</button>`).on("click", () => decide(false)).appendTo($f);
		} else {
			$f.text(a.approver_role ? __("Waiting for a user with the role {0} ({1}).", [a.approver_role, a.name]) : a.why_not || "");
		}
		return $card;
	}

	render_blocks(payload) {
		const $wrap = $(`<div class="ntc-blocks"></div>`);
		if (payload.title) $wrap.append(`<div class="ntc-blocks-title" dir="auto">${ntcEsc(payload.title)}</div>`);
		for (const b of payload.blocks || []) {
			try {
				$wrap.append(this.render_block(b));
			} catch (e) {
				console.error("Neotec AI block", b, e);
			}
		}
		return $wrap;
	}

	render_block(b) {
		switch (b.type) {
			case "text":
				return $(`<div class="ntc-text" dir="auto">${ntcMarkdown(b.text)}</div>`);
			case "callout":
				return $(`<div class="ntc-callout ${b.tone}" dir="auto">${ntcMarkdown(b.text)}</div>`);
			case "kpis": {
				const $k = $(`<div class="ntc-kpis"></div>`);
				for (const i of b.items) {
					$k.append(`<div class="ntc-kpi"><div class="ntc-kpi-value ${i.trend || ""}">${ntcEsc(i.value)}</div>
						<div class="ntc-kpi-label" dir="auto">${ntcEsc(i.label)}</div>
						${i.hint ? `<div class="ntc-kpi-hint" dir="auto">${ntcEsc(i.hint)}</div>` : ""}</div>`);
				}
				return $k;
			}
			case "table": {
				const num = (v) => /^-?[\d,]+(\.\d+)?%?$/.test(String(v).trim());
				const html = `<div class="ntc-table-wrap"><table class="ntc-table">
					${b.caption ? `<caption>${ntcEsc(b.caption)}</caption>` : ""}
					<thead><tr>${b.columns.map((c) => `<th>${ntcEsc(c)}</th>`).join("")}</tr></thead>
					<tbody>${b.rows.map((r) => "<tr>" + r.map((v) => `<td class="${num(v) ? "num" : ""}" dir="auto">${ntcEsc(v)}</td>`).join("") + "</tr>").join("")}</tbody>
					</table></div>`;
				const $t = $(html);
				$(`<button class="btn btn-xs btn-default ntc-copy">${__("Copy as CSV")}</button>`).on("click", () => {
					const csv = [b.columns, ...b.rows].map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
					frappe.utils.copy_to_clipboard(csv);
				}).appendTo($t);
				return $t;
			}
			case "chart": {
				const $c = $(`<div class="ntc-chart">${b.title ? `<div class="ntc-chart-title" dir="auto">${ntcEsc(b.title)}</div>` : ""}<div class="ntc-chart-canvas"></div></div>`);
				setTimeout(() => {
					try {
						this.charts.push(new frappe.Chart($c.find(".ntc-chart-canvas").get(0), {
							type: b.chart, height: 240,
							data: { labels: b.labels, datasets: b.datasets },
							axisOptions: { xIsSeries: b.chart === "line" ? 1 : 0 },
							colors: ["#0F6E66", "#B7791F", "#1D4E89", "#7A3E9D", "#5B6B2F", "#B42318"],
						}));
					} catch (e) { $c.append(`<div class="ntc-muted">${__("Chart could not be drawn.")}</div>`); }
				}, 0);
				return $c;
			}
			case "doclist": {
				const $l = $(`<div class="ntc-doclist"></div>`);
				for (const i of b.items) {
					$l.append(`<a class="ntc-doc" href="${frappe.utils.get_form_link(i.doctype, i.name)}">
						<span class="ntc-doc-type">${ntcEsc(__(i.doctype))}</span>
						<span class="ntc-doc-name" dir="auto">${ntcEsc(i.label || i.name)}</span>
						${i.hint ? `<span class="ntc-doc-hint" dir="auto">${ntcEsc(i.hint)}</span>` : ""}</a>`);
				}
				return $l;
			}
			case "actions": {
				const $a = $(`<div class="ntc-starters"></div>`);
				const busy = this.state.data && this.state.data.status !== "Idle";
				for (const i of b.items) {
					$(`<button class="ntc-chip" type="button" dir="auto">${ntcEsc(i.label)}</button>`)
						.prop("disabled", busy).on("click", () => { this.$input.val(i.prompt); this.send(); }).appendTo($a);
				}
				return $a;
			}
			case "form": {
				const $f = $(`<div class="ntc-form"><div class="ntc-form-title" dir="auto">${ntcEsc(b.title || "")}</div><div class="ntc-form-body"></div></div>`);
				const fg = new frappe.ui.FieldGroup({
					fields: b.fields.map((f) => ({ fieldname: f.fieldname, label: f.label, fieldtype: f.fieldtype,
						options: f.options, default: f.default })),
					body: $f.find(".ntc-form-body").get(0),
				});
				fg.make();
				$(`<button class="btn btn-primary btn-xs">${ntcEsc(b.submit_label || __("Send"))}</button>`).on("click", () => {
					const values = fg.get_values();
					if (!values) return;
					frappe.call({ method: NTC_API + "submit_form",
						args: { conversation: this.state.current, title: b.title, values: JSON.stringify(values) } })
						.then(() => this.refresh_conversation(true));
				}).appendTo($f);
				return $f;
			}
			default:
				return $("<div></div>");
		}
	}

	async send() {
		const text = (this.$input.val() || "").trim();
		if (!text) return;
		if (!this.state.current && !this.state.coworker) {
			frappe.msgprint(__("Choose a coworker first."));
			return;
		}
		this.set_busy(true);
		const args = { text };
		if (this.state.current) args.conversation = this.state.current;
		else {
			args.coworker = this.state.coworker;
			if (this.state.context) Object.assign(args, { context_doctype: this.state.context.doctype, context_name: this.state.context.name });
		}
		try {
			const r = await frappe.call({ method: NTC_API + "send_message", args });
			this.$input.val("");
			this.autosize();
			this.state.current = r.message.conversation;
			await this.refresh_conversation(true);
			this.refresh_list();
		} catch (e) {
			this.set_busy(false);
		}
	}

	async show_activity() {
		this.$activity.removeClass("hidden");
		const $b = this.$activity.find(".ntc-activity-body").html(`<div class="ntc-muted">${__("Loading…")}</div>`);
		const r = await frappe.call({ method: NTC_API + "get_activity", args: { conversation: this.state.current } });
		const rows = r.message || [];
		if (!rows.length) { $b.html(`<div class="ntc-muted">${__("No tool has run in this conversation yet.")}</div>`); return; }
		$b.empty();
		for (const l of rows) {
			$b.append(`<a class="ntc-log ${l.status.replace(/\s/g, "-").toLowerCase()}" href="/app/coworker-action-log/${encodeURIComponent(l.name)}">
				<div class="ntc-log-top"><span class="ntc-log-tool">${ntcEsc(l.tool)}</span>
				<span class="ntc-log-status">${ntcEsc(__(l.status))}</span></div>
				<div class="ntc-log-meta">${ntcEsc(frappe.datetime.comment_when ? frappe.datetime.comment_when(l.creation) : l.creation)}
				${l.duration_ms ? ` · ${l.duration_ms} ms` : ""}${l.rule ? ` · ${ntcEsc(l.rule)}` : ""}</div>
				${l.reason || l.error ? `<div class="ntc-log-reason" dir="auto">${ntcEsc(l.error || l.reason)}</div>` : ""}</a>`);
		}
	}
}

})();
