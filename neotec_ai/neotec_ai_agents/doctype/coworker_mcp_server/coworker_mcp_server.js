// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker MCP Server", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Discover tools"), () =>
			frm.call({ method: "sync_tools", doc: frm.doc, freeze: true, freeze_message: __("Connecting…") }).then((r) => {
				frappe.show_alert({ message: __("{0} tools found. Grant them to coworkers on the AI Coworker form.", [r.message]), indicator: "green" }, 8);
				frm.reload_doc();
			})
		);
	},
});
