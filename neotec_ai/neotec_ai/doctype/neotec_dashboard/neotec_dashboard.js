frappe.ui.form.on("Neotec Dashboard", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Open Dashboard"), () => frappe.set_route("neotec-dashboard", frm.doc.name)).addClass("btn-primary");
			frm.add_custom_button(__("Schedule E-mail"), () =>
				frappe.new_doc("Neotec Report Schedule", {
					reference_type: "Neotec Dashboard",
					reference_name: frm.doc.name,
					title: frm.doc.title,
				})
			);
		}
	},
	open_dashboard(frm) {
		if (!frm.is_new()) frappe.set_route("neotec-dashboard", frm.doc.name);
	},
});
