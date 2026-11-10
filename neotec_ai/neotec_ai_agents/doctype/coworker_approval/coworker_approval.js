// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Coworker Approval", {
	refresh(frm) {
		const colors = { Pending: "orange", Executed: "green", Approved: "green", Rejected: "red", Failed: "red", Expired: "grey" };
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "blue");
		if (frm.doc.status !== "Pending") return;
		frm.call({ method: "decision_rights", doc: frm.doc }).then((r) => {
			const rights = r.message || {};
			if (!rights.can_decide) {
				frm.dashboard.set_headline(rights.why_not || __("You cannot decide this request."));
				return;
			}
			const decide = (method, label) => {
				frappe.prompt(
					[{ fieldname: "comment", fieldtype: "Small Text", label: __("Comment (optional)") }],
					(v) => frm.call({ method, doc: frm.doc, args: { comment: v.comment }, freeze: true }).then(() => frm.reload_doc()),
					label, label
				);
			};
			frm.add_custom_button(__("Approve and run"), () => decide("approve", __("Approve and run"))).addClass("btn-primary");
			frm.add_custom_button(__("Reject"), () => decide("reject", __("Reject")));
		});
		if (frm.doc.conversation) {
			frm.add_custom_button(__("Open conversation"), () => {
				frappe.route_options = { conversation: frm.doc.conversation };
				frappe.set_route("coworker");
			});
		}
	},
});
