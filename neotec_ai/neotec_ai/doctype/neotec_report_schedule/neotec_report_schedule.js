frappe.ui.form.on("Neotec Report Schedule", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Send Now"), () =>
			frappe.call({
				method: "neotec_ai.bi.schedule.send_now",
				args: { name: frm.doc.name },
				freeze: true,
				freeze_message: __("Building and sending..."),
				callback(r) {
					if (r.message) {
						frappe.show_alert({ message: __("Sending to {0} shortly", [(r.message.recipients || []).join(", ")]), indicator: "green" });
						frm.reload_doc();
					}
				},
			})
		);
		frm.add_custom_button(__("Open {0}", [__(frm.doc.reference_type === "Neotec Dashboard" ? "Dashboard" : "Report")]), () => {
			if (frm.doc.reference_type === "Neotec Dashboard") frappe.set_route("neotec-dashboard", frm.doc.reference_name);
			else frappe.set_route("neotec-bi", frm.doc.reference_name);
		});
	},
});
