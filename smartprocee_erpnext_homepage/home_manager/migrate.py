"""Idempotent backfill for category order. Gaps stay inside the supported range."""

import frappe
from frappe.utils import cint

from smartprocee_erpnext_homepage.home_manager.api import GAP_MAX, GAP_MIN, UNCATEGORIZED


def sync_home_layout():
	if not frappe.db.exists("DocType", "SP Home Settings"):
		return
	if not frappe.get_meta("SP Home Settings").has_field("categories"):
		return

	settings = frappe.get_single("SP Home Settings")
	changed = _remap_gaps(settings)
	changed = _ensure_categories(settings) or changed
	if changed:
		settings.save(ignore_permissions=True)


def _remap_gaps(settings):
	changed = False
	for fieldname in ("gap_x", "gap_y"):
		value = settings.get(fieldname)
		if value in (None, ""):
			continue
		number = cint(value)
		clamped = min(GAP_MAX, max(GAP_MIN, number))
		if clamped != number:
			settings.set(fieldname, clamped)
			changed = True
	return changed


def _ensure_categories(settings):
	existing = _names(settings.categories)
	styles = list(settings.styles or [])
	derived = _visible_category_order(styles)
	changed = False

	if not existing:
		for name in derived:
			settings.append("categories", {"category_name": name})
		if derived or styles:
			changed = True
		changed = _resequence_within_categories(settings) or changed
		return changed

	for name in derived:
		if name not in existing:
			settings.append("categories", {"category_name": name})
			existing.append(name)
			changed = True
	return changed


def _visible_category_order(styles):
	visible = [row for row in styles if not cint(row.hidden)]
	visible.sort(key=lambda row: (cint(row.sequence), row.desktop_icon or ""))
	ordered = []
	for row in visible:
		name = (row.category or UNCATEGORIZED).strip() or UNCATEGORIZED
		if name not in ordered:
			ordered.append(name)
	for row in styles:
		name = (row.category or UNCATEGORIZED).strip() or UNCATEGORIZED
		if name not in ordered:
			ordered.append(name)
	return ordered


def _resequence_within_categories(settings):
	"""First backfill only. Hidden rows sort after visible rows, so they cannot lead a category."""
	groups = {}
	for row in settings.styles or []:
		name = (row.category or UNCATEGORIZED).strip() or UNCATEGORIZED
		groups.setdefault(name, []).append(row)
	changed = False
	for rows in groups.values():
		rows.sort(key=lambda row: (cint(row.hidden), cint(row.sequence), row.desktop_icon or ""))
		for index, row in enumerate(rows, start=1):
			if cint(row.sequence) != index:
				row.sequence = index
				changed = True
	return changed


def _names(rows):
	names = []
	for row in rows or []:
		name = (row.category_name or "").strip()
		if name and name not in names:
			names.append(name)
	return names
