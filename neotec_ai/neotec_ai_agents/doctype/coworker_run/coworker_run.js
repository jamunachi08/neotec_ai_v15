// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Run", {
	refresh(frm) {
		frm.disable_save();
		const color = { Succeeded: "green", "Nothing to Report": "blue", Failed: "red", Running: "orange",
			Queued: "orange", "Waiting Approval": "orange", "Budget Exceeded": "red" }[frm.doc.status];
		if (color) frm.page.set_indicator(__(frm.doc.status), color);
		if (frm.doc.conversation) {
			frm.add_custom_button(__("Open conversation"), () => {
				frappe.route_options = { conversation: frm.doc.conversation };
				frappe.set_route("coworker");
			});
		}
		if (frm.doc.playbook && !["Queued", "Running"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Run again"), () =>
				frm.call({ method: "run_again", doc: frm.doc }).then((r) => r.message && frappe.set_route("Form", "Coworker Run", r.message))
			);
		}
		if (["Queued", "Running"].includes(frm.doc.status)) setTimeout(() => frm.reload_doc(), 5000);
	},
});
