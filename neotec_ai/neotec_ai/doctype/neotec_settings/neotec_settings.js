frappe.ui.form.on("Neotec Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save the settings first."));
				return;
			}
			frappe.call({
				method: "neotec_ai.api.test_connection",
				freeze: true,
				freeze_message: __("Contacting provider..."),
				callback(r) {
					const m = r.message || {};
					frappe.msgprint({
						title: m.ok ? __("Connection OK") : __("Connection Failed"),
						indicator: m.ok ? "green" : "red",
						message: frappe.utils.escape_html(m.message || ""),
					});
				},
			});
		});
		frm.add_custom_button(__("Data Dictionary"), () => frappe.set_route("List", "Neotec Data Source"));
		frm.add_custom_button(__("Sample Questions"), () => frappe.set_route("List", "Neotec Sample Question"));
		frm.add_custom_button(__("Saved Reports"), () => frappe.set_route("List", "Neotec AI Report"));
		frm.add_custom_button(__("AI Logs"), () => frappe.set_route("List", "Neotec AI Log"));
	},

	provider(frm) {
		frappe.call({
			method: "neotec_ai.neotec_ai.doctype.neotec_settings.neotec_settings.get_suggested_model",
			args: { provider: frm.doc.provider },
			callback(r) {
				if (r.message) frm.set_value("model", r.message);
			},
		});
	},
});
