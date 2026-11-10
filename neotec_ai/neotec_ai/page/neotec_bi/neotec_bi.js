// Neotec BI Builder: no-code report builder with AI assistance.
frappe.pages["neotec-bi"].on_page_load = function (wrapper) {
	wrapper.builder = new NeotecBuilder(wrapper);
};

frappe.pages["neotec-bi"].on_page_show = function (wrapper) {
	wrapper.builder && wrapper.builder.route_changed();
};

class NeotecBuilder {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("BI Builder"), single_column: true });
		this.esc = neotec.bi.esc;
		this.state = this.blank();
		this.make_layout();
		this.make_actions();
		this.load_meta().then(() => this.route_changed());
	}

	blank() {
		return {
			name: null, title: __("Untitled Report"), description: "", can_write: true,
			query: { source: null, joins: [], columns: [], filters: [], having: [], order_by: [], limit: 100 },
			viz: { type: "table" }, result: null, explanation: "", erp_report: null,
		};
	}

	has_report() {
		return !!(this.state.query.source || (this.state.erp_report && this.state.erp_report.report));
	}

	// ------------------------------------------------------------------ setup
	make_layout() {
		this.$root = $(`
			<div class="nbi">
				<div class="nbi-head">
					<input class="form-control nbi-title" placeholder="${__("Report title")}">
					<input class="form-control nbi-desc" placeholder="${__("Description (optional)")}">
				</div>
				<div class="nbi-ai">
					<textarea class="form-control nbi-ai-input" rows="2" placeholder="${__("Describe the report, e.g. 'Monthly revenue by item group this year as a stacked bar chart' — or ask for a change: 'only top 5 customers', 'make it a pivot by month'")}"></textarea>
					<button class="btn btn-primary btn-sm nbi-ai-go">${__("Build with AI")}</button>
					<div class="nbi-ai-note"></div>
				</div>
				<div class="nbi-main">
					<div class="nbi-left"></div>
					<div class="nbi-right">
						<div class="nbi-viz-types"></div>
						<div class="nbi-viz-options"></div>
						<div class="nbi-result-head"></div>
						<div class="nbi-result"></div>
					</div>
				</div>
			</div>`).appendTo(this.page.main);

		this.$root.find(".nbi-title").on("change", (e) => { this.state.title = e.target.value || __("Untitled Report"); this.set_dirty(); });
		this.$root.find(".nbi-desc").on("change", (e) => { this.state.description = e.target.value; this.set_dirty(); });
		this.$root.find(".nbi-ai-go").on("click", () => this.ai_build());
		this.$root.find(".nbi-ai-input").on("keydown", (e) => {
			if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); this.ai_build(); }
		});
	}

	make_actions() {
		this.page.set_primary_action(__("Save"), () => this.save(), "save");
		this.page.set_secondary_action(__("Run"), () => this.run(), "refresh");
		this.page.add_menu_item(__("New Report"), () => frappe.set_route("neotec-bi"));
		this.page.add_menu_item(__("Save As..."), () => this.save(true));
		this.page.add_menu_item(__("Add to Dashboard"), () => this.add_to_dashboard());
		this.page.add_menu_item(__("Schedule E-mail"), () => this.schedule());
		this.page.add_menu_item(__("Export Excel"), () => this.export("xlsx"));
		this.page.add_menu_item(__("Export CSV"), () => this.export("csv"));
		this.page.add_menu_item(__("Export PDF"), () => this.export("pdf"));
		this.page.add_menu_item(__("Saved Reports"), () => frappe.set_route("List", "Neotec AI Report"));
		this.page.add_menu_item(__("Dashboards"), () => frappe.set_route("neotec-dashboard"));
	}

	load_meta() {
		return frappe.call({ method: "neotec_ai.bi.api.get_builder_meta" }).then((r) => {
			this.meta = r.message;
			this.sources = {};
			(this.meta.sources || []).forEach((s) => (this.sources[s.doctype] = s));
		});
	}

	route_changed() {
		if (!this.meta) return;
		const route = frappe.get_route();
		const name = route[1] ? decodeURIComponent(route[1]) : null;
		if (frappe.route_options && frappe.route_options.definition) {
			const def = JSON.parse(frappe.route_options.definition);
			frappe.route_options = null;
			this.state = this.blank();
			this.apply_definition(def);
			this.set_dirty();
			this.render();
			this.run();
		} else if (name && name !== this.state.name) {
			this.load_report(name);
		} else if (!name && this.state.name) {
			this.state = this.blank();
			this.clear_dirty();
			this.render();
		} else {
			this.render();
		}
	}

	load_report(name) {
		frappe.call({ method: "neotec_ai.bi.api.get_report", args: { name } }).then((r) => {
			const m = r.message;
			if (!m) return;
			this.state = this.blank();
			this.state.name = m.name;
			this.state.can_write = m.can_write;
			this.apply_definition(m.definition);
			this.clear_dirty();
			this.render();
			this.run();
		});
	}

	apply_definition(def) {
		this.state.title = def.title || this.state.title;
		this.state.description = def.description || "";
		this.state.erp_report = def.erp_report ? { report: def.erp_report.report, filters: { ...(def.erp_report.filters || {}) } } : null;
		if (this.state.erp_report) this.load_erp_filters(this.state.erp_report.report);
		const q = def.query || {};
		this.state.query = {
			source: q.source || null, joins: q.joins || [], columns: q.columns || [], filters: q.filters || [],
			having: q.having || [], order_by: q.order_by || [], limit: q.limit || 100,
		};
		this.state.query.columns.forEach((c) => { if (!c.alias) c.alias = this.alias_for(c); });
		this.state.viz = def.viz || { type: "table" };
	}

	definition() {
		const base = { title: this.state.title, description: this.state.description, viz: this.state.viz };
		if (this.state.erp_report && this.state.erp_report.report) {
			return { ...base, erp_report: this.state.erp_report };
		}
		return { ...base, query: this.state.query };
	}

	load_erp_filters(report) {
		this._erp_defs = null;
		frappe.call({ method: "neotec_ai.bi.api.get_erp_report_filters", args: { report } }).then((r) => {
			const m = r.message || {};
			if (!m.ok) {
				this._erp_error = m;
				this._erp_defs = [];
			} else {
				this._erp_error = null;
				this._erp_defs = m.filters || [];
			}
			this.render_left();
		});
	}

	render_erp_left($l) {
		const er = this.state.erp_report;
		const rep = (this.meta.erp_reports || []).find((r) => r.name === er.report) || {};
		if (rep.purpose) $l.find(".nbi-section-body").first().append(`<div class="nbi-hint">${this.esc(rep.purpose)}</div>`);
		if (this._erp_error) {
			$l.append(`<div class="nbi-msg nbi-msg-lock">${this.esc(this._erp_error.message)}</div>`);
			return;
		}
		if (!this._erp_defs) {
			$l.append(`<div class="nbi-empty">${__("Loading filters...")}</div>`);
			return;
		}
		const rows = this._erp_defs.map((d) => {
			const v = er.filters[d.fieldname];
			const shown = Array.isArray(v) ? v.join(", ") : v ?? "";
			const ph = d.default !== null && d.default !== undefined && d.default !== "" ? String(d.default) : d.auto ? __("auto") : "";
			let input;
			if (d.fieldtype === "Select" && Array.isArray(d.options)) {
				input = `<select class="form-control form-control-sm" data-erp="${this.esc(d.fieldname)}">
					<option value="">${ph ? this.esc(`(${ph})`) : ""}</option>
					${d.options.filter((o) => String(o).trim()).map((o) => `<option ${String(v) === String(o) ? "selected" : ""}>${this.esc(o)}</option>`).join("")}</select>`;
			} else if (d.fieldtype === "Check") {
				input = `<input type="checkbox" data-erp="${this.esc(d.fieldname)}" ${v ? "checked" : ""}>`;
			} else {
				const type = d.fieldtype === "Date" ? "date" : "text";
				const hint = ["MultiSelectList", "Table MultiSelect"].includes(d.fieldtype) ? __("comma separated") : ph;
				input = `<input type="${type}" class="form-control form-control-sm" data-erp="${this.esc(d.fieldname)}" data-type="${this.esc(d.fieldtype)}"
					value="${this.esc(shown)}" placeholder="${this.esc(hint)}">`;
			}
			return `<div class="nbi-row"><label title="${this.esc(d.fieldname)}">${this.esc(d.label)}${d.reqd ? ' <span class="nbi-req">*</span>' : ""}</label>${input}</div>`;
		}).join("");
		$l.append(this.section(__("Report filters"), `<div class="nbi-erp-filters">${rows || `<div class="nbi-hint">${__("This report has no filters.")}</div>`}</div>
			<div class="nbi-hint">${__("Leave a filter empty to use its default (company, current fiscal year, today). Dashboard period and company filters override these.")}</div>`));
		$l.find("[data-erp]").on("change", (e) => {
			const $t = $(e.currentTarget);
			const k = $t.attr("data-erp");
			let val = $t.attr("type") === "checkbox" ? ($t.is(":checked") ? 1 : 0) : $t.val();
			if (["MultiSelectList", "Table MultiSelect"].includes($t.attr("data-type")) && typeof val === "string") {
				val = val.split(",").map((x) => x.trim()).filter(Boolean);
			}
			if (val === "" || (Array.isArray(val) && !val.length)) delete er.filters[k];
			else er.filters[k] = val;
			this.changed(false);
		});
	}

	set_dirty() {
		this.dirty = true;
		this.page.set_indicator(__("Not Saved"), "orange");
	}

	clear_dirty() {
		this.dirty = false;
		if (this.state.name) this.page.set_indicator(this.state.can_write ? __("Saved") : __("Read only"), this.state.can_write ? "green" : "gray");
		else this.page.clear_indicator();
	}

	// ------------------------------------------------------------------ helpers
	tables() {
		const q = this.state.query;
		return q.source ? [q.source].concat(q.joins.map((j) => j.doctype)) : [];
	}

	field_meta(ref) {
		if (!ref || ref === "*") return { fieldname: "*", label: __("Rows"), fieldtype: "Int" };
		const i = ref.lastIndexOf(".");
		const dt = i > 0 ? ref.slice(0, i) : this.state.query.source;
		const fn = i > 0 ? ref.slice(i + 1) : ref;
		const src = this.sources[dt];
		return (src && src.fields.find((f) => f.fieldname === fn)) || { fieldname: fn, label: fn, fieldtype: "Data" };
	}

	field_options(selected, filter) {
		const multi = this.tables().length > 1;
		return this.tables()
			.map((dt) => {
				const src = this.sources[dt];
				if (!src) return "";
				const opts = src.fields
					.filter((f) => !filter || filter(f))
					.map((f) => {
						const v = `${dt}.${f.fieldname}`;
						return `<option value="${this.esc(v)}" ${v === selected ? "selected" : ""}>${this.esc(f.label)}</option>`;
					})
					.join("");
				return multi ? `<optgroup label="${this.esc(dt)}">${opts}</optgroup>` : opts;
			})
			.join("");
	}

	alias_for(col, skip) {
		if (col.formula) return col.alias || "formula";
		const fm = this.field_meta(col.field);
		let base = [col.agg, col.date_part, col.field === "*" ? "rows" : fm.fieldname].filter(Boolean).join("_").toLowerCase().replace(/[^a-z0-9_]/g, "_");
		if (/^\d/.test(base)) base = "c_" + base;
		let alias = base, n = 2;
		const taken = this.state.query.columns.filter((c) => c !== skip).map((c) => c.alias);
		while (taken.includes(alias)) alias = `${base}_${n++}`;
		return alias;
	}

	rename_alias(oldA, newA) {
		if (!oldA || oldA === newA) return;
		const v = this.state.viz;
		const sw = (a) => (a === oldA ? newA : a);
		if (v.x) v.x = v.x.map(sw);
		if (v.y) v.y = v.y.map(sw);
		if (v.series) v.series = sw(v.series);
		if (v.column) v.column = sw(v.column);
		if (v.pivot) {
			v.pivot.rows = (v.pivot.rows || []).map(sw);
			v.pivot.columns = sw(v.pivot.columns);
			v.pivot.values = sw(v.pivot.values);
		}
		this.state.query.order_by.forEach((o) => (o.column = sw(o.column)));
		this.state.query.having.forEach((h) => (h.column = sw(h.column)));
	}

	changed(rerender_left = true) {
		this.set_dirty();
		if (rerender_left) this.render_left();
		clearTimeout(this._t);
		this._t = setTimeout(() => this.run(), 600);
	}

	// ------------------------------------------------------------------ render
	render() {
		this.page.set_title(this.state.title || __("BI Builder"));
		this.$root.find(".nbi-title").val(this.state.title).prop("disabled", false);
		this.$root.find(".nbi-desc").val(this.state.description);
		this.$root.find(".nbi-ai-go").text(this.has_report() ? __("Apply with AI") : __("Build with AI"));
		this.$root.find(".nbi-ai-note").html(this.state.explanation ? `💡 ${this.esc(this.state.explanation)}` : "");
		this.render_left();
		this.render_viz_panel();
		this.render_result();
	}

	render_left() {
		const $l = this.$root.find(".nbi-left").empty();
		const q = this.state.query;
		if (!this.meta.sources.length) {
			$l.html(`<div class="nbi-msg nbi-msg-lock">🔒 ${__("You don't have access to any data sources yet. Ask your administrator to add DocTypes to the Data Dictionary or grant you access.")}</div>`);
			return;
		}
		const er = this.state.erp_report;
		const src_opts = this.meta.sources
			.map((s) => `<option value="${this.esc(s.doctype)}" ${!er && s.doctype === q.source ? "selected" : ""}>${this.esc(__(s.doctype))}</option>`)
			.join("");
		const rep_opts = (this.meta.erp_reports || [])
			.map((r) => `<option value="report::${this.esc(r.name)}" ${er && er.report === r.name ? "selected" : ""}>${this.esc(__(r.name))}</option>`)
			.join("");
		$l.append(this.section(__("Data source"), `
			<select class="form-control form-control-sm" data-act="source"><option value="">${__("Choose data...")}</option>
				<optgroup label="${__("Data tables")}">${src_opts}</optgroup>
				${rep_opts ? `<optgroup label="${__("ERPNext reports")}">${rep_opts}</optgroup>` : ""}</select>
			${!er && q.source && this.sources[q.source] ? `<div class="nbi-hint">${this.esc(this.sources[q.source].description)}</div>` : ""}
			${this.meta.hidden_sources ? `<div class="nbi-hint">🔒 ${__("{0} more data sources are hidden because you don't have permission.", [this.meta.hidden_sources])}</div>` : ""}`));
		if (er) {
			this.render_erp_left($l);
			this.bind_left($l);
			return;
		}
		if (!q.source) {
			this.bind_left($l);
			return;
		}

		// joins
		const cands = [];
		this.tables().forEach((t) => (this.sources[t]?.joins || []).forEach((j) => {
			if (!this.tables().includes(j.doctype) && this.sources[j.doctype]) cands.push({ ...j, from: t });
		}));
		const joins_html = q.joins.map((j, i) => `
			<div class="nbi-row"><span class="nbi-chip">${this.esc(j.from)} → ${this.esc(j.doctype)} <small>(${this.esc(j.via)})</small></span>
			<select class="form-control form-control-sm nbi-w-sm" data-act="join-type" data-i="${i}">
				<option value="left" ${j.type === "left" ? "selected" : ""}>${__("keep all")}</option>
				<option value="inner" ${j.type === "inner" ? "selected" : ""}>${__("only matching")}</option></select>
			<a class="nbi-x" data-act="join-del" data-i="${i}">✕</a></div>`).join("");
		const add_join = cands.length
			? `<select class="form-control form-control-sm" data-act="join-add"><option value="">${__("+ Join related data...")}</option>${cands
				.map((c, i) => `<option value="${i}">${this.esc(c.from)} → ${this.esc(c.doctype)} (${this.esc(c.label)})</option>`).join("")}</select>`
			: "";
		this._join_cands = cands;
		$l.append(this.section(__("Joins"), joins_html + add_join));

		// columns
		const aggs = this.meta.aggs.map((a) => ({ v: a, l: { sum: __("Sum"), count: __("Count"), count_distinct: __("Count distinct"), avg: __("Average"), min: __("Min"), max: __("Max") }[a] }));
		const cols_html = q.columns.map((c, i) => {
			if (c.formula) {
				return `<div class="nbi-row nbi-col">
					<input class="form-control form-control-sm nbi-w-md" data-act="col-label" data-i="${i}" value="${this.esc(c.label || c.alias)}" placeholder="${__("Label")}">
					<input class="form-control form-control-sm" data-act="col-formula" data-i="${i}" value="${this.esc(c.formula)}" placeholder="revenue / orders">
					<a class="nbi-x" data-act="col-del" data-i="${i}">✕</a>
					<div class="nbi-alias">= ${this.esc(c.alias)}</div></div>`;
			}
			const fm = this.field_meta(c.field);
			const is_date = ["Date", "Datetime"].includes(fm.fieldtype);
			const is_num = ["Int", "Float", "Currency", "Percent", "Duration", "Rating", "Check"].includes(fm.fieldtype);
			const agg_opts = `<option value="">${__("Value")}</option>` + aggs
				.filter((a) => c.field !== "*" ? (is_num || !["sum", "avg"].includes(a.v)) : a.v === "count")
				.map((a) => `<option value="${a.v}" ${c.agg === a.v ? "selected" : ""}>${a.l}</option>`).join("");
			const part = is_date ? `<select class="form-control form-control-sm nbi-w-sm" data-act="col-part" data-i="${i}"><option value="">${__("Exact")}</option>${this.meta.date_parts
				.map((p) => `<option value="${p}" ${c.date_part === p ? "selected" : ""}>${__(frappe.utils.to_title_case(p.replace("_", " ")))}</option>`).join("")}</select>` : "";
			return `<div class="nbi-row nbi-col">
				<select class="form-control form-control-sm" data-act="col-field" data-i="${i}">
					<option value="*" ${c.field === "*" ? "selected" : ""}>${__("Number of rows")}</option>${this.field_options(c.field)}</select>
				<select class="form-control form-control-sm nbi-w-sm" data-act="col-agg" data-i="${i}">${agg_opts}</select>
				${part}
				<a class="nbi-x" data-act="col-del" data-i="${i}">✕</a>
				<div class="nbi-alias">${this.esc(c.alias)}</div></div>`;
		}).join("");
		$l.append(this.section(__("Columns"), cols_html + `
			<div class="nbi-add"><a data-act="col-add">+ ${__("Column")}</a> · <a data-act="col-add-count">+ ${__("Count")}</a> · <a data-act="col-add-formula">+ ${__("Formula")}</a></div>`));

		// filters
		const ops = this.meta.ops;
		const filt_html = q.filters.map((f, i) => {
			const fm = this.field_meta(f.field);
			return `<div class="nbi-row nbi-filter">
				<select class="form-control form-control-sm" data-act="flt-field" data-i="${i}">${this.field_options(f.field)}</select>
				<select class="form-control form-control-sm nbi-w-sm" data-act="flt-op" data-i="${i}">${ops
					.filter((o) => o !== "timespan" || ["Date", "Datetime"].includes(fm.fieldtype))
					.map((o) => `<option value="${o}" ${f.op === o ? "selected" : ""}>${o}</option>`).join("")}</select>
				${this.value_input(f, i)}
				<a class="nbi-x" data-act="flt-del" data-i="${i}">✕</a></div>`;
		}).join("");
		$l.append(this.section(__("Filters"), filt_html + `<div class="nbi-add"><a data-act="flt-add">+ ${__("Filter")}</a></div>`));

		// summary filters, sort, limit
		const agg_cols = q.columns.filter((c) => c.agg);
		const sql_cols = q.columns.filter((c) => !c.formula);
		const hav_html = q.having.map((h, i) => `<div class="nbi-row">
			<select class="form-control form-control-sm" data-act="hav-col" data-i="${i}">${agg_cols.map((c) => `<option value="${c.alias}" ${h.column === c.alias ? "selected" : ""}>${this.esc(c.alias)}</option>`).join("")}</select>
			<select class="form-control form-control-sm nbi-w-sm" data-act="hav-op" data-i="${i}">${["=", "!=", ">", "<", ">=", "<="].map((o) => `<option ${h.op === o ? "selected" : ""}>${o}</option>`).join("")}</select>
			<input class="form-control form-control-sm nbi-w-sm" type="number" data-act="hav-val" data-i="${i}" value="${this.esc(h.value)}">
			<a class="nbi-x" data-act="hav-del" data-i="${i}">✕</a></div>`).join("");
		if (agg_cols.length) {
			$l.append(this.section(__("Summary filters"), hav_html + `<div class="nbi-add"><a data-act="hav-add">+ ${__("e.g. revenue > 10,000")}</a></div>`, true));
		}
		const sort_html = q.order_by.map((o, i) => `<div class="nbi-row">
			<select class="form-control form-control-sm" data-act="sort-col" data-i="${i}">${sql_cols.map((c) => `<option value="${c.alias}" ${o.column === c.alias ? "selected" : ""}>${this.esc(c.alias)}</option>`).join("")}</select>
			<select class="form-control form-control-sm nbi-w-sm" data-act="sort-dir" data-i="${i}"><option value="asc" ${o.dir === "asc" ? "selected" : ""}>${__("Ascending")}</option><option value="desc" ${o.dir === "desc" ? "selected" : ""}>${__("Descending")}</option></select>
			<a class="nbi-x" data-act="sort-del" data-i="${i}">✕</a></div>`).join("");
		$l.append(this.section(__("Sort and limit"), sort_html + `
			<div class="nbi-add">${sql_cols.length ? `<a data-act="sort-add">+ ${__("Sort")}</a>` : ""}</div>
			<div class="nbi-row"><label class="small text-muted">${__("Max rows")}</label>
			<input class="form-control form-control-sm nbi-w-sm" type="number" min="1" data-act="limit" value="${this.esc(q.limit || 100)}"></div>`, true));

		this.bind_left($l);
	}

	value_input(f, i) {
		const v = f.value;
		if (f.op === "timespan") {
			return `<select class="form-control form-control-sm" data-act="flt-val" data-i="${i}">${this.meta.timespans
				.map((t) => `<option value="${t}" ${v === t ? "selected" : ""}>${__(frappe.utils.to_title_case(t))}</option>`).join("")}</select>`;
		}
		if (f.op === "is") {
			return `<select class="form-control form-control-sm" data-act="flt-val" data-i="${i}"><option value="set" ${v === "set" ? "selected" : ""}>${__("set")}</option><option value="not set" ${v === "not set" ? "selected" : ""}>${__("not set")}</option></select>`;
		}
		if (f.op === "between") {
			const [a, b] = Array.isArray(v) ? v : ["", ""];
			return `<input class="form-control form-control-sm nbi-w-sm" data-act="flt-val0" data-i="${i}" value="${this.esc(a)}" placeholder="${__("from")}">
				<input class="form-control form-control-sm nbi-w-sm" data-act="flt-val1" data-i="${i}" value="${this.esc(b)}" placeholder="${__("to")}">`;
		}
		const shown = Array.isArray(v) ? v.join(", ") : v ?? "";
		const ph = ["in", "not in"].includes(f.op) ? __("a, b, c") : __("value");
		return `<input class="form-control form-control-sm" data-act="flt-val" data-i="${i}" value="${this.esc(shown)}" placeholder="${ph}">`;
	}

	section(title, html, collapsed) {
		return `<details class="nbi-section" ${collapsed ? "" : "open"}><summary>${title}</summary><div class="nbi-section-body">${html}</div></details>`;
	}

	bind_left($l) {
		const q = this.state.query;
		const num = (v) => (v === "" || isNaN(Number(v)) ? v : Number(v));
		$l.find("[data-act]").on("change click", (e) => {
			const $t = $(e.currentTarget);
			const act = $t.attr("data-act");
			const i = Number($t.attr("data-i"));
			const val = $t.val();
			const is_click = e.type === "click";
			const clickers = ["join-del", "col-del", "col-add", "col-add-count", "col-add-formula", "flt-del", "flt-add", "hav-add", "hav-del", "sort-add", "sort-del"];
			if (clickers.includes(act) !== is_click) return;
			if (is_click) e.preventDefault();

			switch (act) {
				case "source":
					this.state.erp_report = null;
					this.state.result = null;
					if (val && val.startsWith("report::")) {
						const name = val.slice(8);
						this.state.query = this.blank().query;
						this.state.erp_report = { report: name, filters: {} };
						this.state.viz = { type: "table" };
						if (this.state.title === __("Untitled Report")) this.state.title = name;
						this.load_erp_filters(name);
						return this.changed();
					}
					this.state.query = { ...this.blank().query, source: val || null };
					if (val) {
						const src = this.sources[val];
						const first = src.fields.find((f) => f.fieldname !== "name") || src.fields[0];
						this.state.query.columns = [{ field: `${val}.${first.fieldname}` }];
						this.state.query.columns[0].alias = this.alias_for(this.state.query.columns[0]);
					}
					this.state.viz = { type: "table" };
					return this.changed();
				case "join-add": {
					const c = this._join_cands[Number(val)];
					if (c) q.joins.push({ doctype: c.doctype, from: c.from, via: c.via, type: c.kind === "link" ? "left" : "inner" });
					return this.changed();
				}
				case "join-type": q.joins[i].type = val; return this.changed(false);
				case "join-del": {
					const removed = new Set([q.joins[i].doctype]);
					let grew = true;
					while (grew) {
						grew = false;
						q.joins.forEach((j) => { if (removed.has(j.from) && !removed.has(j.doctype)) { removed.add(j.doctype); grew = true; } });
					}
					q.joins = q.joins.filter((j) => !removed.has(j.doctype));
					const keep = (ref) => ref === "*" || !ref || !removed.has(ref.slice(0, ref.lastIndexOf(".")));
					q.columns = q.columns.filter((c) => c.formula || keep(c.field));
					q.filters = q.filters.filter((f) => keep(f.field));
					return this.changed();
				}
				case "col-field": case "col-agg": case "col-part": {
					const c = q.columns[i];
					if (act === "col-field") { c.field = val; if (val === "*") c.agg = "count"; c.date_part = null; delete c.label; }
					if (act === "col-agg") c.agg = val || null;
					if (act === "col-part") c.date_part = val || null;
					const old = c.alias;
					c.alias = this.alias_for(c, c);
					this.rename_alias(old, c.alias);
					return this.changed();
				}
				case "col-label": q.columns[i].label = val; return this.changed(false);
				case "col-formula": q.columns[i].formula = val; return this.changed(false);
				case "col-del": {
					const gone = q.columns[i].alias;
					q.columns.splice(i, 1);
					q.order_by = q.order_by.filter((o) => o.column !== gone);
					q.having = q.having.filter((h) => h.column !== gone);
					return this.changed();
				}
				case "col-add": {
					const used = new Set(q.columns.map((c) => c.field));
					const f = this.sources[q.source].fields.find((x) => !used.has(`${q.source}.${x.fieldname}`)) || this.sources[q.source].fields[0];
					const c = { field: `${q.source}.${f.fieldname}` };
					c.alias = this.alias_for(c);
					q.columns.push(c);
					return this.changed();
				}
				case "col-add-count": {
					const c = { field: "*", agg: "count" };
					c.alias = this.alias_for(c);
					q.columns.push(c);
					return this.changed();
				}
				case "col-add-formula": {
					frappe.prompt([
						{ fieldname: "label", fieldtype: "Data", label: __("Label"), reqd: 1 },
						{ fieldname: "formula", fieldtype: "Data", label: __("Formula"), reqd: 1,
							description: __("Use column names shown under each column, e.g. {0}", [q.columns.filter((c) => !c.formula).map((c) => c.alias).slice(0, 3).join(" / ")]) },
					], (v) => {
						let alias = v.label.toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/^(\d)/, "c_$1") || "formula";
						while (q.columns.some((c) => c.alias === alias)) alias += "_2";
						q.columns.push({ formula: v.formula, label: v.label, alias });
						this.changed();
					}, __("Calculated Column"));
					return;
				}
				case "flt-field": q.filters[i].field = val; q.filters[i].op = "="; q.filters[i].value = ""; return this.changed();
				case "flt-op": {
					const f = q.filters[i];
					f.op = val;
					f.value = val === "timespan" ? "this month" : val === "is" ? "set" : val === "between" ? ["", ""] : "";
					return this.changed();
				}
				case "flt-val": {
					const f = q.filters[i];
					f.value = ["in", "not in"].includes(f.op) ? val.split(",").map((x) => x.trim()).filter(Boolean) : num(val);
					return this.changed(false);
				}
				case "flt-val0": case "flt-val1": {
					const f = q.filters[i];
					if (!Array.isArray(f.value)) f.value = ["", ""];
					f.value[act === "flt-val0" ? 0 : 1] = num(val);
					return this.changed(false);
				}
				case "flt-del": q.filters.splice(i, 1); return this.changed();
				case "flt-add": {
					const date = this.sources[q.source].fields.find((f) => ["Date", "Datetime"].includes(f.fieldtype));
					q.filters.push(date ? { field: `${q.source}.${date.fieldname}`, op: "timespan", value: "this year" } : { field: `${q.source}.name`, op: "=", value: "" });
					return this.changed();
				}
				case "hav-add": q.having.push({ column: q.columns.find((c) => c.agg).alias, op: ">", value: 0 }); return this.changed();
				case "hav-col": q.having[i].column = val; return this.changed(false);
				case "hav-op": q.having[i].op = val; return this.changed(false);
				case "hav-val": q.having[i].value = Number(val) || 0; return this.changed(false);
				case "hav-del": q.having.splice(i, 1); return this.changed();
				case "sort-add": q.order_by.push({ column: q.columns.find((c) => !c.formula).alias, dir: "desc" }); return this.changed();
				case "sort-col": q.order_by[i].column = val; return this.changed(false);
				case "sort-dir": q.order_by[i].dir = val; return this.changed(false);
				case "sort-del": q.order_by.splice(i, 1); return this.changed();
				case "limit": q.limit = Math.max(1, Number(val) || 100); return this.changed(false);
			}
		});
	}

	// ------------------------------------------------------------------ visualization panel
	render_viz_panel() {
		const v = this.state.viz;
		const $types = this.$root.find(".nbi-viz-types").empty();
		this.meta.viz_types.forEach((t) => {
			$(`<button class="btn btn-xs ${v.type === t ? "btn-primary" : "btn-default"}">${neotec.bi.VIZ_LABELS[t]}</button>`)
				.appendTo($types)
				.on("click", () => this.set_viz_type(t));
		});
		this.render_viz_options();
	}

	result_columns() {
		if (this.state.result) return this.state.result.columns;
		if (this.state.erp_report) return [];
		return this.state.query.columns.map((c) => ({
			fieldname: c.alias, label: c.label || c.alias,
			fieldtype: c.formula || c.agg ? "Float" : this.field_meta(c.field).fieldtype,
		}));
	}

	set_viz_type(t) {
		const cols = this.result_columns();
		const isnum = (c) => neotec.bi.NUMERIC.includes(c.fieldtype);
		const nums = cols.filter(isnum).map((c) => c.fieldname);
		const labs = cols.filter((c) => !isnum(c)).map((c) => c.fieldname);
		const v = { ...this.state.viz, type: t };
		if (neotec.bi.CHARTS.includes(t)) {
			v.x = (v.x && v.x.length ? v.x : labs.slice(0, 1));
			v.y = (v.y && v.y.length ? v.y : nums.slice(0, 1));
			if (["pie", "donut", "percentage"].includes(t)) { v.y = v.y.slice(0, 1); v.x = v.x.slice(0, 1); v.series = null; }
		} else if (t === "number") {
			v.column = v.column || nums[0];
			v.agg = v.agg || "sum";
		} else if (t === "pivot") {
			v.pivot = v.pivot || { rows: labs.slice(0, 1), columns: labs[1] || labs[0], values: nums[0], agg: "sum" };
		}
		this.state.viz = v;
		this.set_dirty();
		this.render_viz_panel();
		if (t === "pivot") this.run();
		else this.render_result();
	}

	render_viz_options() {
		const $o = this.$root.find(".nbi-viz-options").empty();
		const v = this.state.viz;
		const cols = this.result_columns();
		const isnum = (c) => neotec.bi.NUMERIC.includes(c.fieldtype);
		const opt = (list, sel, blank) => (blank ? `<option value="">${blank}</option>` : "") + list
			.map((c) => `<option value="${c.fieldname}" ${sel === c.fieldname ? "selected" : ""}>${this.esc(c.label)}</option>`).join("");
		const nums = cols.filter(isnum);
		const labs = cols.filter((c) => !isnum(c));
		let html = "";
		if (neotec.bi.CHARTS.includes(v.type)) {
			const single = ["pie", "donut", "percentage"].includes(v.type);
			html += `<label>${__("X axis")}</label><select class="form-control form-control-sm" data-v="x0">${opt(cols, (v.x || [])[0])}</select>`;
			if (!single) html += `<select class="form-control form-control-sm" data-v="x1">${opt(cols, (v.x || [])[1], __("(second label, optional)"))}</select>`;
			html += `<label>${__("Values")}</label><span class="nbi-checks">${nums.map((c) => `<label><input type="${single || v.series ? "radio" : "checkbox"}" name="nbi-y" data-v="y" value="${c.fieldname}" ${(v.y || []).includes(c.fieldname) ? "checked" : ""}> ${this.esc(c.label)}</label>`).join("")}</span>`;
			if (!single) {
				html += `<label>${__("Split by")}</label><select class="form-control form-control-sm" data-v="series">${opt(labs.filter((c) => !(v.x || []).includes(c.fieldname)), v.series, __("(none)"))}</select>`;
				if (v.type !== "line") html += `<label><input type="checkbox" data-v="stacked" ${v.stacked ? "checked" : ""}> ${__("Stacked")}</label>`;
			}
		} else if (v.type === "number") {
			html += `<label>${__("Value")}</label><select class="form-control form-control-sm" data-v="column">${opt(nums, v.column)}</select>
				<select class="form-control form-control-sm" data-v="agg">${["sum", "first", "avg", "min", "max", "count"].map((a) => `<option ${v.agg === a ? "selected" : ""}>${a}</option>`).join("")}</select>
				<input class="form-control form-control-sm nbi-w-sm" data-v="prefix" placeholder="${__("prefix")}" value="${this.esc(v.prefix || "")}">
				<input class="form-control form-control-sm nbi-w-sm" data-v="suffix" placeholder="${__("suffix")}" value="${this.esc(v.suffix || "")}">`;
		} else if (v.type === "pivot") {
			const p = v.pivot || {};
			html += `<label>${__("Rows")}</label><span class="nbi-checks">${labs.map((c) => `<label><input type="checkbox" data-v="p-rows" value="${c.fieldname}" ${(p.rows || []).includes(c.fieldname) ? "checked" : ""}> ${this.esc(c.label)}</label>`).join("")}</span>
				<label>${__("Columns")}</label><select class="form-control form-control-sm" data-v="p-columns">${opt(labs, p.columns)}</select>
				<label>${__("Values")}</label><select class="form-control form-control-sm" data-v="p-values">${opt(nums, p.values)}</select>
				<select class="form-control form-control-sm nbi-w-sm" data-v="p-agg">${["sum", "count", "avg", "min", "max"].map((a) => `<option ${p.agg === a ? "selected" : ""}>${a}</option>`).join("")}</select>`;
		}
		$o.html(html ? `<div class="nbi-viz-form">${html}</div>` : "");
		$o.find("[data-v]").on("change", (e) => {
			const $t = $(e.currentTarget);
			const k = $t.attr("data-v");
			const val = $t.val();
			const vz = this.state.viz;
			if (k === "x0" || k === "x1") {
				const x = [...(vz.x || [])];
				x[k === "x0" ? 0 : 1] = val;
				vz.x = x.filter(Boolean);
			} else if (k === "y") {
				vz.y = $o.find('[data-v="y"]:checked').map((_, el) => el.value).get();
			} else if (k === "stacked") vz.stacked = $t.is(":checked");
			else if (k === "series") { vz.series = val || null; if (vz.series) vz.y = (vz.y || []).slice(0, 1); }
			else if (k.startsWith("p-")) {
				vz.pivot = vz.pivot || {};
				if (k === "p-rows") vz.pivot.rows = $o.find('[data-v="p-rows"]:checked').map((_, el) => el.value).get().slice(0, 3);
				else vz.pivot[k.slice(2)] = val;
			} else vz[k] = val;
			this.set_dirty();
			if (vz.type === "pivot") this.run();
			else { this.render_viz_options(); this.render_result(); }
		});
	}

	render_result() {
		const $h = this.$root.find(".nbi-result-head").empty();
		const $r = this.$root.find(".nbi-result");
		if (this._error) return neotec.bi.render_message($r, this._error);
		const res = this.state.result;
		if (!res) {
			$r.html(`<div class="nbi-empty">${this.has_report() ? __("Run the report to see results.") : __("Choose a data source on the left, or describe the report you want above.")}</div>`);
			return;
		}
		$h.html(`<span>${__("{0} rows", [res.row_count])}</span>${res.truncated ? ` · <span class="text-warning">${__("row limit reached — raise Max rows or add filters")}</span>` : ""}`);
		this.chart = neotec.bi.render_viz($r, res, this.state.viz, { height: 380, limit: 1000 });
	}

	// ------------------------------------------------------------------ actions
	run() {
		const q = this.state.query;
		if (!this.state.erp_report && (!q.source || !q.columns.length)) return this.render_result();
		this.$root.find(".nbi-result").addClass("nbi-loading");
		return frappe.call({
			method: "neotec_ai.bi.api.run",
			type: "POST",
			args: { definition: JSON.stringify(this.definition()) },
		}).then((r) => {
			this.$root.find(".nbi-result").removeClass("nbi-loading");
			const m = r.message || {};
			if (!m.ok) {
				this._error = m;
				this.state.result = null;
			} else {
				this._error = null;
				this.state.result = m.report;
				this.state.viz = m.report.viz;
			}
			this.render_viz_panel();
			this.render_result();
		});
	}

	ai_build() {
		const prompt = (this.$root.find(".nbi-ai-input").val() || "").trim();
		if (!prompt) return frappe.show_alert({ message: __("Describe what you want first."), indicator: "orange" });
		const $btn = this.$root.find(".nbi-ai-go").prop("disabled", true).text(__("Thinking..."));
		frappe.call({
			method: "neotec_ai.bi.api.ai_build",
			type: "POST",
			args: { prompt, definition: this.has_report() ? JSON.stringify(this.definition()) : null },
		}).then((r) => {
			$btn.prop("disabled", false);
			const m = r.message || {};
			if (!m.ok) {
				this.render();
				return neotec.bi.render_message(this.$root.find(".nbi-ai-note"), m);
			}
			const keep = { name: this.state.name, can_write: this.state.can_write };
			this.state = { ...this.blank(), ...keep };
			this.apply_definition(m.report.definition);
			this.state.viz = m.report.viz;
			this.state.result = m.report;
			this.state.explanation = m.explanation;
			this._error = null;
			this.$root.find(".nbi-ai-input").val("");
			this.set_dirty();
			this.render();
		}, () => $btn.prop("disabled", false).text(__("Build with AI")));
	}

	save(as_new) {
		if (!this.has_report()) return frappe.msgprint(__("Build a report first."));
		if (!this.meta.can_save) return frappe.msgprint({ title: __("Not Permitted"), message: __("You don't have permission to save reports."), indicator: "red" });
		const update = this.state.name && this.state.can_write && !as_new;
		const go = (title) =>
			frappe.call({
				method: "neotec_ai.reports.save_report",
				type: "POST",
				args: { definition: JSON.stringify({ ...this.definition(), title }), name: update ? this.state.name : null, title },
				freeze: true,
			}).then((r) => {
				if (!r.message) return;
				this.state.title = r.message.title;
				this.state.name = r.message.name;
				this.state.can_write = true;
				this.clear_dirty();
				frappe.show_alert({ message: __("Report saved"), indicator: "green" });
				if (frappe.get_route()[1] !== r.message.name) frappe.set_route("neotec-bi", r.message.name);
				return r.message;
			});
		if (update) return go(this.state.title);
		if (this.state.name && !this.state.can_write && !as_new) {
			frappe.show_alert({ message: __("This report belongs to someone else; saving a copy."), indicator: "orange" });
		}
		return new Promise((resolve) =>
			frappe.prompt({ fieldname: "title", fieldtype: "Data", label: __("Report title"), reqd: 1, default: as_new ? `${this.state.title} (copy)` : this.state.title },
				(v) => go(v.title).then(resolve), __("Save Report"), __("Save"))
		);
	}

	async ensure_saved() {
		if (this.state.name && !this.dirty) return this.state.name;
		const r = await this.save();
		return r && r.name;
	}

	async add_to_dashboard() {
		const name = await this.ensure_saved();
		if (!name) return;
		const r = await frappe.call({ method: "neotec_ai.bi.api.get_dashboards" });
		const dashboards = ((r.message || {}).dashboards || []).map((d) => ({ label: d.title, value: d.name }));
		const d = new frappe.ui.Dialog({
			title: __("Add to Dashboard"),
			fields: [
				{ fieldname: "dashboard", fieldtype: "Select", label: __("Dashboard"), options: [{ label: __("+ New dashboard"), value: "__new" }, ...dashboards], default: dashboards[0] ? dashboards[0].value : "__new" },
				{ fieldname: "new_title", fieldtype: "Data", label: __("New dashboard title"), depends_on: "eval:doc.dashboard=='__new'" },
				{ fieldname: "width", fieldtype: "Select", label: __("Width"), options: [
					{ label: __("Quarter"), value: "3" }, { label: __("Third"), value: "4" }, { label: __("Half"), value: "6" },
					{ label: __("Two thirds"), value: "8" }, { label: __("Full"), value: "12" }], default: this.state.viz.type === "number" ? "3" : "6" },
			],
			primary_action_label: __("Add"),
			primary_action: async (v) => {
				d.hide();
				let dash = v.dashboard;
				if (dash === "__new") {
					const c = await frappe.call({ method: "neotec_ai.bi.api.create_dashboard", type: "POST", args: { title: v.new_title || __("My Dashboard") } });
					dash = c.message && c.message.name;
				}
				if (!dash) return;
				await frappe.call({ method: "neotec_ai.bi.api.add_dashboard_item", type: "POST", args: { dashboard: dash, report: name, width: v.width } });
				frappe.show_alert({ message: __("Added. {0}", [`<a href="/app/neotec-dashboard/${encodeURIComponent(dash)}">${__("Open dashboard")}</a>`]), indicator: "green" }, 8);
			},
		});
		d.show();
	}

	async schedule() {
		const name = await this.ensure_saved();
		if (name) frappe.new_doc("Neotec Report Schedule", { reference_type: "Neotec AI Report", reference_name: name, title: this.state.title });
	}

	export(fmt) {
		if (!this.has_report()) return frappe.msgprint(__("Build a report first."));
		if (this.state.name && !this.dirty) neotec.bi.export_report({ name: this.state.name }, fmt);
		else neotec.bi.export_report({ definition: this.definition() }, fmt);
	}
}
