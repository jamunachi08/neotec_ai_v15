import frappe
from frappe import _
from frappe.model.document import Document

# Standard columns every DocType table has, usable in the dictionary.
STANDARD_FIELDS = {
    "name": ("ID", "Data"),
    "creation": ("Created On", "Datetime"),
    "modified": ("Last Modified", "Datetime"),
    "owner": ("Created By", "Link"),
    "docstatus": ("Document Status (0 draft, 1 submitted, 2 cancelled)", "Int"),
    "parent": ("Parent Document ID", "Data"),
}

# Field types that are never exposed to the AI.
BLOCKED_FIELDTYPES = {
    "Password", "Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold",
    "Heading", "Table", "Table MultiSelect", "Attach", "Attach Image", "Image", "Signature",
    "Geolocation", "Code", "HTML Editor", "Markdown Editor", "Text Editor",
}

# Field types offered by "Load Fields" (long text is allowed manually but not auto-loaded).
AUTO_LOAD_FIELDTYPES = {
    "Data", "Link", "Dynamic Link", "Select", "Check", "Int", "Float", "Currency", "Percent",
    "Date", "Datetime", "Time", "Duration", "Rating", "Read Only", "Autocomplete",
}

MAX_AUTO_FIELDS = 40


class NeotecDataSource(Document):
    def validate(self):
        if not frappe.db.exists("DocType", self.source_doctype):
            frappe.throw(_("DocType {0} does not exist.").format(self.source_doctype))

        meta = frappe.get_meta(self.source_doctype)
        if meta.issingle:
            frappe.throw(_("Single DocTypes (settings pages) cannot be used as data sources."))
        if self.source_doctype.startswith("Neotec "):
            frappe.throw(_("Neotec AI's own DocTypes cannot be data sources."))

        self.is_child_table = 1 if meta.istable else 0
        if meta.istable:
            self.validate_parent(meta)
        else:
            self.parent_doctype = None

        if not meta.is_submittable and not meta.istable:
            self.submitted_only = 0

        if not self.data_fields:
            self.load_fields()

        self.validate_fields(meta)

    def validate_parent(self, meta):
        if not self.parent_doctype:
            frappe.throw(_("{0} is a child table. Set the Parent DocType.").format(self.source_doctype))
        parent_meta = frappe.get_meta(self.parent_doctype)
        if not any(df.options == self.source_doctype for df in parent_meta.get_table_fields()):
            frappe.throw(
                _("{0} is not a child table of {1}.").format(self.source_doctype, self.parent_doctype)
            )

    def validate_fields(self, meta):
        seen = set()
        for row in self.data_fields:
            row.fieldname = (row.fieldname or "").strip()
            if row.fieldname in seen:
                frappe.throw(_("Row {0}: field {1} is listed twice.").format(row.idx, row.fieldname))
            seen.add(row.fieldname)

            if row.fieldname in STANDARD_FIELDS:
                if row.fieldname == "parent" and not meta.istable:
                    frappe.throw(_("Row {0}: 'parent' only applies to child tables.").format(row.idx))
                row.label, row.fieldtype = STANDARD_FIELDS[row.fieldname]
                continue

            df = meta.get_field(row.fieldname)
            if not df:
                frappe.throw(
                    _("Row {0}: {1} has no field {2}.").format(row.idx, self.source_doctype, row.fieldname)
                )
            if df.fieldtype in BLOCKED_FIELDTYPES:
                frappe.throw(
                    _("Row {0}: fields of type {1} cannot be exposed.").format(row.idx, df.fieldtype)
                )
            row.label = df.label
            row.fieldtype = df.fieldtype

    @frappe.whitelist()
    def load_fields(self, replace=0):
        """Fill the field list from the DocType's meta (most useful fields first)."""
        frappe.only_for("System Manager")
        meta = frappe.get_meta(self.source_doctype)

        if int(replace or 0):
            self.data_fields = []
        existing = {row.fieldname for row in self.data_fields}

        candidates = ["parent"] if meta.istable else ["name"]
        ranked = sorted(
            (
                df for df in meta.fields
                if df.fieldtype in AUTO_LOAD_FIELDTYPES and not df.hidden and df.fieldname
            ),
            key=lambda df: (
                0 if (df.in_list_view or df.in_standard_filter or df.bold or df.reqd) else 1,
                df.idx,
            ),
        )
        candidates += [df.fieldname for df in ranked]

        added = 0
        for fieldname in candidates:
            if fieldname in existing or len(self.data_fields) >= MAX_AUTO_FIELDS:
                continue
            if fieldname in STANDARD_FIELDS:
                label, fieldtype = STANDARD_FIELDS[fieldname]
            else:
                df = meta.get_field(fieldname)
                label, fieldtype = df.label, df.fieldtype
            self.append(
                "data_fields",
                {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "enabled": 1},
            )
            existing.add(fieldname)
            added += 1
        return added


@frappe.whitelist()
def get_doctype_info(doctype):
    """Used by the form to flag child tables and suggest a parent."""
    frappe.only_for("System Manager")
    meta = frappe.get_meta(doctype)
    parents = []
    if meta.istable:
        parents = frappe.get_all(
            "DocField",
            filters={"fieldtype": ["in", ["Table", "Table MultiSelect"]], "options": doctype},
            pluck="parent",
        )
        parents += frappe.get_all(
            "Custom Field",
            filters={"fieldtype": ["in", ["Table", "Table MultiSelect"]], "options": doctype},
            pluck="dt",
        )
    return {
        "istable": meta.istable,
        "is_submittable": meta.is_submittable,
        "parents": sorted(set(parents)),
    }
