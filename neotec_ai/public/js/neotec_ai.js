// Neotec AI desk assistant (Frappe v15+)
frappe.provide("neotec.ai");

neotec.ai.history = [];
neotec.ai.config = null;

$(document).on("app_ready", () => neotec.ai.init());

neotec.ai.init = function () {
	if (neotec.ai._initialised || frappe.session.user === "Guest") return;
	neotec.ai._initialised = true;

	frappe.call({
		method: "neotec_ai.api.get_client_settings",
		callback(r) {
			neotec.ai.config = r.message || { enabled: false };
			if (!neotec.ai.config.enabled) return;
			neotec.ai.add_navbar_button();
			frappe.ui.keys.add_shortcut({
				shortcut: "alt+k",
				action: () => neotec.ai.open(),
				description: __("Open {0}", [neotec.ai.config.assistant_name]),
				ignore_inputs: true,
			});
		},
	});
};

neotec.ai.add_navbar_button = function () {
	if ($(".neotec-ai-trigger").length) return;
	const name = frappe.utils.escape_html(neotec.ai.config.assistant_name);
	const $item = $(`
		<li class="nav-item neotec-ai-nav">
			<a class="nav-link neotec-ai-trigger" href="#" title="${name} (Alt+K)">
				<span class="neotec-dot"></span><span class="neotec-ai-label">${name}</span>
			</a>
		</li>`);
	// v15/v16 desk: right-hand nav list lives inside .navbar-collapse
	let $nav = $("header.navbar .navbar-collapse .navbar-nav").first();
	if (!$nav.length) $nav = $("header.navbar .navbar-nav").last();
	if (!$nav.length) return;
	$nav.prepend($item);
	$item.on("click", "a", (e) => {
		e.preventDefault();
		neotec.ai.open();
	});
};

neotec.ai.current_doc = function () {
	const route = frappe.get_route() || [];
	if (route[0] === "Form" && window.cur_frm && cur_frm.doctype === route[1] && !cur_frm.is_new()) {
		return { doctype: cur_frm.doctype, docname: cur_frm.docname };
	}
	return {};
};

neotec.ai.open = function () {
	const cfg = neotec.ai.config || {};
	const ctx = neotec.ai.current_doc();
	const esc = frappe.utils.escape_html;

	if (neotec.ai.dialog) {
		neotec.ai.dialog.ctx = ctx;
		neotec.ai.render_context();
		neotec.ai.dialog.show();
		return;
	}

	const d = new frappe.ui.Dialog({
		title: esc(cfg.assistant_name || "Neotec AI"),
		size: "large",
		fields: [
			{ fieldname: "context_html", fieldtype: "HTML" },
			{ fieldname: "thread_html", fieldtype: "HTML" },
			{
				fieldname: "prompt",
				fieldtype: "Small Text",
				label: __("Your question"),
				placeholder: __("e.g. Top 10 customers by revenue this year, or which invoices are overdue?"),
			},
		],
		primary_action_label: __("Send"),
		primary_action: () => neotec.ai.send(),
		secondary_action_label: __("New Chat"),
		secondary_action: () => {
			neotec.ai.history = [];
			neotec.ai.render_thread();
		},
	});
	d.ctx = ctx;
	d.$wrapper.addClass("neotec-modal");
	neotec.ai.dialog = d;

	d.fields_dict.thread_html.$wrapper.html(`<div class="neotec-thread"></div>`);
	d.fields_dict.prompt.$input.on("keydown", (e) => {
		if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
			e.preventDefault();
			neotec.ai.send();
		}
	});

	neotec.ai.render_context();
	neotec.ai.render_thread();
	d.show();
	setTimeout(() => d.fields_dict.prompt.$input.trigger("focus"), 200);
};

neotec.ai.render_context = function () {
	const d = neotec.ai.dialog;
	const cfg = neotec.ai.config || {};
	const esc = frappe.utils.escape_html;
	const ctx = d.ctx || {};
	const where =
		ctx.doctype && cfg.doc_context
			? `${esc(__(ctx.doctype))}: <b>${esc(ctx.docname)}</b>`
			: __("No document attached");
	const email = esc(cfg.support_email || "");
	d.fields_dict.context_html.$wrapper.html(`
		<div class="neotec-context">
			<span>${where}</span>
			<span>${cfg.db_queries ? __("Business data: on") : __("Business data: off")}
			${email ? ` · <a href="mailto:${email}">${email}</a>` : ""}</span>
		</div>`);
};

neotec.ai.render_thread = function (pending) {
	const $t = neotec.ai.dialog.$wrapper.find(".neotec-thread");
	const esc = frappe.utils.escape_html;
	if (!neotec.ai.history.length && !pending) {
		$t.html(`<div class="neotec-empty">${__(
			"Ask about your business: sales, customers, stock, payables, or the document you have open. " +
				"Answers only use data you are allowed to see."
		)}</div>`);
		return;
	}
	let html = "";
	for (const m of neotec.ai.history) {
		if (m.role === "user") {
			html += `<div class="neotec-msg neotec-user">${esc(m.content).replace(/\n/g, "<br>")}</div>`;
		} else {
			html += `<div class="neotec-msg neotec-bot">${neotec.ai.sanitize(frappe.markdown(m.content))}`;
			if (m.meta) html += `<div class="neotec-meta">${m.meta}</div>`;
			html += `</div>`;
		}
	}
	if (pending) {
		html += `<div class="neotec-msg neotec-user">${esc(pending).replace(/\n/g, "<br>")}</div>
			<div class="neotec-msg neotec-bot neotec-thinking">${__("Thinking and checking your data...")}</div>`;
	}
	$t.html(html);
	$t.scrollTop($t[0].scrollHeight);
};

neotec.ai.send = function () {
	const d = neotec.ai.dialog;
	if (d._busy) return;
	const prompt = (d.get_value("prompt") || "").trim();
	if (!prompt) return;

	const ctx = (neotec.ai.config.doc_context && d.ctx) || {};
	d._busy = true;
	d.get_primary_btn().prop("disabled", true);
	d.set_value("prompt", "");
	neotec.ai.render_thread(prompt);

	frappe.call({
		method: "neotec_ai.api.chat",
		type: "POST",
		args: {
			prompt,
			doctype: ctx.doctype || null,
			docname: ctx.docname || null,
			history: JSON.stringify(neotec.ai.history.map(({ role, content }) => ({ role, content }))),
		},
		callback(r) {
			const m = r.message || {};
			neotec.ai.history.push({ role: "user", content: prompt });
			if (m.status === "success") {
				neotec.ai.history.push({ role: "assistant", content: m.reply, meta: neotec.ai.meta_line(m) });
			} else {
				neotec.ai.history.pop();
				neotec.ai.render_thread();
				neotec.ai.show_error(m.message || __("Something went wrong."));
				d.set_value("prompt", prompt);
				return;
			}
			neotec.ai.render_thread();
		},
		error() {
			neotec.ai.render_thread();
			d.set_value("prompt", prompt);
		},
		always() {
			d._busy = false;
			d.get_primary_btn().prop("disabled", false);
		},
	});
};

neotec.ai.meta_line = function (m) {
	const esc = frappe.utils.escape_html;
	const parts = [];
	const looked = (m.queries || [])
		.filter((q) => q.doctype)
		.map((q) => (q.error ? `${esc(__(q.doctype))} (✕)` : `${esc(__(q.doctype))} (${q.rows ?? 0})`));
	if (looked.length) parts.push(__("Looked up: {0}", [looked.join(", ")]));
	parts.push(`${(m.latency_ms / 1000).toFixed(1)}s · ${m.tokens} ${__("tokens")}`);
	return parts.join(" · ");
};

neotec.ai.show_error = function (msg) {
	const $t = neotec.ai.dialog.$wrapper.find(".neotec-thread");
	$t.append(`<div class="neotec-msg neotec-error">${frappe.utils.escape_html(msg)}</div>`);
	$t.scrollTop($t[0].scrollHeight);
};

// Allow-list HTML sanitizer for model output (model output may echo database text).
neotec.ai.sanitize = function (html) {
	const ALLOWED = new Set([
		"P", "BR", "HR", "B", "STRONG", "I", "EM", "U", "S", "CODE", "PRE", "BLOCKQUOTE",
		"UL", "OL", "LI", "H1", "H2", "H3", "H4", "H5", "H6",
		"TABLE", "THEAD", "TBODY", "TR", "TH", "TD", "A", "SPAN", "DIV",
	]);
	const DROP = new Set(["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM", "INPUT", "TEXTAREA", "SVG", "MATH", "LINK", "META", "IMG", "VIDEO", "AUDIO"]);
	const doc = new DOMParser().parseFromString(`<div>${html || ""}</div>`, "text/html");
	const root = doc.body.firstChild;

	const walk = (node) => {
		for (const child of Array.from(node.childNodes)) {
			if (child.nodeType === Node.COMMENT_NODE) {
				child.remove();
				continue;
			}
			if (child.nodeType !== Node.ELEMENT_NODE) continue;
			if (DROP.has(child.tagName)) {
				child.remove();
				continue;
			}
			walk(child);
			if (!ALLOWED.has(child.tagName)) {
				child.replaceWith(...Array.from(child.childNodes));
				continue;
			}
			for (const attr of Array.from(child.attributes)) {
				const keep =
					(child.tagName === "A" && attr.name === "href" && /^(https?:|mailto:|\/app\/)/i.test(attr.value.trim())) ||
					((child.tagName === "TD" || child.tagName === "TH") && ["colspan", "rowspan", "align"].includes(attr.name));
				if (!keep) child.removeAttribute(attr.name);
			}
			if (child.tagName === "A") {
				child.setAttribute("target", "_blank");
				child.setAttribute("rel", "noopener noreferrer");
			}
			if (child.tagName === "TABLE") child.classList.add("table", "table-bordered", "table-sm");
		}
	};
	walk(root);
	return root.innerHTML;
};
