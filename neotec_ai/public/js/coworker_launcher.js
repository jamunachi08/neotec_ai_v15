// Copyright (c) 2026, Neotec Integrated Solutions
// Adds "Ask Coworker" to every form and a Ctrl+Shift+K shortcut.
(() => {
	const SKIP = /^(Coworker |AI Coworker$)/;
	const allowed = () => {
		const b = frappe.boot && frappe.boot.neotec_ai_agents;
		return b && b.enabled && b.can_use && !b.legacy;
	};
	const open = (frm) => {
		frappe.route_options = frm && !frm.is_new() ? { doctype: frm.doctype, name: frm.docname } : {};
		frappe.set_route("coworker");
	};
	$(document).on("form-refresh", (e, frm) => {
		try {
			const b = frappe.boot.neotec_ai_agents;
			if (!allowed() || !b.show_form_button || !frm || frm.is_new() || SKIP.test(frm.doctype)) return;
			if (frm.meta && frm.meta.istable) return;
			frm.add_custom_button(__("Ask Coworker"), () => open(frm));
		} catch (err) {
			console.warn("Neotec AI launcher", err);
		}
	});
	$(document).on("app_ready", () => {
		if (!allowed() || !frappe.ui.keys || !frappe.ui.keys.add_shortcut) return;
		frappe.ui.keys.add_shortcut({
			shortcut: "ctrl+shift+k",
			action: () => open(window.cur_frm),
			description: __("Ask Coworker"),
			ignore_inputs: false,
		});
	});
})();
