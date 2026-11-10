frappe.ui.form.on("Neotec AI Report", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Open in BI Builder"), () => frappe.set_route("neotec-bi", frm.doc.name)).addClass("btn-primary");
		frm.add_custom_button(__("Refresh"), () => frm.trigger("run"));
		["xlsx", "csv", "pdf"].forEach((fmt) =>
			frm.add_custom_button(fmt === "xlsx" ? __("Excel") : fmt.toUpperCase(), () => neotec.bi.export_report({ name: frm.doc.name }, fmt), __("Export"))
		);
		frm.add_custom_button(__("Schedule E-mail"), () =>
			frappe.new_doc("Neotec Report Schedule", { reference_type: "Neotec AI Report", reference_name: frm.doc.name, title: frm.doc.title })
		);
		frm.trigger("run");
	},

	run(frm) {
		const $w = frm.get_field("preview_html").$wrapper;
		$w.html(`<div class="text-muted small p-3">${__("Running report with live data...")}</div>`);
		frappe.call({
			method: "neotec_ai.reports.run_report",
			args: { name: frm.doc.name },
			callback(r) {
				const m = r.message || {};
				if (!m.ok) return neotec.bi.render_message($w, m);
				neotec.ai.render_report($w, m.report, { saved: true, full: true, prompt: frm.doc.source_prompt });
			},
		});
	},
});
