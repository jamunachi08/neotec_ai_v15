// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Playbook", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.enabled) return;
		frm.add_custom_button(__("Run now"), () => {
			const fields = [];
			if (frm.doc.parameter_label) {
				fields.push({ fieldname: "parameter", fieldtype: "Data", label: __(frm.doc.parameter_label),
					default: frm.doc.default_parameter, description: frm.doc.parameter_help });
			}
			fields.push({ fieldname: "dry_run", fieldtype: "Check", label: __("Dry run (change nothing)"),
				default: frm.doc.mode === "Draft Changes" ? 1 : 0 });
			frappe.prompt(fields, (v) =>
				frm.call({ method: "run_now", doc: frm.doc, args: v }).then((r) => {
					frappe.show_alert({ message: __("Started. You will get a notification when it finishes."), indicator: "blue" });
					if (r.message) frappe.set_route("Form", "Coworker Run", r.message);
				}), __("Run {0}", [frm.doc.playbook_name]), __("Run"));
		}).addClass("btn-primary");
		frm.add_custom_button(__("Runs"), () => frappe.set_route("List", "Coworker Run", { playbook: frm.doc.name }));
	},
});
