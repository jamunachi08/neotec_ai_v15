// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Trigger", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Test on a document"), () =>
			frappe.prompt([
				{ fieldname: "name", fieldtype: "Link", options: frm.doc.document_type, label: __("Document"), reqd: 1 },
				{ fieldname: "start", fieldtype: "Check", label: __("Also start the playbook") },
			], (v) => frm.call({ method: "test_on", doc: frm.doc, args: v }).then((r) =>
				frappe.msgprint({ title: __("Trigger test"), message: r.message, indicator: "blue" })
			), __("Test trigger"), __("Test"))
		);
	},
});
