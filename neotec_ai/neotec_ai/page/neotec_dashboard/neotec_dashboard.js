// Neotec BI Dashboards: list, view with shared filters, drag-to-arrange, AI-added charts.
frappe.pages["neotec-dashboard"].on_page_load = function (wrapper) {
	wrapper.dash = new NeotecDashboard(wrapper);
};

frappe.pages["neotec-dashboard"].on_page_show = function (wrapper) {
	wrapper.dash && wrapper.dash.route_changed();
};

class NeotecDashboard {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Dashboards"), single_column: true });
		this.esc = neotec.bi.esc;
		this.$root = $('<div class="nbd"></div>').appendTo(this.page.main);
		this.filters = {};
	}

	route_changed() {
		const name = frappe.get_route()[1] ? decodeURIComponent(frappe.get_route()[1]) : null;
		if (name) this.load(name);
		else this.show_list();
	}

	reset_page() {
		this.page.clear_actions_menu();
		this.page.clear_primary_action();
		this.page.clear_secondary_action();
		this.page.clear_inner_toolbar();
		this.page.clear_indicator();
	}

	// ------------------------------------------------------------------ list
	show_list() {
		this.name = null;
		this.reset_page();
		this.page.set_title(__("Dashboards"));
		frappe.call({ method: "neotec_ai.bi.api.get_dashboards" }).then((r) => {
			const m = r.message || { dashboards: [] };
			if (m.can_create) this.page.set_primary_action(__("New Dashboard"), () => this.create(), "add");
			this.page.set_secondary_action(__("BI Builder"), () => frappe.set_route("neotec-bi"));
			if (!m.dashboards.length) {
				this.$root.html(`<div class="nbi-empty nbd-empty">${__("No dashboards yet. Create one, then add saved reports or ask the AI to build charts for it.")}</div>`);
				return;
			}
			this.$root.html(`<div class="nbd-list">${m.dashboards.map((d) => `
				<a class="nbd-list-card" href="/app/neotec-dashboard/${encodeURIComponent(d.name)}">
					<div class="nbd-list-title">${this.esc(d.title)}</div>
					<div class="nbd-list-desc">${this.esc(d.description || "")}</div>
					<div class="nbd-list-meta">${__("{0} items", [d.item_count])} · ${this.esc(frappe.user.full_name(d.owner))} · ${frappe.datetime.comment_when(d.modified)}</div>
				</a>`).join("")}</div>`);
		});
	}

	create() {
		frappe.prompt([
			{ fieldname: "title", fieldtype: "Data", label: __("Title"), reqd: 1 },
			{ fieldname: "description", fieldtype: "Small Text", label: __("Description") },
		], (v) => frappe.call({ method: "neotec_ai.bi.api.create_dashboard", type: "POST", args: v })
			.then((r) => r.message && frappe.set_route("neotec-dashboard", r.message.name)), __("New Dashboard"), __("Create"));
	}

	// ------------------------------------------------------------------ dashboard
	load(name) {
		frappe.call({ method: "neotec_ai.bi.api.get_dashboard", args: { name } }).then((r) => {
			const d = r.message;
			if (!d) return;
			if (this.name !== name) {
				this.filters = d.default_timespan ? { timespan: d.default_timespan } : {};
				this.editing = false;
			}
			this.name = name;
			this.d = d;
			this.render();
		}, () => this.$root.html(`<div class="nbi-msg nbi-msg-lock">🔒 ${__("This dashboard is not available to you.")}</div>`));
	}

	render() {
		const d = this.d;
		this.reset_page();
		this.page.set_title(d.title);
		if (d.can_write) {
			this.page.set_primary_action(this.editing ? __("Done") : __("Edit Layout"), () => this.toggle_edit(), this.editing ? "check" : "edit");
			this.page.add_menu_item(__("Add Saved Report"), () => this.add_report());
			this.page.add_menu_item(__("Add Chart with AI"), () => this.add_ai());
			this.page.add_menu_item(__("Add Text"), () => this.add_text());
			this.page.add_menu_item(__("Dashboard Settings / Share"), () => frappe.set_route("Form", "Neotec Dashboard", d.name));
			this.page.add_menu_item(__("Schedule E-mail"), () =>
				frappe.new_doc("Neotec Report Schedule", { reference_type: "Neotec Dashboard", reference_name: d.name, title: d.title }));
		} else {
			this.page.set_indicator(__("View only"), "gray");
		}
		this.page.set_secondary_action(__("Refresh"), () => this.load_items(), "refresh");
		this.page.add_menu_item(__("Export PDF"), () => neotec.bi.export_dashboard(d.name, "pdf", this.filters));
		this.page.add_menu_item(__("Export Excel"), () => neotec.bi.export_dashboard(d.name, "xlsx", this.filters));
		this.page.add_menu_item(__("All Dashboards"), () => frappe.set_route("neotec-dashboard"));
		this.page.add_menu_item(__("BI Builder"), () => frappe.set_route("neotec-bi"));

		const ts = this.filters.timespan || "";
		const custom = !ts && this.filters.from_date;
		this.$root.html(`
			${d.description ? `<div class="nbd-desc">${this.esc(d.description)}</div>` : ""}
			<div class="nbd-filters">
				<label>${__("Period")}</label>
				<select class="form-control form-control-sm" data-f="timespan">
					<option value="">${__("As defined in each report")}</option>
					${d.timespans.map((t) => `<option value="${t}" ${ts === t ? "selected" : ""}>${__(frappe.utils.to_title_case(t))}</option>`).join("")}
					<option value="__custom" ${custom ? "selected" : ""}>${__("Custom range...")}</option>
				</select>
				<span class="nbd-range" style="${custom ? "" : "display:none"}">
					<input type="date" class="form-control form-control-sm" data-f="from_date" value="${this.esc(this.filters.from_date || "")}">
					<input type="date" class="form-control form-control-sm" data-f="to_date" value="${this.esc(this.filters.to_date || "")}">
				</span>
				${d.enable_company_filter ? `<label>${__("Company")}</label><select class="form-control form-control-sm" data-f="company">
					<option value="">${__("All")}</option>${d.companies.map((c) => `<option ${this.filters.company === c ? "selected" : ""}>${this.esc(c)}</option>`).join("")}</select>` : ""}
				${this.editing ? `<span class="nbd-edit-hint">${__("Drag cards to reorder · change width/height · ✕ removes")}</span>` : ""}
			</div>
			<div class="nbd-grid ${this.editing ? "nbd-editing" : ""}"></div>`);

		this.$root.find("[data-f]").on("change", (e) => {
			const k = $(e.currentTarget).attr("data-f");
			const v = $(e.currentTarget).val();
			if (k === "timespan") {
				if (v === "__custom") { this.$root.find(".nbd-range").show(); return; }
				this.$root.find(".nbd-range").hide();
				this.filters.timespan = v || null;
				delete this.filters.from_date;
				delete this.filters.to_date;
			} else {
				this.filters[k] = v || null;
				if (k !== "company") this.filters.timespan = null;
				if ((k === "from_date" || k === "to_date") && !(this.filters.from_date && this.filters.to_date)) return;
			}
			this.load_items();
		});
		this.render_grid();
	}

	render_grid() {
		const $g = this.$root.find(".nbd-grid").empty();
		if (!this.d.items.length) {
			$g.html(`<div class="nbi-empty nbd-empty" style="grid-column: span 12">${this.d.can_write
				? __("This dashboard is empty. Use the menu: Add Saved Report, or Add Chart with AI.")
				: __("This dashboard is empty.")}</div>`);
			return;
		}
		this.d.items.forEach((it) => {
			const $c = $(`
				<div class="nbd-card nbd-h-${(it.height || "Medium").toLowerCase()}" style="grid-column: span ${it.width}" data-item="${this.esc(it.name)}" ${this.editing ? 'draggable="true"' : ""}>
					<div class="nbd-card-head">
						<span class="nbd-card-title">${this.esc(it.title || "")}</span>
						<span class="nbd-card-tools">
							${this.editing ? `
								<select class="nbd-w" title="${__("Width")}">${["3", "4", "6", "8", "12"].map((w) => `<option ${String(it.width) === w ? "selected" : ""}>${w}</option>`).join("")}</select>
								<select class="nbd-hsel" title="${__("Height")}">${["Small", "Medium", "Large"].map((h) => `<option value="${h}" ${it.height === h ? "selected" : ""}>${__(h)}</option>`).join("")}</select>
								<a class="nbd-del" title="${__("Remove")}">✕</a>`
								: it.report ? `<a class="nbd-open" title="${__("Open in BI Builder")}">↗</a><a class="nbd-xl" title="${__("Export Excel")}">⤓</a>` : ""}
						</span>
					</div>
					<div class="nbd-card-body"><div class="nbi-empty">${__("Loading...")}</div></div>
				</div>`).appendTo($g);
			$c.find(".nbd-open").on("click", () => frappe.set_route("neotec-bi", it.report));
			$c.find(".nbd-xl").on("click", () => neotec.bi.export_report({ name: it.report }, "xlsx"));
			$c.find(".nbd-del").on("click", () => this.remove_item(it));
			$c.find(".nbd-w").on("change", (e) => { it.width = e.target.value; $c.css("grid-column", `span ${it.width}`); this.layout_dirty = true; this.redraw_item(it, $c); });
			$c.find(".nbd-hsel").on("change", (e) => {
				$c.removeClass(`nbd-h-${(it.height || "Medium").toLowerCase()}`);
				it.height = e.target.value;
				$c.addClass(`nbd-h-${it.height.toLowerCase()}`);
				this.layout_dirty = true;
				this.redraw_item(it, $c);
			});
		});
		if (this.editing) this.enable_drag($g);
		this.load_items();
	}

	height_px(it) {
		return { Small: 160, Medium: 260, Large: 380 }[it.height || "Medium"];
	}

	load_items() {
		this.d.items.forEach((it) => {
			const $c = this.$root.find(`.nbd-card[data-item="${CSS.escape(it.name)}"]`);
			const $b = $c.find(".nbd-card-body");
			$b.addClass("nbi-loading");
			frappe.call({
				method: "neotec_ai.bi.api.run_dashboard_item",
				type: "POST",
				args: { dashboard: this.name, item: it.name, filters: JSON.stringify(this.filters) },
			}).then((r) => {
				$b.removeClass("nbi-loading");
				const m = r.message || {};
				it._result = m;
				this.redraw_item(it, $c);
			});
		});
	}

	redraw_item(it, $c) {
		const m = it._result;
		if (!m) return;
		const $b = $c.find(".nbd-card-body");
		if (m.text !== undefined) {
			$b.html(`<div class="nbd-text">${neotec.bi.markdown(m.text)}</div>`);
			return;
		}
		if (!m.ok) return neotec.bi.render_message($b, m);
		if (!it.title) $c.find(".nbd-card-title").text(m.report.title);
		const viz = m.report.viz || {};
		setTimeout(() => neotec.bi.render_viz($b, m.report, viz, { height: this.height_px(it) - 10, limit: 100 }), 0);
	}

	// ------------------------------------------------------------------ editing
	toggle_edit() {
		if (this.editing && this.layout_dirty) {
			this.save_layout().then(() => { this.editing = false; this.render(); });
			return;
		}
		this.editing = !this.editing;
		this.render();
	}

	enable_drag($g) {
		let dragging = null;
		$g.find(".nbd-card").each((_, el) => {
			el.addEventListener("dragstart", (e) => { dragging = el; el.classList.add("nbd-dragging"); e.dataTransfer.effectAllowed = "move"; });
			el.addEventListener("dragend", () => { el.classList.remove("nbd-dragging"); dragging = null; });
			el.addEventListener("dragover", (e) => {
				e.preventDefault();
				if (!dragging || dragging === el) return;
				const rect = el.getBoundingClientRect();
				const after = e.clientX > rect.left + rect.width / 2 || e.clientY > rect.bottom - 10;
				el.parentNode.insertBefore(dragging, after ? el.nextSibling : el);
			});
			el.addEventListener("drop", (e) => {
				e.preventDefault();
				const order = $g.find(".nbd-card").map((_, c) => c.getAttribute("data-item")).get();
				this.d.items.sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name));
				this.layout_dirty = true;
			});
		});
	}

	save_layout() {
		return frappe.call({
			method: "neotec_ai.bi.api.save_dashboard_layout",
			type: "POST",
			args: { name: this.name, items: JSON.stringify(this.d.items.map((i) => ({ name: i.name, width: i.width, height: i.height }))) },
		}).then(() => {
			this.layout_dirty = false;
			frappe.show_alert({ message: __("Layout saved"), indicator: "green" });
		});
	}

	remove_item(it) {
		frappe.confirm(__("Remove '{0}' from this dashboard? The saved report itself is kept.", [it.title || it.report || __("item")]), () =>
			frappe.call({ method: "neotec_ai.bi.api.remove_dashboard_item", type: "POST", args: { dashboard: this.name, item: it.name } })
				.then(() => this.load(this.name)));
	}

	add_report() {
		const d = new frappe.ui.Dialog({
			title: __("Add Saved Report"),
			fields: [
				{ fieldname: "report", fieldtype: "Link", options: "Neotec AI Report", label: __("Report"), reqd: 1 },
				{ fieldname: "title", fieldtype: "Data", label: __("Title (optional)") },
				{ fieldname: "width", fieldtype: "Select", label: __("Width"), options: ["3", "4", "6", "8", "12"], default: "6" },
				{ fieldname: "height", fieldtype: "Select", label: __("Height"), options: ["Small", "Medium", "Large"], default: "Medium" },
			],
			primary_action_label: __("Add"),
			primary_action: (v) => {
				d.hide();
				frappe.call({ method: "neotec_ai.bi.api.add_dashboard_item", type: "POST", args: { dashboard: this.name, ...v } })
					.then(() => this.load(this.name));
			},
		});
		d.show();
	}

	add_ai() {
		const d = new frappe.ui.Dialog({
			title: __("Add Chart with AI"),
			fields: [
				{ fieldname: "prompt", fieldtype: "Small Text", label: __("What should the chart show?"), reqd: 1,
					description: __("e.g. 'Total sales this month as a number', 'Top 10 items by revenue as a bar chart', 'Receivables by customer group as a donut'") },
				{ fieldname: "width", fieldtype: "Select", label: __("Width"), options: ["3", "4", "6", "8", "12"], default: "6" },
			],
			primary_action_label: __("Build"),
			primary_action: (v) => {
				d.hide();
				frappe.call({
					method: "neotec_ai.bi.api.ai_add_to_dashboard",
					type: "POST",
					args: { dashboard: this.name, prompt: v.prompt, width: v.width },
					freeze: true,
					freeze_message: __("Building the chart..."),
				}).then((r) => {
					const m = r.message || {};
					if (!m.ok) return frappe.msgprint({ title: m.permission ? __("No access") : __("Could not build"), message: this.esc(m.message), indicator: "orange" });
					if (m.explanation) frappe.show_alert({ message: this.esc(m.explanation), indicator: "green" }, 8);
					this.load(this.name);
				});
			},
		});
		d.show();
	}

	add_text() {
		frappe.prompt([
			{ fieldname: "title", fieldtype: "Data", label: __("Title") },
			{ fieldname: "content", fieldtype: "Small Text", label: __("Text (Markdown)"), reqd: 1 },
			{ fieldname: "width", fieldtype: "Select", label: __("Width"), options: ["3", "4", "6", "8", "12"], default: "12" },
		], (v) => frappe.call({ method: "neotec_ai.bi.api.add_dashboard_item", type: "POST", args: { dashboard: this.name, item_type: "Text", ...v } })
			.then(() => this.load(this.name)), __("Add Text"), __("Add"));
	}
}
