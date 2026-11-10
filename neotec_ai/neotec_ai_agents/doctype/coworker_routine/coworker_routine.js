// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Routine", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Run now"), () =>
			frm.call({ method: "run_now", doc: frm.doc }).then(() =>
				frappe.show_alert({ message: __("Queued. The result arrives in your notifications."), indicator: "blue" })
			)
		);
		if (frm.doc.conversation) {
			frm.add_custom_button(__("Open history"), () => {
				frappe.route_options = { conversation: frm.doc.conversation };
				frappe.set_route("coworker");
			});
		}
	},
});
