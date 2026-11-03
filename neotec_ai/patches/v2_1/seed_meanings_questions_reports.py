"""v2.1: add new starter data sources, fill empty field meanings, load the sample-question library."""

import frappe

from neotec_ai.install import seed_data_dictionary, seed_sample_questions


def execute():
    seed_data_dictionary()

    for name in frappe.get_all("Neotec Data Source", pluck="name"):
        doc = frappe.get_doc("Neotec Data Source", name)
        if doc.apply_sample_meanings(overwrite=0):
            doc.flags.ignore_permissions = True
            doc.save()

    seed_sample_questions()
