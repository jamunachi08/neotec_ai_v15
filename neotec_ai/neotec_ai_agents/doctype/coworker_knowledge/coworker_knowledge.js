// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Knowledge", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Rebuild index"), () =>
			frm.call({ method: "rebuild_index", doc: frm.doc, freeze: true }).then((r) => {
				frappe.show_alert({ message: __("{0} passages indexed", [r.message]), indicator: "green" });
				frm.reload_doc();
			})
		);
	},
});
