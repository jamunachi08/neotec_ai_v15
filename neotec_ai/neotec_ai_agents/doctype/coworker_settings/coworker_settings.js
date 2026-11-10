// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Open setup wizard"), () => frappe.set_route("coworker-setup"));
		frm.add_custom_button(__("Open chat"), () => frappe.set_route("coworker"));
		if (frm.doc.mcp_enabled) {
			frm.set_df_property("mcp_endpoint", "description",
				__("Full URL: {0}. Clients authenticate with the user's API key: Authorization: token KEY:SECRET",
					[frappe.urllib.get_full_url("/api/method/neotec_ai.agents.mcp.server.handle")]));
		}
	},
});
