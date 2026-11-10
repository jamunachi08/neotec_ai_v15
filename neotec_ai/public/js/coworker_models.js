// Copyright (c) 2026, Neotec Integrated Solutions
// Neotec AI — model picker and open-model guide, shared by the provider form and the setup wizard.
frappe.provide("neotec_ai_agents");

// Shared with the setup wizard: shows the models on a server and calls back with the chosen id.
neotec_ai_agents.pick_model = function (res, on_pick) {
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	const tiers = { coworker: __("Recommended for coworkers"), light: __("Light use"), datacentre: __("Data centre") };
	const rows = (res.models || []).map((m) => `
		<tr data-id="${esc(m.id)}" tabindex="0" style="cursor:pointer">
			<td><strong>${esc(m.id)}</strong>${m.free ? ` <span class="indicator-pill orange">${__("Free tier")}</span>` : ""}</td>
			<td>${esc(m.catalogue || "")}</td>
			<td>${esc(m.tier ? tiers[m.tier] : "")}</td>
			<td>${esc([m.details, m.size].filter(Boolean).join(" · "))}</td>
		</tr>`).join("");
	const d = new frappe.ui.Dialog({
		title: __("Models on this server ({0})", [res.server || "-"]), size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "list" }],
	});
	d.fields_dict.list.$wrapper.html(rows
		? `<p class="text-muted">${__("Click a model to use it. Run Test tool calling afterwards.")}</p>
		   <div style="overflow-x:auto"><table class="table table-hover"><thead><tr>
			<th>${__("Model")}</th><th>${__("Known as")}</th><th>${__("Suitable for")}</th><th>${__("Size")}</th>
		   </tr></thead><tbody>${rows}</tbody></table></div>`
		: `<p>${esc(res.message || __("No models found."))}</p>`);
	d.fields_dict.list.$wrapper.on("click keydown", "tr[data-id]", (e) => {
		if (e.type === "keydown" && e.key !== "Enter") return;
		on_pick($(e.currentTarget).data("id"));
		d.hide();
	});
	d.show();
};

neotec_ai_agents.show_catalogue = function () {
	frappe.call({ method: "neotec_ai.agents.api.open_model_catalogue" }).then((r) => {
		const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
		const c = r.message;
		const d = new frappe.ui.Dialog({ title: __("Open models you can host yourself"), size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "t" }] });
		d.fields_dict.t.$wrapper.html(`
			<p class="text-muted">${__("Free to download. They run on your own GPU server with Ollama or vLLM, so data stays in the Kingdom. The self-test decides whether a model may run playbooks.")}</p>
			<div style="overflow-x:auto"><table class="table"><thead><tr>
				<th>${__("Model")}</th><th>${__("Licence")}</th><th>${__("GPU")}</th><th>${__("Suitable for")}</th>
				<th>${__("Arabic")}</th><th>${__("Notes")}</th></tr></thead><tbody>
			${c.models.map((m) => `<tr><td><strong>${esc(m.label)}</strong><br><span class="text-muted">${esc(m.publisher)} · ${esc(m.kind)}${m.hf_id ? "<br><code>" + esc(m.hf_id) + "</code>" : ""}</span></td>
				<td>${esc(m.licence)}</td><td>${esc(m.gpu)}</td><td>${esc(c.tiers[m.tier])}</td><td>${esc(m.arabic)}</td>
				<td>${esc(m.notes)}</td></tr>`).join("")}
			</tbody></table></div>`);
		d.show();
	});
};
