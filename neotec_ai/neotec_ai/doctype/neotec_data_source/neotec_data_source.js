frappe.ui.form.on("Neotec Data Source", {
	refresh(frm) {
		if (!frm.doc.source_doctype) return;
		frm.add_custom_button(__("Load Fields"), () => {
			const run = (replace) =>
				frm.call({ doc: frm.doc, method: "load_fields", args: { replace } }).then((r) => {
					frm.refresh_field("data_fields");
					frm.dirty();
					frappe.show_alert({ message: __("{0} fields added", [r.message || 0]), indicator: "green" });
				});
			if ((frm.doc.data_fields || []).length) {
				frappe.confirm(
					__("Replace the current field list? Choose No to only add missing fields."),
					() => run(1),
					() => run(0)
				);
			} else {
				run(0);
			}
		});
	},

	source_doctype(frm) {
		if (!frm.doc.source_doctype) return;
		frappe.call({
			method: "neotec_ai.neotec_ai.doctype.neotec_data_source.neotec_data_source.get_doctype_info",
			args: { doctype: frm.doc.source_doctype },
			callback(r) {
				const info = r.message || {};
				frm.set_value("is_child_table", info.istable ? 1 : 0);
				frm.set_value("submitted_only", info.is_submittable || info.istable ? 1 : 0);
				if (info.istable && info.parents && info.parents.length === 1) {
					frm.set_value("parent_doctype", info.parents[0]);
				}
			},
		});
	},
});
