import json
import re

import frappe

from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache
from frappe.utils import cint
from smartprocee_erpnext_homepage.home_manager.labels import display_label

MANAGER_ICON_LABEL = "مدیریت صفحه اصلی"
MANAGER_ICON_LINK = "/app/home-manager"
UNCATEGORIZED = "عمومی"


def _require_manager():
	if "System Manager" not in frappe.get_roles():
		frappe.throw("فقط مدیر سیستم می‌تواند صفحه اصلی را مدیریت کند.", frappe.PermissionError)


def get_boot_layout():
	settings = _get_settings()
	style_map = {row.desktop_icon: row for row in (settings.styles or [])}
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
		use_custom = cint(style.get("use_custom_style")) if style else 0
		items.append(
			{
				"name": icon.name,
				"label": icon.label,
				"custom_label": display_label(style.custom_label if style and style.custom_label else icon.label),
				"category": (style.category if style and style.category else UNCATEGORIZED),
				"shape": style.shape if use_custom and style and style.shape else (settings.default_shape or "rounded"),
				"size": style.size if use_custom and style and style.size else (settings.default_size or "medium"),
				"use_custom_style": use_custom,
				"custom_color": style.custom_color if style else "",
				"custom_link": style.custom_link if style else "",
				"custom_icon_image": style.custom_icon_image if style else "",
				"hidden": cint(style.hidden) if style else cint(icon.hidden),
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
		)

	# Global sequence preserves the editor's category order; newly created categories stay last.
	items.sort(key=lambda row: (row["sequence"], row["label"]))
	return {
		"enabled": cint(settings.enable_custom_styles),
		"manager_only": not cint(settings.apply_to_all_users),
		"apply_to_all_users": cint(settings.apply_to_all_users),
		"default_shape": settings.default_shape or "rounded",
		"default_size": settings.default_size or "medium",
		"icon_style": settings.icon_style or "Solid",
		"gap_x": _int_setting(settings, "gap_x", 8),
		"gap_y": _int_setting(settings, "gap_y", 8),
		"columns": _clamp_columns(settings.get("columns") if hasattr(settings, "get") else None),
		"items": items,
	}


@frappe.whitelist()
def get_current_layout():
	"""Same presentation data as boot, for reconnect/focus synchronization."""
	return get_boot_layout()


@frappe.whitelist()
def get_layout():
	_require_manager()
	return get_boot_layout()


@frappe.whitelist()
def save_layout(payload=None):
	_require_manager()
	data = _parse_payload(payload)
	items = data.get("items") or []
	if not items:
		frappe.throw("آیکونی برای ذخیره ارسال نشده است. صفحه را تازه‌سازی کنید و دوباره تلاش کنید.")

	settings = _get_settings()
	settings.enable_custom_styles = cint(data.get("enable_custom_styles", 1))
	settings.apply_to_all_users = cint(data.get("apply_to_all_users", 1))
	settings.default_shape = data.get("default_shape") or "rounded"
	settings.default_size = data.get("default_size") or "medium"
	settings.icon_style = data.get("icon_style") or "Solid"
	settings.gap_x = _clamp_gap(data.get("gap_x"), 8)
	settings.gap_y = _clamp_gap(data.get("gap_y"), 8)
	settings.columns = _clamp_columns(data.get("columns"))
	_validate_style(settings.default_shape, settings.default_size, settings.icon_style)
	settings.set("styles", [])

	for index, item in enumerate(items, start=1):
		name = item.get("name") or item.get("desktop_icon")
		if not name or not frappe.db.exists("Desktop Icon", name):
			continue
		hidden = cint(item.get("hidden"))
		sequence = cint(item.get("sequence") or index)
		_validate_style(item.get("shape") or settings.default_shape, item.get("size") or settings.default_size)
		color = item.get("custom_color") or ""
		if color and not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", color):
			frappe.throw("رنگ باید یک کد معتبر سه یا شش رقمی با علامت # باشد.")
		custom_link = (item.get("custom_link") or "").strip()
		custom_icon_image = (item.get("custom_icon_image") or "").strip()
		_validate_link(custom_link)
		_validate_uploaded_image(custom_icon_image)
		settings.append(
			"styles",
			{
				"desktop_icon": name,
				"custom_label": item.get("custom_label") or "",
				"category": item.get("category") or UNCATEGORIZED,
				"shape": item.get("shape") or settings.default_shape,
				"size": item.get("size") or settings.default_size,
				"use_custom_style": cint(item.get("use_custom_style")),
				"custom_color": item.get("custom_color") or "",
				"custom_link": custom_link,
				"custom_icon_image": custom_icon_image,
				"hidden": hidden,
				"sequence": sequence,
			},
		)

	settings.save(ignore_permissions=True)
	_clear_desktop_caches()
	layout = get_boot_layout()
	frappe.publish_realtime("sp_home_layout_updated", layout, after_commit=True)
	return layout


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
	return get_boot_layout()


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
	number = cint(value)
	if value in (None, "") and not number:
		number = default
	if number < -50:
		return -50
	if number > 100:
		return 100
	return number


def _parse_payload(payload):
	if isinstance(payload, str):
		try:
			payload = json.loads(payload or "{}")
		except (ValueError, TypeError):
			frappe.throw("اطلاعات چیدمان معتبر نیست.")
	if not isinstance(payload, dict) or not isinstance(payload.get("items"), list) or not all(isinstance(item, dict) for item in payload["items"]):
		frappe.throw("اطلاعات چیدمان معتبر نیست.")
	return payload


def _validate_style(shape, size, icon_style="Solid"):
	if shape not in ("rounded", "circle", "square") or size not in ("small", "medium", "large", "xlarge") or icon_style not in ("Solid", "Subtle"):
		frappe.throw("شکل، اندازه یا سبک آیکون معتبر نیست.")


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


def _clear_desktop_caches():
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")
	for user in frappe.get_all("User", filters={"enabled": 1}, pluck="name"):
		clear_desktop_caches_for_user(user)


def clear_desktop_caches_for_user(user):
	clear_desktop_icons_cache(user)
