// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Channel", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Send test"), () =>
			frm.call({ method: "send_test", doc: frm.doc }).then((r) => {
				frappe.show_alert({ message: r.message || __("Sent"), indicator: "green" });
				frm.reload_doc();
			})
		);
	},
});
