// Copyright (c) 2026, Neotec Integrated Solutions
// ✦ writing help on long text fields: spell check, translate, improve, formal, shorter. Preview first.
(() => {
	const TYPES = ["Small Text", "Text", "Long Text"];
	const ACTIONS = [
		["spell", __("Fix spelling")], ["translate", __("Translate Arabic ↔ English")],
		["improve", __("Improve wording")], ["formal", __("Make formal")], ["shorten", __("Make shorter")],
	];
	const on = (dt) => {
		const w = frappe.boot && frappe.boot.neotec_ai_writing;
		return w && (w.doctypes.includes("*") || w.doctypes.includes(dt));
	};
	const preview = (frm, df, action) => {
		const text = frm.doc[df.fieldname];
		if (!text || !String(text).trim()) return frappe.show_alert({ message: __("The field is empty."), indicator: "orange" });
		frappe.call({
			method: "neotec_ai.writing.transform", freeze: true, freeze_message: __("Working on the text…"),
			args: { text, action, doctype: frm.doctype, docname: frm.is_new() ? null : frm.docname },
		}).then((r) => {
			const m = r.message || {};
			if (!m.changed) return frappe.show_alert({ message: __("Nothing to change."), indicator: "green" });
			const d = new frappe.ui.Dialog({
				title: __("Preview: {0}", [__(df.label || df.fieldname)]),
				fields: [
					{ fieldtype: "HTML", fieldname: "warn" },
					{ fieldtype: "Small Text", fieldname: "before", label: __("Now"), read_only: 1, default: text },
					{ fieldtype: "Small Text", fieldname: "after", label: __("Suggested (you can edit)"), default: m.result },
				],
				primary_action_label: __("Apply"),
				primary_action: (v) => { frm.set_value(df.fieldname, v.after); d.hide(); },
			});
			if ((m.warnings || []).length) {
				d.fields_dict.warn.$wrapper.html(`<div class="alert alert-warning">${m.warnings.map(frappe.utils.escape_html).join("<br>")}</div>`);
			}
			d.show();
		});
	};
	$(document).on("form-refresh", (e, frm) => {
		try {
			if (!frm || !frm.meta || frm.meta.istable || !on(frm.doctype)) return;
			(frm.meta.fields || []).filter((df) => TYPES.includes(df.fieldtype) && !df.read_only && !df.hidden).forEach((df) => {
				const field = frm.fields_dict[df.fieldname];
				if (!field || !field.$wrapper || field.$wrapper.find(".ntc-write").length) return;
				const $btn = $(`<a class="ntc-write" title="${__("Writing help")}">✦</a>`);
				const $menu = $(`<div class="ntc-write-menu hidden"></div>`);
				ACTIONS.forEach(([a, label]) => $(`<a>${label}</a>`).on("click", () => { $menu.addClass("hidden"); preview(frm, df, a); }).appendTo($menu));
				$btn.on("click", (ev) => { ev.stopPropagation(); $menu.toggleClass("hidden"); });
				$(document).on("click", () => $menu.addClass("hidden"));
				field.$wrapper.find(".control-label").first().append($btn).append($menu);
			});
		} catch (err) {
			console.warn("Neotec AI writing", err);
		}
	});
})();
