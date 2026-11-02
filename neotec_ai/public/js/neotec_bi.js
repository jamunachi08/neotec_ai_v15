// Neotec BI: shared rendering (charts, tables, pivots, KPI cards), exports and messages.
frappe.provide("neotec.bi");

neotec.bi.NUMERIC = ["Int", "Float", "Currency", "Percent", "Duration", "Rating"];
neotec.bi.CHARTS = ["bar", "line", "area", "pie", "donut", "percentage"];
neotec.bi.VIZ_LABELS = {
	table: __("Table"), bar: __("Bar"), line: __("Line"), area: __("Area"), pie: __("Pie"),
	donut: __("Donut"), percentage: __("Percentage"), number: __("Number"), pivot: __("Pivot"),
};
neotec.bi.esc = (s) => frappe.utils.escape_html(s === null || s === undefined ? "" : String(s));

neotec.bi.render_message = function ($el, m) {
	const lock = m && m.permission;
	$el.html(`<div class="nbi-msg ${lock ? "nbi-msg-lock" : "nbi-msg-error"}">
		<b>${lock ? "🔒 " + __("No access") : __("Cannot show this report")}</b><br>
		${neotec.bi.esc((m && m.message) || __("Something went wrong."))}</div>`);
};

/** Render the visualization of a report result into $el. Returns the frappe.Chart (if any). */
neotec.bi.render_viz = function ($el, report, viz, opts = {}) {
	viz = viz || report.viz || { type: "table" };
	$el.empty();
	if (!report.rows || !report.rows.length) {
		$el.html(`<div class="nbi-empty">${__("No data for these filters.")}</div>`);
		return null;
	}
	if (viz.type === "number") {
		$el.html(neotec.bi.number_html(report, viz));
		return null;
	}
	if (viz.type === "pivot" && report.pivot) {
		$el.html(neotec.bi.table_html(report.pivot, opts.limit || 500, true));
		return null;
	}
	if (neotec.bi.CHARTS.includes(viz.type)) {
		return neotec.bi.draw_chart($el, report, viz, opts.height || 260);
	}
	$el.html(neotec.bi.table_html(report, opts.limit || 200));
	return null;
};

neotec.bi.number_value = function (report, viz) {
	const i = report.columns.findIndex((c) => c.fieldname === viz.column);
	if (i < 0) return null;
	const vals = report.rows.map((r) => r[i]).filter((v) => typeof v === "number");
	const agg = viz.agg || "sum";
	if (agg === "count") return report.rows.length;
	if (!vals.length) return null;
	return {
		sum: vals.reduce((a, b) => a + b, 0),
		first: vals[0],
		avg: vals.reduce((a, b) => a + b, 0) / vals.length,
		min: Math.min(...vals),
		max: Math.max(...vals),
	}[agg];
};

neotec.bi.short_number = function (v) {
	if (v === null || v === undefined) return "–";
	const a = Math.abs(v);
	if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
	if (a >= 1e6) return (v / 1e6).toFixed(2) + "M";
	if (a >= 1e4) return (v / 1e3).toFixed(1) + "K";
	return format_number(v, null, Number.isInteger(v) ? 0 : 2);
};

neotec.bi.number_html = function (report, viz) {
	const v = neotec.bi.number_value(report, viz);
	const col = report.columns.find((c) => c.fieldname === viz.column) || {};
	const full = v === null ? "" : format_number(v, null, Number.isInteger(v) ? 0 : 2);
	return `<div class="nbi-number">
		<div class="nbi-number-value" title="${neotec.bi.esc(full)}">${neotec.bi.esc(viz.prefix || "")}${neotec.bi.short_number(v)}${neotec.bi.esc(viz.suffix || "")}</div>
		<div class="nbi-number-label">${neotec.bi.esc(col.label || "")}</div>
	</div>`;
};

neotec.bi.chart_data = function (report, viz) {
	const idx = {};
	report.columns.forEach((c, i) => (idx[c.fieldname] = i));
	const label_of = (f) => (report.columns[idx[f]] || {}).label || f;
	const xs = (viz.x || []).filter((x) => x in idx);
	const xlabel = (r) => xs.map((x) => (r[idx[x]] === null || r[idx[x]] === undefined ? "-" : r[idx[x]])).join("-");
	const single = ["pie", "donut", "percentage"].includes(viz.type);
	let rows = report.rows.slice();

	if (viz.series && viz.series in idx && !single) {
		const yi = idx[viz.y[0]];
		const si = idx[viz.series];
		const labels = [];
		const series = {};
		rows.forEach((r) => {
			const lab = String(xlabel(r));
			if (!labels.includes(lab)) labels.push(lab);
			const s = String(r[si] ?? "-");
			(series[s] = series[s] || {})[lab] = (series[s][lab] || 0) + (Number(r[yi]) || 0);
		});
		const names = Object.keys(series).slice(0, 12);
		return {
			labels: labels.slice(0, 150),
			datasets: names.map((n) => ({ name: n, values: labels.slice(0, 150).map((l) => series[n][l] || 0) })),
		};
	}

	if (single && rows.length > 12) {
		const yi = idx[viz.y[0]];
		rows.sort((a, b) => (Number(b[yi]) || 0) - (Number(a[yi]) || 0));
		const other = rows.slice(11).reduce((s, r) => s + (Number(r[yi]) || 0), 0);
		rows = rows.slice(0, 11);
		const o = new Array(report.columns.length).fill(null);
		o[idx[xs[0]]] = __("Other");
		o[yi] = other;
		rows.push(o);
	} else if (rows.length > 150) {
		rows = rows.slice(0, 150);
	}
	return {
		labels: rows.map((r) => String(xlabel(r))),
		datasets: (viz.y || []).filter((y) => y in idx).map((y) => ({ name: label_of(y), values: rows.map((r) => Number(r[idx[y]]) || 0) })),
	};
};

neotec.bi.draw_chart = function ($el, report, viz, height) {
	const data = neotec.bi.chart_data(report, viz);
	if (!data.labels.length || !data.datasets.length) {
		$el.html(`<div class="nbi-empty">${__("Pick X and Y columns to draw a chart.")}</div>`);
		return null;
	}
	const type = viz.type === "area" ? "line" : viz.type;
	const holder = $('<div class="nbi-chart"></div>').appendTo($el)[0];
	try {
		return new frappe.Chart(holder, {
			type,
			height,
			data,
			axisOptions: { xIsSeries: type === "line" ? 1 : 0, xAxisMode: data.labels.length > 12 ? "tick" : "span", shortenYAxisNumbers: 1 },
			lineOptions: { regionFill: viz.type === "area" ? 1 : 0, dotSize: 3, hideDots: data.labels.length > 40 ? 1 : 0 },
			barOptions: { spaceRatio: 0.35, stacked: viz.stacked ? 1 : 0 },
			tooltipOptions: { formatTooltipY: (v) => format_number(v, null, Number.isInteger(v) ? 0 : 2) },
			colors: ["#0d9488", "#2563eb", "#f59e0b", "#db2777", "#7c3aed", "#16a34a", "#ea580c", "#0891b2", "#64748b", "#dc2626"],
		});
	} catch (e) {
		$el.html(`<div class="nbi-empty">${__("This data cannot be drawn as a {0} chart.", [viz.type])}</div>`);
		return null;
	}
};

neotec.bi.table_html = function (table, limit, pivot) {
	const esc = neotec.bi.esc;
	const cols = table.columns;
	const isnum = (c) => neotec.bi.NUMERIC.includes(c.fieldtype);
	const fmt = (v, c) => {
		if (v === null || v === undefined || v === "") return "";
		if (typeof v === "number" && isnum(c)) return format_number(v, null, ["Int"].includes(c.fieldtype) || Number.isInteger(v) ? 0 : 2);
		if (c.fieldtype === "Date") return esc(frappe.datetime.str_to_user(String(v)));
		if (c.fieldtype === "Check") return v ? "✓" : "";
		return esc(v);
	};
	const head = cols.map((c) => `<th class="${isnum(c) ? "text-right" : ""}">${esc(c.label)}</th>`).join("");
	const rows = table.rows.slice(0, limit);
	const body = rows
		.map((r, i) => {
			const total = pivot && i === table.rows.length - 1 && r[0] === "Total";
			return `<tr class="${total ? "nbi-total" : ""}">${r.map((v, j) => `<td class="${isnum(cols[j]) ? "text-right" : ""}">${fmt(v, cols[j])}</td>`).join("")}</tr>`;
		})
		.join("");
	const more = table.rows.length > limit
		? `<div class="text-muted small mt-1">${__("Showing {0} of {1} rows. Export for all rows.", [limit, table.rows.length])}</div>`
		: "";
	return `<div class="nbi-table-wrap"><table class="table table-sm table-bordered table-hover nbi-table">
		<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>${more}`;
};

// POST a hidden form so the browser downloads the file. Exports re-run the query on the server.
neotec.bi.post_download = function (method, params) {
	const $form = $("<form>", { method: "POST", action: `/api/method/${method}`, target: "_blank" });
	Object.entries({ ...params, csrf_token: frappe.csrf_token }).forEach(([k, v]) => {
		if (v === undefined || v === null) return;
		$form.append($("<input>", { type: "hidden", name: k, value: typeof v === "string" ? v : JSON.stringify(v) }));
	});
	$form.appendTo("body").trigger("submit").remove();
};

neotec.bi.export_report = function (target, fmt) {
	const params = { fmt };
	if (target.name) params.name = target.name;
	else params.definition = JSON.stringify(target.definition);
	neotec.bi.post_download("neotec_ai.reports.export_report", params);
};

neotec.bi.export_dashboard = function (name, fmt, filters) {
	neotec.bi.post_download("neotec_ai.bi.api.export_dashboard", { name, fmt, filters: JSON.stringify(filters || {}) });
};

/** Open the BI builder with an unsaved definition (e.g. from chat). */
neotec.bi.open_in_builder = function (definition, name) {
	if (name) return frappe.set_route("neotec-bi", name);
	frappe.route_options = { definition: JSON.stringify(definition) };
	frappe.set_route("neotec-bi");
};

/** Save a definition (prompting for a title) then optionally add it to a dashboard. */
neotec.bi.save_dialog = function (definition, opts = {}) {
	return new Promise((resolve) => {
		frappe.call({ method: "neotec_ai.bi.api.get_dashboards" }).then((r) => {
			const dashboards = ((r.message || {}).dashboards || []).map((d) => ({ label: d.title, value: d.name }));
			const d = new frappe.ui.Dialog({
				title: opts.dashboard_only ? __("Add to Dashboard") : __("Save Report"),
				fields: [
					{ fieldname: "title", fieldtype: "Data", label: __("Report title"), reqd: 1, default: definition.title },
					{ fieldname: "add", fieldtype: "Check", label: __("Add to a dashboard"), default: opts.dashboard_only ? 1 : 0 },
					{ fieldname: "dashboard", fieldtype: "Select", label: __("Dashboard"), options: [{ label: __("+ New dashboard"), value: "__new" }, ...dashboards], depends_on: "add" },
					{ fieldname: "new_title", fieldtype: "Data", label: __("New dashboard title"), depends_on: "eval:doc.add && doc.dashboard=='__new'" },
					{ fieldname: "width", fieldtype: "Select", label: __("Width"), options: [
						{ label: __("Quarter"), value: "3" }, { label: __("Third"), value: "4" }, { label: __("Half"), value: "6" },
						{ label: __("Two thirds"), value: "8" }, { label: __("Full"), value: "12" }], default: "6", depends_on: "add" },
				],
				primary_action_label: __("Save"),
				async primary_action(v) {
					d.hide();
					const saved = await frappe.call({
						method: "neotec_ai.reports.save_report",
						type: "POST",
						args: { definition: JSON.stringify({ ...definition, title: v.title }), prompt: opts.prompt || "" },
						freeze: true,
					});
					const rep = saved.message;
					if (!rep) return resolve(null);
					let dash = null;
					if (v.add) {
						dash = v.dashboard;
						if (!dash || dash === "__new") {
							const c = await frappe.call({ method: "neotec_ai.bi.api.create_dashboard", type: "POST", args: { title: v.new_title || __("My Dashboard") } });
							dash = c.message && c.message.name;
						}
						if (dash) await frappe.call({ method: "neotec_ai.bi.api.add_dashboard_item", type: "POST", args: { dashboard: dash, report: rep.name, width: v.width } });
					}
					const links = [`<a href="/app/neotec-bi/${encodeURIComponent(rep.name)}">${neotec.bi.esc(rep.title)}</a>`];
					if (dash) links.push(`<a href="/app/neotec-dashboard/${encodeURIComponent(dash)}">${__("open dashboard")}</a>`);
					frappe.show_alert({ message: __("Saved: {0}", [links.join(" · ")]), indicator: "green" }, 8);
					resolve({ report: rep, dashboard: dash });
				},
			});
			d.show();
		});
	});
};

neotec.bi.markdown = function (text) {
	return neotec.ai && neotec.ai.sanitize ? neotec.ai.sanitize(frappe.markdown(text || "")) : neotec.bi.esc(text);
};
