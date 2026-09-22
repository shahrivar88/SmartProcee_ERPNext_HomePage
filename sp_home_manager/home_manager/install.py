import json

import frappe

from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache
from sp_home_manager.home_manager.api import MANAGER_ICON_LABEL, ensure_manager_icon

STATE_KEY = "sp_home_manager_install_state"
ICON_FIELDS = (
	"name",
	"label",
	"icon_type",
	"link_type",
	"link_to",
	"link",
	"parent_icon",
	"icon",
	"icon_image",
	"logo_url",
	"bg_color",
	"hidden",
	"idx",
	"standard",
	"restrict_removal",
)


def _capture_state():
	if frappe.db.get_default(STATE_KEY):
		return

	icon = None
	if frappe.db.exists("Desktop Icon", MANAGER_ICON_LABEL):
		icon = frappe.db.get_value("Desktop Icon", MANAGER_ICON_LABEL, ICON_FIELDS, as_dict=True)

	frappe.db.set_default(STATE_KEY, json.dumps({"manager_icon": icon}, default=str))


def after_install():
	_capture_state()
	_claim_module()
	ensure_manager_icon()
	_clear_caches()
	frappe.db.commit()


def after_migrate():
	_capture_state()
	_claim_module()
	ensure_manager_icon()
	_clear_caches()


def before_uninstall():
	state_raw = frappe.db.get_default(STATE_KEY)
	state = json.loads(state_raw) if state_raw else {}
	previous_icon = state.get("manager_icon")

	if frappe.db.exists("Desktop Icon", MANAGER_ICON_LABEL):
		frappe.delete_doc("Desktop Icon", MANAGER_ICON_LABEL, force=True, ignore_permissions=True)

	if previous_icon:
		previous_icon["doctype"] = "Desktop Icon"
		frappe.get_doc(previous_icon).insert(ignore_permissions=True)

	frappe.db.delete("DefaultValue", {"defkey": STATE_KEY})
	_clear_caches()
	frappe.db.commit()


def mark_migrated_install():
	"""Treat the legacy Home Manager icon as owned by this extracted app."""
	frappe.db.set_default(STATE_KEY, json.dumps({"manager_icon": None}))
	_claim_module()
	frappe.db.commit()


def _claim_module():
	if frappe.db.exists("Module Def", "Home Manager"):
		frappe.db.set_value("Module Def", "Home Manager", "app_name", "sp_home_manager", update_modified=False)


def _clear_caches():
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")
	for user in frappe.get_all("User", filters={"enabled": 1}, pluck="name"):
		clear_desktop_icons_cache(user)
