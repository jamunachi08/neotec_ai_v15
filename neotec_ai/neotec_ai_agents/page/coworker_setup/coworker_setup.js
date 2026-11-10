// Copyright (c) 2026, Neotec Integrated Solutions
// Neotec AI — setup wizard: provider, coworkers, governance and access, health.

(() => {
const API = "neotec_ai.agents.api.";
const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

frappe.pages["coworker-setup"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Coworker Setup"), single_column: true });
	wrapper.setup = new Setup(wrapper);
};

frappe.pages["coworker-setup"].on_page_show = function (wrapper) {
	if (wrapper.setup) wrapper.setup.load();
};

class Setup {
	constructor(wrapper) {
		this.page = wrapper.page;
		this.$body = $(this.page.body).addClass("ntc-page");
		this.page.set_secondary_action(__("Open chat"), () => frappe.set_route("coworker"));
		this.load();
	}

	render_integrations(rows, move) {
		const $i = this.$body.find(".ntc-integrations").empty();
		if (!rows.length) $i.append(`<p class="ntc-muted">${__("No other app on this site offers a connection yet.")}</p>`);
		rows.forEach((r) => {
			const $row = $(`<label class="ntc-int-row"><input type="checkbox" ${r.connected ? "checked" : ""}>
				<b>${esc(r.label)}</b> <span class="ntc-muted">${esc(r.description || "")}</span></label>`).appendTo($i);
			$row.find("input").on("change", (e) => frappe.call({ method: "neotec_ai.platform.integrations.set_integration",
				args: { app: r.app, enabled: e.target.checked ? 1 : 0 } })
				.then(() => frappe.show_alert({ message: e.target.checked ? __("{0} now uses Neotec AI", [r.label]) : __("{0} uses its own connection", [r.label]), indicator: "green" })));
		});
		const $m = this.$body.find(".ntc-move").empty();
		if (move.legacy_installed) {
			$m.html(move.safe_to_uninstall
				? `<div class="alert alert-success">${__("All coworker records now belong to Neotec AI. Uninstall the old Neotec Coworker app from this site to finish the move; nothing is lost.")}</div>`
				: `<div class="alert alert-warning">${__("Run Migrate once more before uninstalling the old Neotec Coworker app. Still moving: {0}", [esc((move.pending || []).join(", "))])}</div>`);
		}
	}

	async load() {
		const r = await frappe.call({ method: API + "get_setup_state" });
		this.state = r.message;
		this.render();
	}

	render() {
		const s = this.state;
		this.$body.html(`
			<div class="ntc-setup">
				<section class="ntc-step" data-step="1">
					<h3><span class="ntc-step-no">1</span>${__("Connect an AI provider")}</h3>
					<p class="ntc-muted">${__("Pick where the model runs. On-premises and in-Kingdom providers keep ERP data in Saudi Arabia.")}</p>
					<div class="ntc-presets"></div>
					<div class="ntc-provider-form"></div>
					<div class="ntc-provider-result"></div>
				</section>
				<section class="ntc-step" data-step="2">
					<h3><span class="ntc-step-no">2</span>${__("Choose your coworkers")}</h3>
					<p class="ntc-muted">${__("Each coworker has its own role, instructions and granted tools. You can edit them later under AI Coworker.")}</p>
					<div class="ntc-pick"></div>
				</section>
				<section class="ntc-step" data-step="3">
					<h3><span class="ntc-step-no">3</span>${__("Governance and access")}</h3>
					<div class="ntc-gov"></div>
				</section>
				<section class="ntc-step" data-step="4">
					<h3><span class="ntc-step-no">4</span>${__("Connected apps")}</h3>
					<p class="ntc-muted">${__("Other Neotec apps can send their AI calls through this gateway: one set of providers, one residency policy, one usage ledger. Each app keeps its own connection as a fallback.")}</p>
					<div class="ntc-integrations"></div>
					<div class="ntc-move"></div>
				</section>
				<section class="ntc-step" data-step="5">
					<h3><span class="ntc-step-no">5</span>${__("Health check")}</h3>
					<div class="ntc-health"></div>
					<div class="ntc-mcp"></div>
				</section>
			</div>`);
		this.render_presets();
		this.render_coworkers();
		this.render_governance();
		this.render_health(s.health);
		this.render_integrations(s.integrations || [], s.move || {});
		if (s.settings.mcp_enabled) {
			this.$body.find(".ntc-mcp").html(`<p class="ntc-muted">${__("MCP endpoint for external AI clients:")}</p>
				<pre class="ntc-code">${esc(s.mcp_url)}\nAuthorization: token &lt;api_key&gt;:&lt;api_secret&gt;</pre>`);
		}
	}

	render_presets() {
		const $p = this.$body.find(".ntc-presets");
		const current = (this.state.providers || []).find((p) => p.is_default);
		Object.keys(this.state.presets).forEach((name) => {
			const p = this.state.presets[name];
			const where = { External: __("External"), "On-Premises": __("On-premises"), "In Kingdom (KSA)": __("In Kingdom") }[p.data_location];
			$(`<button type="button" class="ntc-preset ${current && current.preset === name ? "active" : ""}">
				<span class="ntc-preset-name">${esc(name)}</span><span class="ntc-preset-where ${p.data_location === "External" ? "ext" : "local"}">${esc(where)}</span>
			</button>`).on("click", (e) => {
				$p.find(".ntc-preset").removeClass("active");
				$(e.currentTarget).addClass("active");
				this.provider_form(name);
			}).appendTo($p);
		});
		if (current) {
			this.$body.find(".ntc-provider-result").html(
				`<div class="ntc-callout ${(current.last_test || "").includes("Connected") ? "success" : "warning"}">
				${esc(__("Current provider: {0} ({1}, {2}).", [current.name, current.model, current.data_location]))}<br>${esc(current.last_test || __("Not tested yet."))}</div>`);
		}
	}

	provider_form(preset) {
		const p = this.state.presets[preset];
		const $f = this.$body.find(".ntc-provider-form").empty();
		this.pf = new frappe.ui.FieldGroup({
			body: $f.get(0),
			fields: [
				{ fieldname: "base_url", fieldtype: "Data", label: __("Base URL"), default: p.base_url, reqd: 1 },
				{ fieldname: "model", fieldtype: "Data", label: __("Model"), default: p.model, reqd: 1,
					description: preset.startsWith("Azure") ? __("Your deployment name") : __("Exact model id from the provider") },
				{ fieldname: "cb", fieldtype: "Column Break" },
				{ fieldname: "api_key", fieldtype: "Password", label: __("API key"), reqd: p.needs_key ? 1 : 0,
					description: p.needs_key ? __("Stored encrypted. Never shown again.") : __("Optional for local servers") },
				{ fieldname: "data_location", fieldtype: "Select", label: __("Data location"),
					options: "External\nIn Kingdom (KSA)\nOn-Premises", default: p.data_location },
				{ fieldname: "api_version", fieldtype: "Data", label: __("API version"), default: p.api_version || "",
					hidden: preset.startsWith("Azure") ? 0 : 1 },
			],
		});
		this.pf.make();
		if (p.hint) $(`<p class="ntc-muted">${esc(__(p.hint))}</p>`).appendTo($f);
		const $bar = $(`<div class="ntc-provider-actions" style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0"></div>`).appendTo($f);
		if (p.discover) {
			$(`<button class="btn btn-default btn-sm">${__("Find models on this server")}</button>`).on("click", async () => {
				const v = this.pf.get_values(true) || {};
				if (!v.base_url) return frappe.msgprint(__("Enter the server's base URL first."));
				const r = await frappe.call({ method: API + "discover_models", freeze: true,
					args: { base_url: v.base_url, api_key: v.api_key, provider_type: p.provider_type } });
				neotec_ai_agents.pick_model(r.message || {}, (id) => this.pf.set_value("model", id));
			}).appendTo($bar);
			$(`<button class="btn btn-default btn-sm">${__("Open models guide")}</button>`)
				.on("click", () => neotec_ai_agents.show_catalogue()).appendTo($bar);
		}
		$(`<button class="btn btn-primary btn-sm">${__("Save and test connection")}</button>`).on("click", async () => {
			const v = this.pf.get_values();
			if (!v) return;
			const r = await frappe.call({ method: API + "save_provider", args: { preset, ...v }, freeze: true,
				freeze_message: __("Calling the provider…") });
			const res = r.message || {};
			const $res = this.$body.find(".ntc-provider-result").html(
				`<div class="ntc-callout ${res.ok ? "success" : "danger"}">${esc(res.message)}</div>`);
			if (res.ok) {
				$(`<button class="btn btn-default btn-sm" style="margin-top:8px">${__("Test tool calling")}</button>`)
					.on("click", async () => {
						const t = await frappe.call({ method: API + "test_tool_calling", args: { name: res.provider },
							freeze: true, freeze_message: __("Running four short checks…") });
						const m = t.message || {};
						$res.append(`<div class="ntc-callout ${m.status === "Passed" ? "success" : m.status === "Partial" ? "warning" : "danger"}">
							<strong>${esc(__("Tool-calling self-test: {0}", [__(m.status)]))}</strong><br>${esc(m.detail).replace(/\n/g, "<br>")}</div>`);
						const h2 = await frappe.call({ method: API + "health" });
						this.render_health(h2.message);
					}).appendTo($res);
			}
			const h = await frappe.call({ method: API + "health" });
			this.render_health(h.message);
		}).appendTo($bar);
	}

	render_coworkers() {
		const $c = this.$body.find(".ntc-pick").empty();
		const ar = (frappe.boot.lang || "").startsWith("ar");
		for (const cw of this.state.coworkers.filter((c) => c.chat_visible)) {
			$(`<label class="ntc-pick-row">
				<input type="checkbox" value="${esc(cw.name)}" ${cw.enabled ? "checked" : ""}>
				<span class="ntc-avatar sm">${esc(cw.icon || "🤖")}</span>
				<span><strong>${esc(cw.name)}</strong> <span class="ntc-muted">${esc(ar && cw.title_ar ? cw.title_ar : cw.title || "")}</span><br>
				<span class="ntc-muted">${esc(cw.description || "")}</span></span>
			</label>`).appendTo($c);
		}
	}

	render_governance() {
		const s = this.state.settings;
		const $g = this.$body.find(".ntc-gov").empty();
		this.gov = new frappe.ui.FieldGroup({
			body: $g.get(0),
			fields: [
				{ fieldname: "residency_mode", fieldtype: "Select", label: __("Data residency"), options: "Guarded\nStrict\nOpen",
					default: s.residency_mode || "Guarded",
					description: __("Guarded: sensitive records (employees, salaries, bank accounts) never reach an external provider. Strict: external providers are blocked.") },
				{ fieldname: "redact_external", fieldtype: "Check", label: __("Mask ID numbers, IBANs, cards, mobiles and e-mails sent to external providers"),
					default: s.redact_external == null ? 1 : s.redact_external },
				{ fieldname: "cb", fieldtype: "Column Break" },
				{ fieldname: "allow_self_approval", fieldtype: "Check", label: __("Users confirm their own coworker's changes"),
					default: s.allow_self_approval == null ? 1 : s.allow_self_approval,
					description: __("Rules with an approver role still need someone else.") },
				{ fieldname: "mcp_enabled", fieldtype: "Check", label: __("Let external AI clients use ERPNext through the MCP endpoint"), default: s.mcp_enabled || 0 },
				{ fieldname: "grant_scope", fieldtype: "Select", label: __("Give the Coworker User role to"),
					options: "\nme\nall", default: "me", description: __("'all' = every active System User. You can adjust roles later.") },
			],
		});
		this.gov.make();
		$(`<button class="btn btn-primary btn-sm">${__("Save and finish")}</button>`).on("click", async () => {
			const v = this.gov.get_values();
			const picked = this.$body.find(".ntc-pick input:checked").map((i, el) => el.value).get();
			const r = await frappe.call({ method: API + "save_setup", freeze: true,
				args: { coworkers: JSON.stringify(picked), ...v } });
			frappe.show_alert({ message: __("Saved. {0} user(s) given access.", [r.message.granted || 0]), indicator: "green" });
			await this.load();
		}).appendTo($g);
	}

	render_health(checks) {
		const $h = this.$body.find(".ntc-health").empty();
		for (const c of checks || []) {
			$h.append(`<div class="ntc-check ${c.ok ? "ok" : "bad"}"><span class="ntc-check-mark"></span>
				<span>${esc(c.label)}${c.fix ? `<br><span class="ntc-muted">${esc(c.fix)}</span>` : ""}</span></div>`);
		}
		if ((checks || []).length && checks.every((c) => c.ok)) {
			$(`<button class="btn btn-primary btn-sm">${__("Start a conversation")}</button>`)
				.on("click", () => frappe.set_route("coworker")).appendTo($h);
		}
	}
}
})();
