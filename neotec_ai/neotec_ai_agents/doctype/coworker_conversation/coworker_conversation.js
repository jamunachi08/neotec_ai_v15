// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Conversation", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Open in chat"), () => {
			frappe.route_options = { conversation: frm.doc.name };
			frappe.set_route("coworker");
		});
	},
});
