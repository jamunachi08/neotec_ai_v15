// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("AI Coworker", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.chat_visible) {
			frm.add_custom_button(__("Open chat"), () => {
				frappe.route_options = { coworker: frm.doc.name };
				frappe.set_route("coworker");
			});
		}
		frm.add_custom_button(__("Grant all read-only tools"), () =>
			frm.call({ method: "grant_read_tools", doc: frm.doc, freeze: true }).then(() => frm.reload_doc()),
			__("Tools")
		);
	},
});
