frappe.ui.form.on("Neotec AI Report", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.trigger("run");
		frm.add_custom_button(__("Refresh"), () => frm.trigger("run"));
		frm.add_custom_button(__("Excel"), () => neotec.ai.export_report({ name: frm.doc.name }, "xlsx"), __("Export"));
		frm.add_custom_button(__("CSV"), () => neotec.ai.export_report({ name: frm.doc.name }, "csv"), __("Export"));
		frm.add_custom_button(__("Ask AI about this report"), () => {
			neotec.ai.open();
			neotec.ai.dialog.set_value("prompt", __("About my saved report '{0}': ", [frm.doc.title]));
		});
	},

	run(frm) {
		const $w = frm.get_field("preview_html").$wrapper;
		$w.html(`<div class="text-muted small p-3">${__("Running report with live data...")}</div>`);
		frappe.call({
			method: "neotec_ai.reports.run_report",
			args: { name: frm.doc.name },
			callback(r) {
				const m = r.message || {};
				if (!m.ok) {
					$w.html(`<div class="neotec-msg neotec-error">${frappe.utils.escape_html(m.message || __("Could not run report."))}</div>`);
					return;
				}
				m.report.name = frm.doc.name;
				neotec.ai.render_report($w, m.report, { saved: true, full: true, prompt: frm.doc.source_prompt });
			},
		});
	},
});
