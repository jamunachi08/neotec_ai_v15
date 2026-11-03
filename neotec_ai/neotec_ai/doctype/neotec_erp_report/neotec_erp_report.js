frappe.ui.form.on("Neotec ERP Report", {
	refresh(frm) {
		frm.trigger("show_filters");
		if (!frm.is_new()) {
			frm.add_custom_button(__("Open Report"), () => frappe.set_route("query-report", frm.doc.report));
		}
	},
	report(frm) {
		frm.trigger("show_filters");
	},
	show_filters(frm) {
		const $w = frm.get_field("filters_html").$wrapper;
		if (!frm.doc.report) return $w.empty();
		frappe.call({
			method: "neotec_ai.neotec_ai.doctype.neotec_erp_report.neotec_erp_report.get_filters_preview",
			args: { report: frm.doc.report },
			callback(r) {
				const esc = frappe.utils.escape_html;
				const defs = r.message || [];
				if (!defs.length) {
					$w.html(`<div class="text-muted small">${__("No filters detected. The AI will run the report with its defaults; add House Default Filters if it needs any.")}</div>`);
					return;
				}
				$w.html(`<table class="table table-sm table-bordered small"><thead><tr>
					<th>${__("Filter")}</th><th>${__("Type")}</th><th>${__("Options")}</th><th>${__("Required")}</th><th>${__("Default")}</th></tr></thead><tbody>
					${defs.map((d) => `<tr><td><code>${esc(d.fieldname)}</code> ${esc(d.label || "")}</td><td>${esc(d.fieldtype)}</td>
						<td>${esc(Array.isArray(d.options) ? d.options.join(", ") : d.options || "")}</td><td>${d.reqd ? "✓" : ""}</td>
						<td>${d.dynamic_default ? __("(computed)") : esc(d.default ?? "")}</td></tr>`).join("")}
					</tbody></table>
					<div class="text-muted small">${__("Company, fiscal year and date filters are filled automatically when the user doesn't specify them.")}</div>`);
			},
		});
	},
});
