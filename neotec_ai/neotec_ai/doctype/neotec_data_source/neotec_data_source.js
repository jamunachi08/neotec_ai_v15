frappe.ui.form.on("Neotec Data Source", {
	refresh(frm) {
		frm.trigger("render_guide");
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
		}, __("Fields"));

		const meanings = (method, label) => {
			const run = (overwrite) =>
				frm.call({
					doc: frm.doc,
					method,
					args: { overwrite },
					freeze: true,
					freeze_message: label,
				}).then((r) => {
					frm.refresh_field("data_fields");
					if (r.message) frm.dirty();
					frappe.show_alert({
						message: __("{0} meanings filled. Review them, then Save.", [r.message || 0]),
						indicator: "green",
					});
				});
			const has_any = (frm.doc.data_fields || []).some((r) => r.description);
			if (has_any) {
				frappe.confirm(
					__("Overwrite meanings you already wrote? Choose No to fill only empty ones."),
					() => run(1),
					() => run(0)
				);
			} else {
				run(0);
			}
		};

		frm.add_custom_button(__("Fill Sample Meanings"), () =>
			meanings("fill_sample_meanings", __("Filling sample meanings...")), __("Fields"));
		frm.add_custom_button(__("Suggest Meanings (AI)"), () =>
			meanings("suggest_meanings_ai", __("Asking the AI to draft meanings...")), __("Fields"));
	},

	render_guide(frm) {
		const wrapper = frm.get_field("meaning_guide").$wrapper;
		frappe.call({
			method: "neotec_ai.neotec_ai.doctype.neotec_data_source.neotec_data_source.get_meaning_examples",
			callback(r) {
				const esc = frappe.utils.escape_html;
				const rows = (r.message || [])
					.map(([f, m]) => `<tr><td><code>${esc(f)}</code></td><td>${esc(m)}</td></tr>`)
					.join("");
				wrapper.html(`
					<details class="neotec-guide">
						<summary>${__("How to write a good 'Meaning for AI' (examples)")}</summary>
						<p class="text-muted small">${__(
							"Say what the field means in your business, its unit or currency, the values it can take, and how it should be used in reports. One sentence is enough. Fields without a meaning still work, but the AI has to guess from the label."
						)}</p>
						<table class="table table-sm table-bordered small"><thead><tr>
							<th>${__("Field")}</th><th>${__("Good meaning")}</th></tr></thead>
							<tbody>${rows}</tbody></table>
						<p class="text-muted small">${__(
							"Tip: use Fields → Fill Sample Meanings for built-in ERPNext meanings and allowed values, or Fields → Suggest Meanings (AI) to draft meanings for custom fields; then edit them."
						)}</p>
					</details>`);
			},
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
