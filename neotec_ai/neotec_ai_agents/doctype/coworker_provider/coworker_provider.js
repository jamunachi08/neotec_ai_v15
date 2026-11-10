// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Provider", {
	refresh(frm) {
		frm.add_custom_button(__("Open models guide"), () => neotec_ai_agents.show_catalogue(), __("Models"));
		if (frm.is_new()) return;
		frm.add_custom_button(__("Test connection"), () => {
			frm.call({ method: "test_connection", doc: frm.doc, freeze: true, freeze_message: __("Calling the provider…") })
				.then((r) => {
					const res = r.message || {};
					frappe.show_alert({ message: res.message, indicator: res.ok ? "green" : "red" }, 10);
					frm.reload_doc();
				});
		});
		frm.add_custom_button(__("Test tool calling"), () => {
			frm.call({ method: "test_tool_calling", doc: frm.doc, freeze: true,
				freeze_message: __("Running four short checks…") }).then((r) => {
				const res = r.message || {};
				frappe.msgprint({ title: __("Tool-calling self-test: {0}", [__(res.status)]),
					message: frappe.utils.escape_html(res.detail || "").replace(/\n/g, "<br>"),
					indicator: { Passed: "green", Partial: "orange" }[res.status] || "red" });
				frm.reload_doc();
			});
		});
		if (frm.doc.provider_type === "OpenAI Compatible") {
			frm.add_custom_button(__("Find models on this server"), () =>
				frm.call({ method: "find_models", doc: frm.doc, freeze: true }).then((r) =>
					neotec_ai_agents.pick_model(r.message || {}, (id) => { frm.set_value("model", id); frm.save(); })
				), __("Models"));
		}
		const st = frm.doc.tool_test_status;
		if (st && st !== "Not tested") {
			frm.dashboard.set_headline_alert(
				__("Tool-calling self-test: {0}", [__(st)]) + (frm.doc.tool_test_model ? ` (${frappe.utils.escape_html(frm.doc.tool_test_model)})` : ""),
				{ Passed: "green", Partial: "orange", Failed: "red" }[st]);
		}
	},
});
