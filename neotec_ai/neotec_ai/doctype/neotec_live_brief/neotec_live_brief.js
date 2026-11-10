// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Neotec Live Brief", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Refresh now"), () =>
			frappe.call({ method: "neotec_ai.briefs.refresh_now", args: { brief: frm.doc.name } })
				.then(() => frappe.show_alert({ message: __("Refreshing — this page updates when it is done."), indicator: "blue" })));
		if (frm.doc.conversation) frm.add_custom_button(__("Open conversation"), () => frappe.set_route("coworker", { conversation: frm.doc.conversation }));
		frappe.realtime.off("neotec_ai_brief");
		frappe.realtime.on("neotec_ai_brief", (m) => { if (m.brief === frm.doc.name) frm.reload_doc(); });
	},
});
