import json
import re

import frappe
from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache
from frappe.utils import cint

from smartprocee_erpnext_homepage.home_manager.labels import display_label

MANAGER_ICON_LABEL = "مدیریت صفحه اصلی"
MANAGER_ICON_LINK = "/app/home-manager"
UNCATEGORIZED = "عمومی"
ICON_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
GAP_MIN = -23
GAP_MAX = 48


def _require_manager():
	if "System Manager" not in frappe.get_roles():
		frappe.throw("فقط مدیر سیستم می‌تواند صفحه اصلی را مدیریت کند.", frappe.PermissionError)


def _session_user():
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw("برای این کار باید وارد سامانه شوید.", frappe.PermissionError)
	return user


def get_boot_layout():
	user = frappe.session.user
	if not user or user == "Guest":
		return {
			"active": 0,
			"personalized": 0,
			"default_shape": "rounded",
			"default_size": "medium",
			"icon_style": "Solid",
			"gap_x": 8,
			"gap_y": 8,
			"columns": 5,
			"categories": [],
			"folders": [],
			"items": [],
		}
	return _presentation(_filter_inaccessible(_resolve_layout(user)))


@frappe.whitelist()
def get_current_layout():
	"""Resolved home page for the logged-in user only."""
	return get_boot_layout()


@frappe.whitelist()
def get_layout():
	_require_manager()
	return _global_layout()


@frappe.whitelist()
def get_my_layout():
	"""Editor payload for the session user. Does not create a preference document."""
	user = _session_user()
	layout = _resolve_layout(user)
	layout["items"] = [item for item in layout["items"] if not item.get("globally_hidden")]
	layout["items"] = _sort_items(layout["items"], layout["categories"])
	return _filter_inaccessible(layout)


@frappe.whitelist()
def save_layout(payload=None):
	_require_manager()
	data = _parse_payload(payload)
	items = data.get("items") or []
	if not items:
		frappe.throw("آیکونی برای ذخیره ارسال نشده است. صفحه را تازه‌سازی کنید و دوباره تلاش کنید.")

	settings = _get_settings()
	if "enable_custom_styles" in data:
		settings.enable_custom_styles = cint(data.get("enable_custom_styles"))
	elif "enabled" in data:
		settings.enable_custom_styles = cint(data.get("enabled"))
	else:
		settings.enable_custom_styles = 1
	if "apply_to_all_users" in data:
		settings.apply_to_all_users = cint(data.get("apply_to_all_users"))
	settings.default_shape = data.get("default_shape") or "rounded"
	settings.default_size = data.get("default_size") or "medium"
	settings.icon_style = data.get("icon_style") or "Solid"
	settings.gap_x = _clamp_gap(data.get("gap_x"), 8)
	settings.gap_y = _clamp_gap(data.get("gap_y"), 8)
	settings.columns = _clamp_columns(data.get("columns"))
	_validate_style(settings.default_shape, settings.default_size, settings.icon_style)

	prepared = [_prepare_style_row(item, settings) for item in items]
	prepared = [row for row in prepared if row]
	folders = _prepare_folders(data.get("folders"))
	folder_names = {row["folder_name"] for row in folders}
	for row in prepared:
		if row.get("folder") not in folder_names:
			row["folder"] = ""
	names = _category_names(data.get("categories"), prepared)
	for folder in folders:
		if folder["category"] not in names:
			names.append(folder["category"])
	previous_categories = _stored_category_names(settings.categories)
	_write_categories(settings, "categories", names)
	settings.set("folders", [])
	for folder in folders:
		settings.append("folders", folder)
	settings.set("styles", [])
	for row in prepared:
		settings.append("styles", row)

	settings.save(ignore_permissions=True)
	_forget_removed_categories(previous_categories, names)
	_retarget_preferences(data.get("category_renames"), names)
	_clear_desktop_caches()
	layout = _global_layout()
	_publish_refresh("global")
	return layout


@frappe.whitelist()
def save_my_layout(payload=None):
	user = _session_user()
	data = _parse_payload(payload)
	doc = _preference_doc(user)
	if doc.user != user:
		frappe.throw("چیدمان کاربر دیگری قابل ویرایش نیست.", frappe.PermissionError)

	global_layout = _global_layout()
	global_folders = {row["folder_name"] for row in global_layout.get("folders") or []}
	global_hidden = {item["name"] for item in global_layout["items"] if item.get("globally_hidden")}
	prepared = []
	for item in data.get("items") or []:
		name = item.get("name") or item.get("desktop_icon")
		if not name or name in global_hidden or not frappe.db.exists("Desktop Icon", name):
			continue
		row = _prepare_style_row(item, _get_settings(), allow_link=False)
		if not row:
			continue
		if row.get("folder") not in global_folders:
			row["folder"] = ""
		prepared.append(row)

	folders = []
	for folder in _prepare_folders(data.get("folders"), allow_appearance=False):
		if folder["folder_name"] not in global_folders:
			continue
		folders.append(folder)
	prepared, folders = _keep_unseen_preferences(doc, prepared, folders, global_layout)

	names = _category_names(data.get("categories"), prepared)
	for folder in folders:
		if folder["category"] not in names:
			names.append(folder["category"])
	doc.user = user
	_write_categories(doc, "categories", names)
	doc.set("folders", [])
	for folder in folders:
		doc.append("folders", {
			"folder_name": folder["folder_name"],
			"category": folder["category"],
			"sequence": folder["sequence"],
		})
	doc.set("items", [])
	for row in prepared:
		doc.append("items", row)
	doc.save(ignore_permissions=True)
	_publish_refresh("personal", user)
	return get_my_layout()


@frappe.whitelist()
def reset_my_layout():
	user = _session_user()
	if frappe.db.exists("SP Home Preference", user):
		owned = frappe.db.get_value("SP Home Preference", user, "user")
		if owned != user:
			frappe.throw("چیدمان کاربر دیگری قابل ویرایش نیست.", frappe.PermissionError)
		frappe.delete_doc("SP Home Preference", user, ignore_permissions=True)
	_publish_refresh("personal", user)
	return get_my_layout()


@frappe.whitelist()
def create_desktop_icon(label, link=""):
	_require_manager()
	label = (label or "").strip()
	if not label:
		frappe.throw("نام آیکون الزامی است.")
	if frappe.db.exists("Desktop Icon", label):
		frappe.throw("آیکونی با نام {0} از قبل وجود دارد.".format(label))

	doc = frappe.get_doc(
		{
			"doctype": "Desktop Icon",
			"label": label,
			"icon_type": "Link",
			"link_type": "External",
			"link": link or "/app",
			"standard": 0,
			"bg_color": "blue",
			"idx": 99,
		}
	)
	doc.insert(ignore_permissions=True)
	_clear_desktop_caches()
	return _global_layout()


def ensure_manager_icon():
	if frappe.db.exists("Desktop Icon", MANAGER_ICON_LABEL):
		frappe.db.set_value(
			"Desktop Icon",
			MANAGER_ICON_LABEL,
			{"link_type": "External", "link": MANAGER_ICON_LINK, "hidden": 0},
			update_modified=False,
		)
		return

	max_idx = frappe.db.sql("select ifnull(max(idx), 0) from `tabDesktop Icon`")[0][0]
	doc = frappe.get_doc(
		{
			"doctype": "Desktop Icon",
			"label": MANAGER_ICON_LABEL,
			"icon_type": "Link",
			"link_type": "External",
			"link": MANAGER_ICON_LINK,
			"standard": 0,
			"bg_color": "blue",
			"idx": cint(max_idx) + 1,
		}
	)
	doc.insert(ignore_permissions=True)
	_clear_desktop_caches()


def _accessible_icon_names():
	"""Desktop Icon names the session user may open.

	Mirrors ``get_desktop_icons`` without collapsing children into native folders:
	workspace icons require a non-empty ``get_sidebar_items`` entry for their label,
	app icons use ``check_app_permission``, and configured Desktop Icon roles must
	intersect the user's roles. External links have no destination check in Frappe
	(the same as a URL sidebar item), so they stay visible unless those roles exclude
	the user. Administrator is unfiltered, matching ``DeskViews.is_item_allowed``.
	Returns None when every icon is allowed.
	"""
	user = frappe.session.user
	if user == "Administrator":
		return None

	from frappe.boot import get_sidebar_items
	from frappe.desk.desktop import get_workspaces
	from frappe.desk.doctype.desktop_icon.desktop_icon import check_app_permission

	pages = [page.name for page in (get_workspaces().get("pages") or [])]
	sidebars = get_sidebar_items(pages)
	user_roles = set(frappe.get_roles(user))
	icons = frappe.get_all(
		"Desktop Icon",
		fields=["name", "label", "icon_type", "link_type", "app"],
	)
	role_map = {}
	icon_names = [icon.name for icon in icons]
	if icon_names:
		for row in frappe.get_all(
			"Has Role",
			filters={"parenttype": "Desktop Icon", "parent": ["in", icon_names]},
			fields=["parent", "role"],
		):
			role_map.setdefault(row.parent, set()).add(row.role)

	allowed = set()
	for icon in icons:
		if icon.icon_type == "Folder":
			continue
		if icon.icon_type == "App":
			permitted = bool(check_app_permission(icon.label, icon.app))
		elif (icon.link_type or "") == "External":
			permitted = True
		else:
			sidebar = sidebars.get((icon.label or "").lower())
			permitted = bool(sidebar and sidebar.get("items"))
		if permitted and role_map.get(icon.name):
			permitted = bool(role_map[icon.name] & user_roles)
		if permitted:
			allowed.add(icon.name)
	return allowed


def _filter_inaccessible(layout):
	"""Drop icons and empty folders the session user cannot open.

	This changes the response only. Saved hidden flags and folder membership stay.
	"""
	allowed = _accessible_icon_names()
	if allowed is None:
		return _annotate_folders(layout)
	items = [item for item in (layout.get("items") or []) if item.get("name") in allowed]
	folder_names = {item.get("folder") for item in items if item.get("folder")}
	folders = [
		folder for folder in (layout.get("folders") or [])
		if folder.get("folder_name") in folder_names
	]
	filtered = dict(layout)
	filtered["items"] = items
	filtered["folders"] = folders
	return _annotate_folders(filtered)


def _keep_unseen_preferences(doc, prepared, folders, global_layout):
	"""Keep preference rows for icons the user cannot currently open."""
	allowed = _accessible_icon_names()
	if allowed is None:
		return prepared, folders

	settings = _get_settings()
	kept_names = {row["desktop_icon"] for row in prepared}
	existing_items = {row.desktop_icon: row for row in (doc.items or [])}
	for item in global_layout.get("items") or []:
		name = item.get("name")
		if not name or name in allowed or name in kept_names or item.get("globally_hidden"):
			continue
		previous = existing_items.get(name)
		if previous:
			prepared.append({
				"desktop_icon": previous.desktop_icon,
				"custom_label": previous.custom_label or "",
				"category": (previous.category or UNCATEGORIZED).strip() or UNCATEGORIZED,
				"folder": (previous.folder or "").strip()[:140],
				"shape": previous.shape,
				"size": previous.size,
				"use_custom_style": cint(previous.use_custom_style),
				"custom_color": previous.custom_color or "",
				"custom_icon_image": previous.custom_icon_image or "",
				"icon_name": previous.icon_name or "",
				"hidden": cint(previous.hidden),
				"sequence": cint(previous.sequence),
			})
		else:
			prepared.append({
				"desktop_icon": name,
				"custom_label": "",
				"category": (item.get("category") or UNCATEGORIZED).strip() or UNCATEGORIZED,
				"folder": (item.get("folder") or "").strip()[:140],
				"shape": item.get("shape") or settings.default_shape,
				"size": item.get("size") or settings.default_size,
				"use_custom_style": 0,
				"custom_color": "",
				"custom_icon_image": "",
				"icon_name": "",
				"hidden": 0,
				"sequence": cint(item.get("sequence")),
			})
		kept_names.add(name)

	kept_folders = {row["folder_name"] for row in folders}
	accessible_folders = {
		item.get("folder")
		for item in (global_layout.get("items") or [])
		if item.get("name") in allowed and item.get("folder") and not item.get("globally_hidden")
	}
	existing_folders = {row.folder_name: row for row in (doc.folders or [])}
	for folder in global_layout.get("folders") or []:
		name = folder.get("folder_name")
		if not name or name in kept_folders or name in accessible_folders:
			continue
		previous = existing_folders.get(name)
		if previous:
			folders.append({
				"folder_name": name,
				"category": (previous.category or UNCATEGORIZED).strip() or UNCATEGORIZED,
				"sequence": cint(previous.sequence),
			})
		else:
			folders.append({
				"folder_name": name,
				"category": (folder.get("category") or UNCATEGORIZED).strip() or UNCATEGORIZED,
				"sequence": cint(folder.get("sequence")),
			})
		kept_folders.add(name)
	return prepared, folders


def _resolve_layout(user):
	layout = _global_layout()
	layout["active"] = 1 if _is_active_for(user, layout) else 0
	layout["personalized"] = 0
	preference = _read_preference(user)
	if not preference:
		return layout
	return _apply_preference(layout, preference)


def _global_layout():
	settings = _get_settings()
	style_map = {}
	for row in settings.styles or []:
		style_map[row.desktop_icon] = row
	icons = frappe.get_all(
		"Desktop Icon",
		fields=[
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
		],
		order_by="idx asc, label asc",
	)
	items = []
	for icon in icons:
		if icon.icon_type == "Folder":
			continue
		style = style_map.get(icon.name) or style_map.get(icon.label)
		items.append(_item_from_icon(icon, style, settings))

	categories = _stored_category_names(settings.categories)
	if not categories:
		categories = _categories_from_items(items)
	else:
		for item in items:
			if item["category"] not in categories:
				categories.append(item["category"])
	items = _sort_items(items, categories)
	return _annotate_folders({
		"enabled": cint(settings.enable_custom_styles),
		"apply_to_all_users": cint(settings.apply_to_all_users),
		"active": 0,
		"personalized": 0,
		"default_shape": settings.default_shape or "rounded",
		"default_size": settings.default_size or "medium",
		"icon_style": settings.icon_style or "Solid",
		"gap_x": _int_setting(settings, "gap_x", 8),
		"gap_y": _int_setting(settings, "gap_y", 8),
		"columns": _clamp_columns(settings.get("columns") if hasattr(settings, "get") else None),
		"categories": categories,
		"folders": _folder_rows(getattr(settings, "folders", None)),
		"items": items,
	})


def _apply_preference(layout, preference):
	global_names = list(layout["categories"])
	global_set = set(global_names)
	personal_names = set()
	for row in preference.items or []:
		category = (row.category or "").strip()
		if category and category not in global_set:
			personal_names.add(category)
	for row in preference.folders or []:
		category = (row.category or "").strip()
		if category and category not in global_set:
			personal_names.add(category)
	names = []
	for name in _stored_category_names(preference.categories):
		# A preference category row does not recreate a deleted global category.
		# A personal category remains only when an icon or folder still uses it.
		if name in global_set or name in personal_names:
			if name not in names:
				names.append(name)
	for name in global_names:
		if name not in names:
			names.append(name)
	by_icon = {row.desktop_icon: row for row in (preference.items or [])}
	for item in layout["items"]:
		row = by_icon.get(item["name"])
		if not row or item.get("globally_hidden"):
			item["sequence"] = 100000 + cint(item.get("sequence"))
			continue
		if row.custom_label:
			item["custom_label"] = display_label(row.custom_label)
		category = (row.category or "").strip()
		if category and (category in global_set or category in personal_names):
			item["category"] = category
			if category not in names:
				names.append(category)
		item["use_custom_style"] = cint(row.use_custom_style)
		if item["use_custom_style"]:
			item["shape"] = row.shape or layout["default_shape"]
			item["size"] = row.size or layout["default_size"]
		item["custom_color"] = row.custom_color or ""
		item["custom_icon_image"] = row.custom_icon_image or ""
		item["icon_name"] = row.icon_name or ""
		item["hidden"] = cint(row.hidden)
		item["sequence"] = cint(row.sequence)
		folder_name = (row.get("folder") or "").strip()
		known = {folder["folder_name"] for folder in layout.get("folders") or []}
		# An older preference has no folder rows and blank membership. Keep the
		# current global folders until that user actually saves a folder choice.
		explicit_folders = bool(preference.folders) or any(
			(entry.get("folder") or "").strip() for entry in (preference.items or [])
		)
		if explicit_folders:
			item["folder"] = folder_name if folder_name in known else ""
	for folder in layout.get("folders") or []:
		row = next((entry for entry in (preference.folders or []) if entry.folder_name == folder["folder_name"]), None)
		if not row:
			continue
		category = (row.category or "").strip()
		if category and (category in global_set or category in personal_names):
			folder["category"] = category
			if category not in names:
				names.append(category)
		folder["sequence"] = cint(row.sequence)
	layout["categories"] = names
	layout["items"] = _sort_items(layout["items"], names)
	layout["personalized"] = 1
	return _annotate_folders(layout)


def _presentation(layout):
	return {
		"active": cint(layout.get("active")),
		"personalized": cint(layout.get("personalized")),
		"default_shape": layout.get("default_shape") or "rounded",
		"default_size": layout.get("default_size") or "medium",
		"icon_style": layout.get("icon_style") or "Solid",
		"gap_x": layout.get("gap_x"),
		"gap_y": layout.get("gap_y"),
		"columns": layout.get("columns"),
		"categories": list(layout.get("categories") or []),
		"folders": list(layout.get("folders") or []),
		"items": [item for item in layout.get("items") or [] if not item.get("hidden")],
	}


def _item_from_icon(icon, style, settings):
	use_custom = cint(style.get("use_custom_style")) if style else 0
	globally_hidden = cint(style.hidden) if style else cint(icon.hidden)
	category = (style.category if style and style.category else UNCATEGORIZED).strip() or UNCATEGORIZED
	return {
		"name": icon.name,
		"label": icon.label,
		"custom_label": display_label(style.custom_label if style and style.custom_label else icon.label),
		"category": category,
		"folder": ((style.get("folder") or "").strip() if style else ""),
		"shape": style.shape if use_custom and style and style.shape else (settings.default_shape or "rounded"),
		"size": style.size if use_custom and style and style.size else (settings.default_size or "medium"),
		"use_custom_style": use_custom,
		"custom_color": style.custom_color if style else "",
		"custom_link": style.custom_link if style else "",
		"custom_icon_image": style.custom_icon_image if style else "",
		"icon_name": (style.icon_name or "") if style else "",
		"icon": icon.icon or "",
		"hidden": globally_hidden,
		"globally_hidden": globally_hidden,
		"sequence": cint(style.sequence) if style and style.sequence else cint(icon.idx),
		"icon_type": icon.icon_type,
		"link_type": icon.link_type,
		"link_to": icon.link_to,
		"link": icon.link,
		"parent_icon": icon.parent_icon,
		"icon_image": icon.icon_image,
		"logo_url": icon.logo_url,
		"bg_color": icon.bg_color,
		"restrict_removal": cint(icon.restrict_removal),
	}


def _prepare_style_row(item, settings, allow_link=True):
	name = item.get("name") or item.get("desktop_icon")
	if not name or not frappe.db.exists("Desktop Icon", name):
		return None
	hidden = cint(item.get("hidden"))
	sequence = cint(item.get("sequence") or 0)
	shape = item.get("shape") or settings.default_shape
	size = item.get("size") or settings.default_size
	_validate_style(shape, size)
	color = item.get("custom_color") or ""
	if color and not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", color):
		frappe.throw("رنگ باید یک کد معتبر سه یا شش رقمی با علامت # باشد.")
	icon_name = (item.get("icon_name") or "").strip()
	_validate_icon_name(icon_name)
	custom_icon_image = (item.get("custom_icon_image") or "").strip()
	_validate_uploaded_image(custom_icon_image)
	row = {
		"desktop_icon": name,
		"custom_label": item.get("custom_label") or "",
		"category": (item.get("category") or UNCATEGORIZED).strip() or UNCATEGORIZED,
		"folder": (item.get("folder") or "").strip()[:140],
		"shape": shape,
		"size": size,
		"use_custom_style": cint(item.get("use_custom_style")),
		"custom_color": color,
		"custom_icon_image": custom_icon_image,
		"icon_name": icon_name,
		"hidden": hidden,
		"sequence": sequence,
	}
	if allow_link:
		custom_link = (item.get("custom_link") or "").strip()
		_validate_link(custom_link)
		row["custom_link"] = custom_link
	return row


def _prepare_folders(raw, allow_appearance=True):
	folders = []
	seen = set()
	for entry in raw or []:
		if not isinstance(entry, dict):
			continue
		name = (entry.get("folder_name") or "").strip()
		if not name or name in seen or len(name) > 140:
			continue
		seen.add(name)
		icon_name = (entry.get("icon_name") or "").strip() if allow_appearance else ""
		image = (entry.get("custom_icon_image") or "").strip() if allow_appearance else ""
		if allow_appearance:
			_validate_icon_name(icon_name)
			_validate_uploaded_image(image)
		folders.append({
			"folder_name": name,
			"category": (entry.get("category") or UNCATEGORIZED).strip() or UNCATEGORIZED,
			"sequence": cint(entry.get("sequence")),
			"icon_name": icon_name,
			"custom_icon_image": image,
		})
	return folders


def folder_icon_mode(folder):
	"""image, then an explicit icon name, otherwise the automatic child preview."""
	if (folder.get("custom_icon_image") or "").strip():
		return "image"
	if (folder.get("icon_name") or "").strip():
		return "icon"
	return "preview"


def folder_preview_items(folder, items):
	"""First four visible children, in the folder's saved order. The fifth is excluded."""
	name = (folder.get("folder_name") or "").strip()
	members = [
		item
		for item in items or []
		if (item.get("folder") or "") == name and not cint(item.get("hidden")) and item.get("icon_type") != "Folder"
	]
	members.sort(key=lambda item: (cint(item.get("sequence")), item.get("label") or "", item.get("name") or ""))
	return members[:4]


def category_entries(layout, category):
	"""Icons and folders in one sequence. Equal sequences place the folder first."""
	category = category or UNCATEGORIZED
	folders = [
		folder
		for folder in layout.get("folders") or []
		if (folder.get("category") or UNCATEGORIZED) == category
	]
	folder_names = {folder["folder_name"] for folder in folders}
	entries = []
	for item in layout.get("items") or []:
		if item.get("icon_type") == "Folder":
			continue
		if (item.get("category") or UNCATEGORIZED) != category:
			continue
		if (item.get("folder") or "") in folder_names:
			continue
		entries.append((cint(item.get("sequence")), 1, "icon", item.get("name") or ""))
	for folder in folders:
		entries.append((cint(folder.get("sequence")), 0, "folder", folder["folder_name"]))
	entries.sort()
	return [(kind, name) for _, _, kind, name in entries]


def _annotate_folders(layout):
	for folder in layout.get("folders") or []:
		folder["icon_mode"] = folder_icon_mode(folder)
		folder["preview"] = [item["name"] for item in folder_preview_items(folder, layout.get("items") or [])]
	return layout


def _folder_rows(rows):
	folders = []
	for row in rows or []:
		name = (row.folder_name or "").strip()
		if not name:
			continue
		folders.append({
			"folder_name": name,
			"category": (row.category or UNCATEGORIZED).strip() or UNCATEGORIZED,
			"sequence": cint(row.sequence),
			"icon_name": row.get("icon_name") or "",
			"custom_icon_image": row.get("custom_icon_image") or "",
		})
	return folders


def _category_names(raw, rows):
	names = []
	if raw is None:
		raw = []
		for row in rows:
			category = row["category"]
			if category not in names:
				names.append(category)
		return names or [UNCATEGORIZED]
	for entry in raw:
		if isinstance(entry, str):
			name = entry.strip()
		elif isinstance(entry, dict):
			name = (entry.get("category_name") or entry.get("name") or "").strip()
		else:
			name = ""
		if name and name not in names:
			names.append(name)
	for row in rows:
		if row["category"] not in names:
			names.append(row["category"])
	return names or [UNCATEGORIZED]


def _write_categories(parent, fieldname, names):
	parent.set(fieldname, [])
	for name in names:
		parent.append(fieldname, {"category_name": name})


def _stored_category_names(rows):
	ordered = sorted(list(rows or []), key=lambda row: cint(row.idx) or 0)
	names = []
	for row in ordered:
		name = (row.category_name or "").strip()
		if name and name not in names:
			names.append(name)
	return names


def _categories_from_items(items):
	visible = [item for item in items if not item.get("hidden")]
	visible.sort(key=lambda item: (cint(item.get("sequence")), item.get("label") or ""))
	names = []
	for item in visible:
		if item["category"] not in names:
			names.append(item["category"])
	for item in items:
		if item["category"] not in names:
			names.append(item["category"])
	return names or [UNCATEGORIZED]


def _sort_items(items, categories):
	index = {name: position for position, name in enumerate(categories)}
	return sorted(
		items,
		key=lambda item: (
			index.get(item.get("category"), len(index)),
			cint(item.get("sequence")),
			item.get("label") or "",
		),
	)


def _is_active_for(user, layout):
	if not cint(layout.get("enabled")):
		return False
	if cint(layout.get("apply_to_all_users")):
		return True
	return "System Manager" in frappe.get_roles(user)


def _read_preference(user):
	if not user or user == "Guest" or not frappe.db.exists("DocType", "SP Home Preference"):
		return None
	if not frappe.db.exists("SP Home Preference", user):
		return None
	return frappe.get_doc("SP Home Preference", user)


def _preference_doc(user):
	if frappe.db.exists("SP Home Preference", user):
		return frappe.get_doc("SP Home Preference", user)
	doc = frappe.new_doc("SP Home Preference")
	doc.user = user
	return doc


def _globally_hidden_names():
	layout = _global_layout()
	return {item["name"] for item in layout["items"] if item.get("globally_hidden")}


def _get_settings():
	if not frappe.db.exists("DocType", "SP Home Settings"):
		return frappe._dict(
			enable_custom_styles=1,
			apply_to_all_users=1,
			default_shape="rounded",
			default_size="medium",
			icon_style="Solid",
			gap_x=8,
			gap_y=8,
			categories=[],
			folders=[],
			styles=[],
		)
	return frappe.get_single("SP Home Settings")


def _int_setting(settings, fieldname, default):
	value = settings.get(fieldname) if hasattr(settings, "get") else None
	if value in (None, ""):
		return default
	return _clamp_gap(value, default)


def _clamp_columns(value):
	number = cint(value)
	if not number:
		return 5
	return min(10, max(2, number))


def _clamp_gap(value, default):
	if value in (None, ""):
		return default
	number = cint(value)
	if number < GAP_MIN:
		return GAP_MIN
	if number > GAP_MAX:
		return GAP_MAX
	return number


def _forget_removed_categories(previous, saved_names):
	"""Drop a deleted global category from personal preferences.

	Personal categories that were never global are left in place.
	"""
	removed = [name for name in (previous or []) if name not in set(saved_names or [])]
	if not removed or not frappe.db.exists("DocType", "SP Home Preference"):
		return
	removed_set = set(removed)
	for name in frappe.get_all("SP Home Preference", pluck="name"):
		doc = frappe.get_doc("SP Home Preference", name)
		changed = False
		kept = []
		for row in doc.categories or []:
			category = (row.category_name or "").strip()
			if category in removed_set:
				changed = True
				continue
			if category and category not in kept:
				kept.append(category)
		if [(row.category_name or "").strip() for row in (doc.categories or [])] != kept:
			_write_categories(doc, "categories", kept)
			changed = True
		for row in doc.items or []:
			if (row.category or "").strip() in removed_set:
				row.category = ""
				changed = True
		for row in doc.get("folders") or []:
			if (row.category or "").strip() in removed_set:
				row.category = ""
				changed = True
		if changed:
			doc.save(ignore_permissions=True)


def _retarget_preferences(renames, saved_names):
	"""Point personalized category names at a renamed global category."""
	if not renames or not frappe.db.exists("DocType", "SP Home Preference"):
		return
	saved = set(saved_names or [])
	pairs = []
	for entry in renames:
		old = (entry.get("from") or "").strip()
		new = (entry.get("to") or "").strip()
		if not old or not new or old == new or new not in saved or old in saved:
			continue
		pairs.append((old, new))
	if not pairs:
		return
	for name in frappe.get_all("SP Home Preference", pluck="name"):
		doc = frappe.get_doc("SP Home Preference", name)
		if _rewrite_preference_categories(doc, pairs):
			doc.save(ignore_permissions=True)


def _map_category_name(name, pairs):
	current = (name or "").strip()
	for old, new in pairs:
		if current == old:
			current = new
	return current


def _rewrite_preference_categories(doc, pairs):
	changed = False
	names = []
	for row in doc.categories or []:
		name = (row.category_name or "").strip()
		updated = _map_category_name(name, pairs)
		if updated != name:
			changed = True
		if updated and updated not in names:
			names.append(updated)
	if [(row.category_name or "").strip() for row in (doc.categories or [])] != names:
		changed = True
		_write_categories(doc, "categories", names)
	for row in doc.items or []:
		updated = _map_category_name(row.category, pairs)
		if updated and updated != (row.category or "").strip():
			row.category = updated
			changed = True
	for row in doc.get("folders") or []:
		updated = _map_category_name(row.category, pairs)
		if updated and updated != (row.category or "").strip():
			row.category = updated
			changed = True
	return changed


def _parse_payload(payload):
	if isinstance(payload, str):
		try:
			payload = json.loads(payload or "{}")
		except (ValueError, TypeError):
			frappe.throw("اطلاعات چیدمان معتبر نیست.")
	if not isinstance(payload, dict) or not isinstance(payload.get("items"), list) or not all(
		isinstance(item, dict) for item in payload["items"]
	):
		frappe.throw("اطلاعات چیدمان معتبر نیست.")
	categories = payload.get("categories")
	if categories is not None and (
		not isinstance(categories, list) or not all(isinstance(entry, (str, dict)) for entry in categories)
	):
		frappe.throw("اطلاعات دسته‌ها معتبر نیست.")
	folders = payload.get("folders")
	if folders is not None and (
		not isinstance(folders, list) or not all(isinstance(entry, dict) for entry in folders)
	):
		frappe.throw("اطلاعات پوشه‌ها معتبر نیست.")
	renames = payload.get("category_renames")
	if renames is not None and (
		not isinstance(renames, list) or not all(isinstance(entry, dict) for entry in renames)
	):
		frappe.throw("اطلاعات دسته‌ها معتبر نیست.")
	payload.pop("user", None)
	return payload


def _validate_style(shape, size, icon_style="Solid"):
	if (
		shape not in ("rounded", "circle", "square")
		or size not in ("small", "medium", "large", "xlarge")
		or icon_style not in ("Solid", "Subtle")
	):
		frappe.throw("شکل، اندازه یا سبک آیکون معتبر نیست.")


def _validate_icon_name(icon_name):
	if icon_name and not ICON_NAME_RE.fullmatch(icon_name):
		frappe.throw("نام آیکون فراپه معتبر نیست.")


def _validate_link(link):
	if not link:
		return
	if len(link) > 1000 or not re.match(r"^(?:/|https?://|mailto:)", link, re.IGNORECASE):
		frappe.throw("لینک باید داخلی یا با http، https یا mailto آغاز شود.")


def _validate_uploaded_image(file_url):
	if not file_url:
		return
	if len(file_url) > 1000 or not re.match(r"^/(?:private/)?files/", file_url, re.IGNORECASE):
		frappe.throw("تصویر آیکون باید از ابزار بارگذاری همین سامانه انتخاب شود.")
	if not frappe.db.exists("File", {"file_url": file_url}):
		frappe.throw("فایل تصویر انتخاب‌شده در سامانه پیدا نشد.")


def _publish_refresh(scope, user=None):
	kwargs = {"after_commit": True}
	if user:
		kwargs["user"] = user
	frappe.publish_realtime("sp_home_layout_updated", {"scope": scope}, **kwargs)


def _clear_desktop_caches():
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")
	for user in frappe.get_all("User", filters={"enabled": 1}, pluck="name"):
		clear_desktop_caches_for_user(user)


def clear_desktop_caches_for_user(user):
	clear_desktop_icons_cache(user)
