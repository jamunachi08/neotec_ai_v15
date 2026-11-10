// Copyright (c) 2026, Neotec Integrated Solutions
// Neotec AI — automation health: what needs attention, how each playbook has been running, spend.

(() => {
const API = "neotec_ai.agents.automation.health.";
const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
const STATUS_CLASS = {
	"Succeeded": "ok", "Nothing to Report": "quiet", "Failed": "bad", "Budget Exceeded": "bad",
	"Waiting Approval": "wait", "Cancelled": "quiet",
};
const SEV_CLASS = { critical: "bad", warn: "wait", info: "quiet" };
const num = (n) => (n == null ? "–" : Number(n).toLocaleString());

frappe.pages["coworker-health"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Coworker Health"), single_column: true });
	wrapper.health = new Health(wrapper);
};

frappe.pages["coworker-health"].on_page_show = function (wrapper) {
	if (wrapper.health) wrapper.health.load();
};

class Health {
	constructor(wrapper) {
		this.page = wrapper.page;
		this.days = 7;
		this.$body = $(this.page.body).addClass("ntc-page");
		this.page.set_primary_action(__("Run checks now"), () => this.runChecks(), "refresh");
		this.page.add_inner_button(__("Playbooks"), () => frappe.set_route("List", "Coworker Playbook"));
		this.page.add_inner_button(__("Runs"), () => frappe.set_route("List", "Coworker Run"));
		this.page.add_inner_button(__("Issues"), () => frappe.set_route("List", "Coworker Issue", { status: "Open" }));
		this.period = this.page.add_field({
			fieldname: "days", fieldtype: "Select", label: __("Period"), default: "7",
			options: [{ value: "1", label: __("Last 24 hours") }, { value: "7", label: __("Last 7 days") },
				{ value: "30", label: __("Last 30 days") }, { value: "90", label: __("Last 90 days") }],
			change: () => { this.days = this.period.get_value(); this.load(); },
		});
		this.load();
	}

	async load() {
		const r = await frappe.call({ method: API + "summary", args: { days: this.days } });
		this.data = r.message;
		this.render();
	}

	async runChecks() {
		const r = await frappe.call({ method: API + "run_checks", freeze: true, freeze_message: __("Checking…") });
		const m = r.message || {};
		frappe.show_alert({ message: __("{0} opened, {1} resolved, {2} open", [m.opened, m.resolved, m.open]),
			indicator: m.open ? "orange" : "green" });
		this.load();
	}

	headline(d) {
		const crit = d.issues.filter((i) => i.severity === "critical").length;
		const k = d.kpis;
		if (!k.runs && !d.issues.length) {
			return { cls: "quiet", text: __("No playbook has run yet"),
				sub: __("Open a playbook and press Run now, or schedule one with a routine.") };
		}
		if (crit) return { cls: "bad", text: __("{0} problem(s) stop automation from working", [crit]),
			sub: __("Fix these first. Each one says how.") };
		if (d.issues.length) return { cls: "wait", text: __("{0} issue(s) to look at", [d.issues.length]),
			sub: __("Nothing is blocked, but results may be incomplete.") };
		return { cls: "ok", text: __("Automation is healthy"),
			sub: __("{0} runs, {1}% finished cleanly.", [num(k.runs), k.success_rate ?? 100]) };
	}

	render() {
		const d = this.data, k = d.kpis, h = this.headline(d);
		const budget = k.month_cap
			? `<div class="ntc-h-budget">
				<div class="ntc-h-budget-bar"><span style="width:${Math.min(100, Math.round(100 * k.month_tokens / k.month_cap))}%"
					class="${k.month_tokens >= k.month_cap ? "bad" : k.month_tokens >= 0.8 * k.month_cap ? "wait" : "ok"}"></span></div>
				<div class="ntc-muted">${__("{0} of {1} tokens this month", [num(k.month_tokens), num(k.month_cap)])}</div>
			</div>` : "";
		this.$body.html(`
			<div class="ntc-health">
				<section class="ntc-h-head ${h.cls}">
					<div>
						<h2>${esc(h.text)}</h2>
						<p class="ntc-muted">${esc(h.sub)}</p>
					</div>
					<dl class="ntc-h-facts">
						<div><dt>${__("Runs")}</dt><dd>${num(k.runs)}</dd></div>
						<div><dt>${__("Clean")}</dt><dd>${k.success_rate == null ? "–" : k.success_rate + "%"}</dd></div>
						<div><dt>${__("Quality")}</dt><dd>${k.avg_score == null ? "–" : k.avg_score + "/5"}</dd></div>
						<div><dt>${__("Tokens")}</dt><dd>${num(k.tokens)}</dd></div>
						<div><dt>${__("Cost")}</dt><dd>$${Number(k.cost || 0).toFixed(2)}</dd></div>
						<div><dt>${__("Running")}</dt><dd>${num(k.running)}</dd></div>
					</dl>
					${budget}
				</section>
				${this.issues(d.issues)}
				${this.playbooks(d.playbooks)}
				<p class="ntc-muted ntc-h-foot">${__("Active: {0} playbooks, {1} routines, {2} triggers, {3} chains, {4} channels.",
					[d.counts.playbooks, d.counts.routines, d.counts.triggers, d.counts.chains, d.counts.channels])}</p>
			</div>`);
		this.$body.find("[data-issue]").on("click", (e) => frappe.set_route("Form", "Coworker Issue", $(e.currentTarget).data("issue")));
		this.$body.find("[data-run]").on("click", (e) => { e.stopPropagation(); frappe.set_route("Form", "Coworker Run", $(e.currentTarget).data("run")); });
		this.$body.find("[data-playbook]").on("click", (e) => frappe.set_route("Form", "Coworker Playbook", $(e.currentTarget).data("playbook")));
	}

	issues(rows) {
		if (!rows.length) return "";
		return `<section class="ntc-h-block">
			<h3>${__("Needs attention")}</h3>
			<ul class="ntc-h-issues">${rows.map((i) => `
				<li data-issue="${esc(i.name)}" tabindex="0">
					<span class="ntc-h-sev ${SEV_CLASS[i.severity] || "quiet"}">${esc(__(i.severity))}</span>
					<div>
						<strong>${esc(i.title)}</strong>
						${i.fix_hint ? `<div class="ntc-muted">${esc(i.fix_hint)}</div>` : ""}
					</div>
					<span class="ntc-muted">${esc(__(i.category))}${i.occurrences > 1 ? " · " + i.occurrences + "×" : ""}</span>
				</li>`).join("")}
			</ul></section>`;
	}

	playbooks(rows) {
		if (!rows.length) {
			return `<section class="ntc-h-block"><h3>${__("Playbooks")}</h3>
				<p class="ntc-muted">${__("No runs in this period.")}</p></section>`;
		}
		return `<section class="ntc-h-block">
			<h3>${__("Playbooks, least reliable first")}</h3>
			<div class="ntc-h-table-wrap"><table class="ntc-h-table">
				<thead><tr>
					<th>${__("Playbook")}</th><th>${__("Recent runs, oldest to newest")}</th>
					<th class="num">${__("Runs")}</th><th class="num">${__("Clean")}</th><th class="num">${__("Quiet")}</th>
					<th class="num">${__("Score")}</th><th class="num">${__("Avg time")}</th><th class="num">${__("Cost")}</th>
				</tr></thead>
				<tbody>${rows.map((r) => `
					<tr data-playbook="${esc(r.playbook)}" tabindex="0">
						<td><strong>${esc(r.playbook)}</strong></td>
						<td><div class="ntc-h-ribbon">${(r.ribbon || []).map((x) =>
							`<button class="${STATUS_CLASS[x.status] || "quiet"}" data-run="${esc(x.name)}"
								title="${esc(x.at + " · " + __(x.status))}" aria-label="${esc(__(x.status))}"></button>`).join("")}</div></td>
						<td class="num">${num(r.runs)}</td>
						<td class="num">${r.success_rate}%</td>
						<td class="num">${num(r.quiet)}</td>
						<td class="num">${r.avg_score == null ? "–" : r.avg_score}</td>
						<td class="num">${r.avg_duration}s</td>
						<td class="num">$${Number(r.cost || 0).toFixed(3)}</td>
					</tr>`).join("")}
				</tbody></table></div>
			<p class="ntc-muted ntc-h-legend">
				<i class="ok"></i>${__("Finished")} <i class="quiet"></i>${__("Nothing new")}
				<i class="wait"></i>${__("Waiting")} <i class="bad"></i>${__("Failed")}
			</p></section>`;
	}
}
})();
