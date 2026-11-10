// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Chain", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.enabled) return;
		frm.add_custom_button(__("Run now"), () =>
			frappe.prompt([{ fieldname: "parameter", fieldtype: "Data", label: __("Parameter (optional)") }], (v) =>
				frm.call({ method: "run_now", doc: frm.doc, args: v }).then(() =>
					frappe.show_alert({ message: __("Chain started. Each step appears under Coworker Run."), indicator: "blue" })
				), __("Run {0}", [frm.doc.chain_name]), __("Run"))
		).addClass("btn-primary");
		frm.add_custom_button(__("Runs"), () => frappe.set_route("List", "Coworker Run", { chain: frm.doc.name }));
	},
});
