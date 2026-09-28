"""Database round-trip checks, rolled back after each test; no core fixtures."""
import copy
import unittest
from unittest.mock import patch

import frappe

from smartprocee_erpnext_homepage.home_manager import api


class TestHomeLayout(unittest.TestCase):
    def setUp(self):
        self.user = frappe.session.user
        frappe.set_user("Administrator")
        frappe.db.savepoint("home_manager_test")
        self.before = frappe.get_all("Desktop Icon", fields=["name", "hidden", "idx", "parent_icon"], order_by="name")
        self.layout = api.get_layout()

    def tearDown(self):
        frappe.db.rollback(save_point="home_manager_test")
        frappe.set_user(self.user)

    def test_round_trip(self):
        cases = [
            (3, -50, 100, "small", "circle", api.GAP_MIN, 48),
            (5, 30, 0, "medium", "square", 30, 0),
            (7, 8, 8, "large", "rounded", 8, 8),
            (6, -25, -10, "xlarge", "square", api.GAP_MIN, -10),
        ]
        for columns, gap_x, gap_y, size, shape, expected_x, expected_y in cases:
            payload = copy.deepcopy(self.layout)
            payload.update(columns=columns, gap_x=gap_x, gap_y=gap_y, default_size=size, default_shape=shape)
            with patch.object(frappe, "publish_realtime") as publish:
                api.save_layout(payload)
                publish.assert_any_call("sp_home_layout_updated", {"scope": "global"}, after_commit=True)
                self.assertEqual(sum(call.args[0] == "sp_home_layout_updated" for call in publish.call_args_list), 1)
            reloaded = api.get_layout()
            self.assertEqual(reloaded["columns"], columns)
            self.assertEqual(reloaded["gap_x"], expected_x)
            self.assertEqual(reloaded["gap_y"], expected_y)
            self.assertEqual(reloaded["default_size"], size)
            self.assertEqual(reloaded["default_shape"], shape)
            self.assertEqual(self.before, frappe.get_all("Desktop Icon", fields=["name", "hidden", "idx", "parent_icon"], order_by="name"))

    def test_override_survives_defaults(self):
        payload = copy.deepcopy(self.layout)
        item = payload["items"][0]
        item.update(use_custom_style=1, size="small", shape="circle", custom_color="#123456")
        payload.update(default_size="large", default_shape="square")
        with patch.object(frappe, "publish_realtime"):
            result = api.save_layout(payload)
        saved = next(row for row in result["items"] if row["name"] == item["name"])
        self.assertEqual((saved["size"], saved["shape"], saved["custom_color"]), ("small", "circle", "#123456"))

    def test_custom_link_survives_round_trip(self):
        payload = copy.deepcopy(self.layout)
        item = payload["items"][0]
        item["custom_link"] = "/app/user"
        with patch.object(frappe, "publish_realtime"):
            result = api.save_layout(payload)
        saved = next(row for row in result["items"] if row["name"] == item["name"])
        self.assertEqual(saved["custom_link"], "/app/user")

    def test_uploaded_image_survives_round_trip(self):
        file_url = "/files/sp-home-test-icon.png"
        payload = copy.deepcopy(self.layout)
        item = payload["items"][0]
        item["custom_icon_image"] = file_url
        original_exists = frappe.db.exists

        def exists(doctype, filters, *args, **kwargs):
            if doctype == "File" and filters == {"file_url": file_url}:
                return True
            return original_exists(doctype, filters, *args, **kwargs)

        with patch.object(frappe.db, "exists", side_effect=exists), patch.object(frappe, "publish_realtime"):
            result = api.save_layout(payload)
        saved = next(row for row in result["items"] if row["name"] == item["name"])
        self.assertEqual(saved["custom_icon_image"], file_url)

    def test_reject_invalid_input(self):
        for changes in [{"default_shape": "invalid"}, {"default_size": "invalid"}, {"icon_style": "invalid"}]:
            payload = copy.deepcopy(self.layout)
            payload.update(changes)
            with self.assertRaises(frappe.ValidationError):
                api.save_layout(payload)
        with self.assertRaises(frappe.ValidationError):
            api.save_layout("not json")
        unsafe_link = copy.deepcopy(self.layout)
        unsafe_link["items"][0]["custom_link"] = "javascript:alert(1)"
        with self.assertRaises(frappe.ValidationError):
            api.save_layout(unsafe_link)
        unsafe_image = copy.deepcopy(self.layout)
        unsafe_image["items"][0]["custom_icon_image"] = "https://example.com/icon.png"
        with self.assertRaises(frappe.ValidationError):
            api.save_layout(unsafe_image)

    def test_manager_permission(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            api.get_layout()

    def test_folders_are_not_returned(self):
        layout = api.get_layout()
        self.assertTrue(layout["items"])
        self.assertFalse(any(item["icon_type"] == "Folder" for item in layout["items"]))

    def test_new_category_stays_last(self):
        payload = copy.deepcopy(self.layout)
        moved = payload["items"][0]
        moved.update(category="دسته تازه", sequence=9999)
        with patch.object(frappe, "publish_realtime"):
            result = api.save_layout(payload)
        categories = []
        for item in result["items"]:
            if item["category"] not in categories:
                categories.append(item["category"])
        self.assertEqual(categories[-1], "دسته تازه")

    def test_hidden_icon_does_not_control_category_order(self):
        payload = copy.deepcopy(self.layout)
        hidden = payload["items"][0]
        visible = payload["items"][1]
        hidden.update(category="دسته پنهان", hidden=1, sequence=1)
        visible.update(category="دسته نمایان", hidden=0, sequence=80)
        payload["categories"] = ["دسته نمایان", "دسته پنهان"]
        with patch.object(frappe, "publish_realtime"):
            result = api.save_layout(payload)
        self.assertEqual(result["categories"][:2], ["دسته نمایان", "دسته پنهان"])

    def test_user_without_preference_receives_global_layout(self):
        user = self._make_user("sp-home-global@example.com")
        frappe.set_user(user)
        mine = api.get_my_layout()
        current = api.get_current_layout()
        self.assertEqual(mine["personalized"], 0)
        self.assertEqual(current["categories"], mine["categories"])
        self.assertEqual([item["name"] for item in current["items"]], [item["name"] for item in mine["items"] if not item["hidden"]])

    def test_personal_layouts_are_isolated(self):
        user_a = self._make_user("sp-home-a@example.com")
        user_b = self._make_user("sp-home-b@example.com")
        frappe.set_user(user_a)
        payload = copy.deepcopy(api.get_my_layout())
        payload.pop("user", None)
        payload["user"] = user_b
        payload["items"][0]["custom_label"] = "فقط الف"
        payload["categories"] = list(reversed(payload["categories"]))
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(payload)
        self.assertTrue(frappe.db.exists("SP Home Preference", user_a))
        self.assertFalse(frappe.db.exists("SP Home Preference", user_b))
        frappe.set_user(user_b)
        foreign = frappe.get_doc("SP Home Preference", user_a)
        self.assertFalse(frappe.has_permission(foreign.doctype, "read", foreign))
        with self.assertRaises(frappe.PermissionError):
            foreign.check_permission("read")
        with self.assertRaises(frappe.PermissionError):
            foreign.check_permission("write")
        other = api.get_my_layout()
        self.assertEqual(other["personalized"], 0)
        self.assertNotEqual(other["items"][0]["custom_label"], "فقط الف")
        payload_b = copy.deepcopy(other)
        payload_b["items"][0]["custom_label"] = "فقط ب"
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(payload_b)
        frappe.set_user(user_a)
        foreign_b = frappe.get_doc("SP Home Preference", user_b)
        self.assertFalse(frappe.has_permission(foreign_b.doctype, "read", foreign_b))
        with self.assertRaises(frappe.PermissionError):
            foreign_b.check_permission("write")
        again = api.get_my_layout()
        saved = next(row for row in again["items"] if row["name"] == payload["items"][0]["name"])
        self.assertEqual(saved["custom_label"], "فقط الف")
        frappe.set_user(user_b)
        theirs = api.get_my_layout()
        other = next(row for row in theirs["items"] if row["name"] == payload["items"][0]["name"])
        self.assertEqual(other["custom_label"], "فقط ب")

    def test_reset_preference_returns_global_layout(self):
        user = self._make_user("sp-home-reset@example.com")
        frappe.set_user("Administrator")
        global_layout = api.get_layout()
        frappe.set_user(user)
        payload = copy.deepcopy(api.get_my_layout())
        target = payload["items"][0]["name"]
        payload["items"][0]["custom_label"] = "موقت"
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(payload)
            reset = api.reset_my_layout()
        self.assertEqual(reset["personalized"], 0)
        self.assertFalse(frappe.db.exists("SP Home Preference", user))
        self.assertEqual(reset["categories"], global_layout["categories"])
        restored = next(row for row in reset["items"] if row["name"] == target)
        self.assertNotEqual(restored["custom_label"], "موقت")

    def test_icon_name_survives_without_desktop_icon_write(self):
        before = frappe.get_all(
            "Desktop Icon",
            fields=["name", "icon", "icon_image", "logo_url", "hidden", "idx", "parent_icon"],
            order_by="name",
        )
        payload = copy.deepcopy(self.layout)
        item = payload["items"][0]
        item.update(icon_name="users", custom_icon_image="")
        with patch.object(frappe, "publish_realtime"):
            result = api.save_layout(payload)
        saved = next(row for row in result["items"] if row["name"] == item["name"])
        self.assertEqual(saved["icon_name"], "users")
        self.assertEqual(before, frappe.get_all(
            "Desktop Icon",
            fields=["name", "icon", "icon_image", "logo_url", "hidden", "idx", "parent_icon"],
            order_by="name",
        ))

    def test_migration_backfill_is_idempotent(self):
        from smartprocee_erpnext_homepage.home_manager.migrate import sync_home_layout

        settings = frappe.get_single("SP Home Settings")
        styles = list(settings.styles)
        self.assertGreaterEqual(len(styles), 2)
        styles[0].category = "دسته نمایان"
        styles[0].hidden = 0
        styles[0].sequence = 50
        styles[1].category = "دسته پنهان"
        styles[1].hidden = 1
        styles[1].sequence = 1
        settings.set("categories", [])
        settings.gap_x = -20
        settings.gap_y = -5
        settings.save(ignore_permissions=True)
        sync_home_layout()
        first = frappe.get_single("SP Home Settings")
        ordered = [row.category_name for row in first.categories]
        self.assertLess(ordered.index("دسته نمایان"), ordered.index("دسته پنهان"))
        self.assertEqual(int(first.gap_x), -20)
        self.assertEqual(int(first.gap_y), -5)
        first.gap_x = api.GAP_MIN - 17
        first.gap_y = 90
        first.save(ignore_permissions=True)
        sync_home_layout()
        clamped = frappe.get_single("SP Home Settings")
        self.assertEqual(int(clamped.gap_x), api.GAP_MIN)
        self.assertEqual(int(clamped.gap_y), api.GAP_MAX)
        sync_home_layout()
        second = frappe.get_single("SP Home Settings")
        self.assertEqual([row.category_name for row in second.categories], ordered)
        self.assertEqual(len(second.categories), len(set(ordered)))

    def test_folder_persists_and_deletion_keeps_icons(self):
        payload = copy.deepcopy(self.layout)
        first, second = payload["items"][0], payload["items"][1]
        category = first["category"]
        before = frappe.get_all(
            "Desktop Icon",
            fields=["name", "icon", "hidden", "idx", "parent_icon"],
            order_by="name",
        )
        payload["folders"] = [{
            "folder_name": "عملیات",
            "category": category,
            "sequence": 1,
            "icon_name": "folder",
            "custom_icon_image": "",
        }]
        first.update(folder="عملیات", sequence=1, category=category)
        second.update(folder="عملیات", sequence=2, category=category)
        with patch.object(frappe, "publish_realtime"):
            saved = api.save_layout(payload)
        self.assertEqual([row["folder_name"] for row in saved["folders"]], ["عملیات"])
        members = [row["name"] for row in saved["items"] if row.get("folder") == "عملیات"]
        self.assertEqual(members[:2], [first["name"], second["name"]])
        cleared = copy.deepcopy(saved)
        cleared["folders"] = []
        for item in cleared["items"]:
            if item.get("folder") == "عملیات":
                item["folder"] = ""
        with patch.object(frappe, "publish_realtime"):
            result = api.save_layout(cleared)
        self.assertEqual(result["folders"], [])
        names = {row["name"] for row in result["items"]}
        self.assertIn(first["name"], names)
        self.assertIn(second["name"], names)
        for name in (first["name"], second["name"]):
            row = next(item for item in result["items"] if item["name"] == name)
            self.assertEqual(row.get("folder") or "", "")
        self.assertEqual(before, frappe.get_all(
            "Desktop Icon",
            fields=["name", "icon", "hidden", "idx", "parent_icon"],
            order_by="name",
        ))

    def test_old_preference_keeps_global_folder(self):
        user = self._make_user("sp-home-oldpref@example.com")
        frappe.set_user(user)
        visible = api.get_my_layout()["items"]
        self.assertTrue(visible)
        visible_name = visible[0]["name"]
        frappe.set_user("Administrator")
        payload = copy.deepcopy(api.get_layout())
        item = next(row for row in payload["items"] if row["name"] == visible_name)
        payload["folders"] = [{
            "folder_name": "عملیات",
            "category": item["category"],
            "sequence": 1,
            "icon_name": "folder",
            "custom_icon_image": "",
        }]
        item["folder"] = "عملیات"
        with patch.object(frappe, "publish_realtime"):
            api.save_layout(payload)
        frappe.set_user(user)
        personal = api.get_my_layout()
        for row in personal["items"]:
            row["folder"] = ""
        personal["folders"] = []
        with patch.object(frappe, "publish_realtime"):
            saved = api.save_my_layout(personal)
        kept = next(row for row in saved["items"] if row["name"] == visible_name)
        self.assertEqual(kept.get("folder"), "عملیات")

    def test_personal_layout_cannot_create_global_folder(self):
        user = self._make_user("sp-home-folder@example.com")
        frappe.set_user(user)
        payload = api.get_my_layout()
        payload["folders"] = [{
            "folder_name": "پوشه غیرمجاز",
            "category": "عمومی",
            "sequence": 1,
            "icon_name": "folder",
        }]
        payload["items"][0]["folder"] = "پوشه غیرمجاز"
        with patch.object(frappe, "publish_realtime"):
            saved = api.save_my_layout(payload)
        self.assertFalse(any(row["folder_name"] == "پوشه غیرمجاز" for row in saved.get("folders") or []))
        self.assertNotEqual(saved["items"][0].get("folder"), "پوشه غیرمجاز")
        frappe.set_user("Administrator")
        self.assertFalse(any(row["folder_name"] == "پوشه غیرمجاز" for row in api.get_layout().get("folders") or []))

    def test_manager_apis_reject_desk_user(self):
        user = self._make_user("sp-home-desk@example.com")
        frappe.set_user(user)
        with self.assertRaises(frappe.PermissionError):
            api.get_layout()
        with self.assertRaises(frappe.PermissionError):
            api.save_layout(self.layout)
        with self.assertRaises(frappe.PermissionError):
            api.create_desktop_icon("نباید ساخته شود")

    def test_client_has_no_fixed_icon_placement(self):
        root = frappe.get_app_path("smartprocee_erpnext_homepage")
        css = open(f"{root}/public/css/home_manager_desk.css", encoding="utf-8").read()
        desk = open(f"{root}/public/js/home_manager_desk.js", encoding="utf-8").read()
        editor_css = open(f"{root}/home_manager/page/home_manager/home_manager.css", encoding="utf-8").read()
        icon_js = open(f"{root}/public/js/home_icon.js", encoding="utf-8").read()
        self.assertNotIn("var(--sp-col)", css)
        self.assertNotIn("--sp-col:", css)
        self.assertNotIn("--sp-row", css)
        self.assertNotIn("translate:", css)
        self.assertNotIn("direction: rtl", css)
        self.assertNotIn("direction: rtl", editor_css)
        self.assertNotIn("parent_icon", desk)
        self.assertIn("replaceChildren", desk)
        editor = open(f"{root}/public/js/home_manager_editor.js", encoding="utf-8").read()
        self.assertNotIn("sp-home-card-meta", editor)
        self.assertNotIn("var(--sp-col)", editor)
        self.assertNotIn("--sp-row", editor)
        self.assertNotIn("translate(", editor)
        self.assertNotIn(':scope > .icon-container > img.app-icon', desk)
        image = icon_js.index("item.custom_icon_image")
        chosen = icon_js.index("item.icon_name")
        bundled = icon_js.index("if (bundledUrl)")
        native = icon_js.index("if (item.icon)")
        self.assertLess(image, chosen)
        self.assertLess(chosen, bundled)
        self.assertLess(bundled, native)
        self.assertIn(f"SP_HOME_GAP_MIN = {api.GAP_MIN}", icon_js)
        self.assertIn(f"SP_HOME_GAP_MAX = {api.GAP_MAX}", icon_js)
        self.assertIn("window.SP_HOME_GAP_MIN", editor)
        self.assertIn("window.SP_HOME_GAP_MIN", desk)
        self.assertNotIn(".sp-home-folder {\n\tgrid-column: 1 / -1;", css)
        self.assertIn("sp-folder-face", css)
        self.assertIn("sp-folder-preview", css)
        self.assertIn("is-drop-target", css)
        self.assertNotIn("sp-home-folder-cards", editor)
        self.assertNotIn("sp-folder-drawer", editor)
        self.assertIn("forceFallback: true", editor)
        self.assertIn("بازگشت به دسته", editor)
        self.assertNotIn('frappe.set_route("desktop")', editor)
        self.assertIn("sp-home-go-desktop", editor)
        self.assertIn("make_url", editor)
        self.assertIn("link.href = this.home_href()", editor)
        mode = icon_js.index("function sp_home_folder_icon_mode")
        members = icon_js.index("function sp_home_folder_members")
        face = icon_js.index("function sp_home_folder_face")
        self.assertLess(mode, face)
        self.assertIn(".slice(0, 4)", icon_js[members:members + 700])
        self.assertIn("sp_home_resolve_icon", icon_js[face:face + 1200])
        self.assertIn("sp_home_folder_face", desk)
        self.assertIn("sp_home_folder_face", editor)

    def test_category_rename_keeps_idx_icons_folders_and_preferences(self):
        payload = copy.deepcopy(self.layout)
        old = next(
            name for name in payload["categories"]
            if any(item["category"] == name for item in payload["items"])
        )
        new = "عملیات آزمون"
        index = payload["categories"].index(old)
        icon_order = [item["name"] for item in payload["items"] if item["category"] == old]
        folder_order = [folder["folder_name"] for folder in payload.get("folders") or [] if folder["category"] == old]
        for item in payload["items"]:
            if item["category"] == old:
                item["category"] = new
        for folder in payload.get("folders") or []:
            if folder["category"] == old:
                folder["category"] = new
        payload["categories"][index] = new
        payload["folders"] = list(payload.get("folders") or [])
        payload["folders"].append({
            "folder_name": "پوشه آزمون تغییر نام",
            "category": new,
            "sequence": 500,
            "icon_name": "folder",
            "custom_icon_image": "",
        })
        moved = next(item for item in payload["items"] if item["name"] == icon_order[0])
        moved["folder"] = "پوشه آزمون تغییر نام"
        payload["category_renames"] = [{"from": old, "to": new}]

        user = self._make_user("sp-home-rename@example.com")
        frappe.set_user(user)
        api.save_my_layout(api.get_my_layout())
        preference = frappe.get_doc("SP Home Preference", user)
        self.assertTrue(
            any((row.category_name or "") == old for row in preference.categories)
            or any((row.category or "") == old for row in preference.items)
        )
        frappe.set_user("Administrator")
        saved = api.save_layout(payload)
        self.assertEqual(saved["categories"][index], new)
        self.assertNotIn(old, saved["categories"])
        settings = frappe.get_single("SP Home Settings")
        row = next(entry for entry in settings.categories if entry.category_name == new)
        self.assertEqual(row.idx, index + 1)
        self.assertEqual(
            [item["name"] for item in saved["items"] if item["name"] in set(icon_order)],
            icon_order,
        )
        self.assertTrue(all(item["category"] != old for item in saved["items"]))
        self.assertEqual(
            [item["category"] for item in saved["items"] if item["name"] in set(icon_order)],
            [new] * len(icon_order),
        )
        renamed_folder = next(folder for folder in saved["folders"] if folder["folder_name"] == "پوشه آزمون تغییر نام")
        self.assertEqual(renamed_folder["category"], new)
        self.assertEqual(saved["items"][saved["items"].index(next(item for item in saved["items"] if item["name"] == icon_order[0]))]["folder"], "پوشه آزمون تغییر نام")
        self.assertEqual(
            [folder["folder_name"] for folder in saved["folders"] if folder["folder_name"] in set(folder_order)],
            folder_order,
        )
        frappe.set_user(user)
        mine = api.get_my_layout()
        self.assertNotIn(old, mine["categories"])
        self.assertIn(new, mine["categories"])
        self.assertFalse(any(item["category"] == old for item in mine["items"]))
        self.assertTrue(any(item["category"] == new for item in mine["items"]))
        preference = frappe.get_doc("SP Home Preference", user)
        self.assertFalse(any((row.category_name or "") == old for row in preference.categories))
        self.assertFalse(any((row.category or "") == old for row in list(preference.items) + list(preference.get("folders") or [])))
        self.assertEqual(
            self.before,
            frappe.get_all("Desktop Icon", fields=["name", "hidden", "idx", "parent_icon"], order_by="name"),
        )

    def test_deleted_global_category_is_not_restored_by_preference(self):
        payload = copy.deepcopy(self.layout)
        stale = "دسته حذف شده آزمون"
        payload["categories"] = list(payload["categories"]) + [stale]
        icon = next(item for item in payload["items"] if not item.get("hidden"))
        folder_name = "پوشه دسته معتبر"
        valid_category = icon["category"]
        payload["folders"] = list(payload.get("folders") or []) + [{
            "folder_name": folder_name,
            "category": valid_category,
            "sequence": 3,
            "icon_name": "",
            "custom_icon_image": "",
        }]
        with patch.object(frappe, "publish_realtime"):
            api.save_layout(payload)

        personal = api.get_my_layout()
        self.assertIn(stale, personal["categories"])
        for item in personal["items"]:
            if item["name"] == icon["name"]:
                item["sequence"] = 7
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(personal)

        removed = api.get_layout()
        removed["categories"] = [name for name in removed["categories"] if name != stale]
        with patch.object(frappe, "publish_realtime"):
            api.save_layout(removed)
        preference = frappe.get_doc("SP Home Preference", "Administrator")
        self.assertNotIn(stale, [row.category_name for row in preference.categories])
        preference.append("categories", {"category_name": stale})
        preference.save(ignore_permissions=True)

        current = api.get_current_layout()
        boot = api.get_boot_layout()
        self.assertNotIn(stale, current["categories"])
        self.assertNotIn(stale, boot["categories"])
        kept = next(item for item in current["items"] if item["name"] == icon["name"])
        self.assertEqual(kept["category"], valid_category)
        self.assertEqual(kept["sequence"], 7)
        self.assertIn(valid_category, current["categories"])
        self.assertTrue(any(
            folder["folder_name"] == folder_name and folder["category"] == valid_category
            for folder in current["folders"]
        ))
        self.assertIn(icon["name"], [item["name"] for item in current["items"]])

        again = api.get_layout()
        self.assertNotIn(stale, again["categories"])
        self.assertIn(icon["name"], [item["name"] for item in again["items"]])
        self.assertTrue(any(folder["folder_name"] == folder_name for folder in again["folders"]))

    def test_empty_category_can_be_deleted(self):
        payload = copy.deepcopy(self.layout)
        payload["categories"] = list(payload["categories"]) + ["دسته خالی آزمون"]
        saved = api.save_layout(payload)
        self.assertIn("دسته خالی آزمون", saved["categories"])
        saved["categories"] = [name for name in saved["categories"] if name != "دسته خالی آزمون"]
        again = api.save_layout(saved)
        self.assertNotIn("دسته خالی آزمون", again["categories"])

    def test_non_empty_category_cannot_be_deleted(self):
        payload = copy.deepcopy(self.layout)
        target = next(name for name in payload["categories"] if any(item["category"] == name for item in payload["items"]))
        payload["categories"] = [name for name in payload["categories"] if name != target]
        saved = api.save_layout(payload)
        self.assertIn(target, saved["categories"])

    def test_category_with_folder_cannot_be_deleted(self):
        payload = copy.deepcopy(self.layout)
        name = "دسته فقط پوشه"
        payload["categories"] = list(payload["categories"]) + [name]
        payload["folders"] = list(payload.get("folders") or []) + [{
            "folder_name": "پوشه مانع حذف",
            "category": name,
            "sequence": 1,
            "icon_name": "folder",
        }]
        saved = api.save_layout(payload)
        self.assertIn(name, saved["categories"])
        saved["categories"] = [row for row in saved["categories"] if row != name]
        again = api.save_layout(saved)
        self.assertIn(name, again["categories"])
        self.assertTrue(any(
            folder["folder_name"] == "پوشه مانع حذف" and folder["category"] == name
            for folder in again["folders"]
        ))

    def test_gap_range_survives_and_clamps(self):
        payload = copy.deepcopy(self.layout)
        cases = (
            (20, 20, 20, 20),
            (0, 0, 0, 0),
            (-10, -10, -10, -10),
            (-20, -20, -20, -20),
            (api.GAP_MIN, api.GAP_MIN, api.GAP_MIN, api.GAP_MIN),
            (api.GAP_MIN - 10, 90, api.GAP_MIN, 48),
        )
        for gap_x, gap_y, expected_x, expected_y in cases:
            payload["gap_x"] = gap_x
            payload["gap_y"] = gap_y
            saved = api.save_layout(payload)
            self.assertEqual((saved["gap_x"], saved["gap_y"]), (expected_x, expected_y))
        self.assertEqual(
            self.before,
            frappe.get_all("Desktop Icon", fields=["name", "hidden", "idx", "parent_icon"], order_by="name"),
        )

    def test_appearance_save_does_not_write_desktop_icon(self):
        payload = copy.deepcopy(self.layout)
        payload["default_shape"] = "circle"
        payload["default_size"] = "large"
        payload["icon_style"] = "Subtle"
        payload["items"][0]["shape"] = "square"
        payload["items"][0]["size"] = "small"
        payload["items"][0]["use_custom_style"] = 1
        payload["items"][0]["custom_color"] = "#0289F7"
        api.save_layout(payload)
        self.assertEqual(
            self.before,
            frappe.get_all("Desktop Icon", fields=["name", "hidden", "idx", "parent_icon"], order_by="name"),
        )

    def _loose_icons(self, payload, category, count):
        icons = [
            item for item in payload["items"]
            if item.get("category") == category and not item.get("folder") and not item.get("hidden") and item.get("icon_type") != "Folder"
        ]
        self.assertGreaterEqual(len(icons), count)
        return icons[:count]

    def test_mixed_folder_order_persists_between_icons(self):
        payload = copy.deepcopy(self.layout)
        category = next(
            name for name in payload["categories"]
            if sum(1 for item in payload["items"] if item.get("category") == name and not item.get("folder") and not item.get("hidden")) >= 4
        )
        icons = self._loose_icons(payload, category, 4)
        icons[0]["sequence"] = 10
        icons[1]["sequence"] = 20
        icons[2]["sequence"] = 40
        icons[3]["sequence"] = 50
        payload["folders"] = [row for row in payload.get("folders") or [] if row.get("category") != category]
        payload["folders"].append({
            "folder_name": "پوشه ترتیب",
            "category": category,
            "sequence": 30,
            "icon_name": "",
            "custom_icon_image": "",
        })
        saved = api.save_layout(payload)
        wanted = {icons[0]["name"], icons[1]["name"], icons[2]["name"], icons[3]["name"], "پوشه ترتیب"}
        expected = [
            ("icon", icons[0]["name"]),
            ("icon", icons[1]["name"]),
            ("folder", "پوشه ترتیب"),
            ("icon", icons[2]["name"]),
            ("icon", icons[3]["name"]),
        ]
        self.assertEqual([entry for entry in api.category_entries(saved, category) if entry[1] in wanted], expected)
        reloaded = api.get_layout()
        self.assertEqual([entry for entry in api.category_entries(reloaded, category) if entry[1] in wanted], expected)
        self.assertEqual(
            self.before,
            frappe.get_all("Desktop Icon", fields=["name", "hidden", "idx", "parent_icon"], order_by="name"),
        )

    def test_folder_preview_order_limit_and_explicit_icon(self):
        payload = copy.deepcopy(self.layout)
        category = next(
            name for name in payload["categories"]
            if sum(1 for item in payload["items"] if item.get("category") == name and not item.get("hidden")) >= 5
        )
        icons = [
            item for item in payload["items"]
            if item.get("category") == category and not item.get("hidden") and item.get("icon_type") != "Folder"
        ][:5]
        folder = {
            "folder_name": "پوشه پیش‌نمایش",
            "category": category,
            "sequence": 1,
            "icon_name": "",
            "custom_icon_image": "",
        }
        payload["folders"] = list(payload.get("folders") or []) + [folder]
        for index, item in enumerate(icons, start=1):
            item["folder"] = folder["folder_name"]
            item["category"] = category
            item["sequence"] = index * 10
        saved = api.save_layout(payload)
        stored = next(row for row in saved["folders"] if row["folder_name"] == folder["folder_name"])
        self.assertEqual(stored["icon_mode"], "preview")
        self.assertEqual(stored["preview"], [item["name"] for item in icons[:4]])
        self.assertNotIn(icons[4]["name"], stored["preview"])
        self.assertEqual(api.folder_icon_mode({"custom_icon_image": "/files/folder.png", "icon_name": "heart"}), "image")

        payload = api.get_layout()
        stored = next(row for row in payload["folders"] if row["folder_name"] == folder["folder_name"])
        stored["icon_name"] = "accounting"
        stored["custom_icon_image"] = ""
        chosen = api.save_layout(payload)
        stored = next(row for row in chosen["folders"] if row["folder_name"] == folder["folder_name"])
        self.assertEqual(stored["icon_mode"], "icon")
        self.assertEqual(stored["icon_name"], "accounting")

        payload = api.get_layout()
        stored = next(row for row in payload["folders"] if row["folder_name"] == folder["folder_name"])
        stored["icon_name"] = ""
        stored["custom_icon_image"] = ""
        cleared = api.save_layout(payload)
        stored = next(row for row in cleared["folders"] if row["folder_name"] == folder["folder_name"])
        self.assertEqual(stored["icon_mode"], "preview")
        self.assertEqual(stored["preview"], [item["name"] for item in icons[:4]])
        self.assertEqual(
            self.before,
            frappe.get_all("Desktop Icon", fields=["name", "hidden", "idx", "parent_icon"], order_by="name"),
        )

    def test_personal_folder_preview_uses_that_users_order(self):
        payload = copy.deepcopy(self.layout)
        category = next(
            name for name in payload["categories"]
            if sum(1 for item in payload["items"] if item.get("category") == name and not item.get("hidden")) >= 5
        )
        icons = [
            item for item in payload["items"]
            if item.get("category") == category and not item.get("hidden") and item.get("icon_type") != "Folder"
        ][:5]
        payload["folders"] = list(payload.get("folders") or []) + [{
            "folder_name": "پوشه شخصی",
            "category": category,
            "sequence": 5,
            "icon_name": "",
            "custom_icon_image": "",
        }]
        for index, item in enumerate(icons, start=1):
            item["folder"] = "پوشه شخصی"
            item["sequence"] = index
        api.save_layout(payload)

        user = self._make_user("sp-home-preview@example.com")
        frappe.set_user(user)
        personal = api.get_my_layout()
        for item in personal["items"]:
            if item["name"] == icons[0]["name"]:
                item["sequence"] = 50
            elif item["name"] == icons[1]["name"]:
                item["sequence"] = 40
            elif item["name"] == icons[2]["name"]:
                item["sequence"] = 30
            elif item["name"] == icons[3]["name"]:
                item["sequence"] = 20
            elif item["name"] == icons[4]["name"]:
                item["sequence"] = 10
        saved = api.save_my_layout(personal)
        stored = next(row for row in saved["folders"] if row["folder_name"] == "پوشه شخصی")
        visible_names = {item["name"] for item in saved["items"]}
        expected = [
            item["name"] for item in (icons[4], icons[3], icons[2], icons[1], icons[0])
            if item["name"] in visible_names
        ][:4]
        self.assertEqual(stored["preview"], expected)
        self.assertLessEqual(len(stored["preview"]), 4)
        self.assertEqual(stored["icon_mode"], "preview")
        frappe.set_user("Administrator")
        admin = api.get_layout()
        admin_folder = next(row for row in admin["folders"] if row["folder_name"] == "پوشه شخصی")
        self.assertEqual(admin_folder["preview"], [item["name"] for item in icons[:4]])
        self.assertEqual(
            self.before,
            frappe.get_all("Desktop Icon", fields=["name", "hidden", "idx", "parent_icon"], order_by="name"),
        )

    def test_permission_filter_is_dynamic_and_keeps_preference(self):
        user_a = self._make_user("sp-home-access-a@example.com")
        user_b = self._make_user("sp-home-access-b@example.com")
        user_c = self._make_user("sp-home-access-c@example.com")
        self._ensure_role(user_a, "System Manager")
        frappe.set_user(user_b)
        visible = [
            item for item in api.get_current_layout()["items"]
            if item.get("link_type") != "External" and item.get("icon_type") != "App"
        ]
        self.assertGreaterEqual(len(visible), 3)
        selling, buying, stock = visible[:3]
        wanted = [selling["name"], buying["name"], stock["name"]]
        payload = copy.deepcopy(api.get_my_layout())
        for item in payload["items"]:
            if item["name"] == selling["name"]:
                item["sequence"] = 10
            elif item["name"] == buying["name"]:
                item["sequence"] = 20
            elif item["name"] == stock["name"]:
                item["sequence"] = 30
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(payload)
        self.assertEqual(self._names_in_order(api.get_current_layout(), wanted), wanted)

        frappe.set_user("Administrator")
        self._set_desktop_icon_roles(buying["name"], ["System Manager"])
        frappe.set_user(user_a)
        self.assertIn(buying["name"], [item["name"] for item in api.get_layout()["items"]])
        self.assertIn(buying["name"], [item["name"] for item in api.get_current_layout()["items"]])
        frappe.set_user(user_b)
        hidden = api.get_current_layout()
        self.assertNotIn(buying["name"], [item["name"] for item in hidden["items"]])
        self.assertEqual(self._names_in_order(hidden, wanted), [selling["name"], stock["name"]])
        self.assertEqual(self._preference_sequence(user_b, buying["name"]), 20)
        editor = api.get_my_layout()
        self.assertNotIn(buying["name"], [item["name"] for item in editor["items"]])
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(editor)
        self.assertEqual(self._preference_sequence(user_b, buying["name"]), 20)
        self.assertEqual(self._preference_value(user_b, buying["name"], "hidden"), 0)

        frappe.set_user("Administrator")
        self._set_desktop_icon_roles(buying["name"], [])
        frappe.set_user(user_b)
        self.assertEqual(self._names_in_order(api.get_current_layout(), wanted), wanted)
        self.assertEqual(self._preference_sequence(user_b, buying["name"]), 20)

        frappe.set_user("Administrator")
        layout = copy.deepcopy(api.get_layout())
        mixed = "Mixed Access"
        closed = "Closed Access"
        layout["folders"] = [
            {"folder_name": mixed, "category": stock["category"], "sequence": 1, "icon_name": "", "custom_icon_image": ""},
            {"folder_name": closed, "category": selling["category"], "sequence": 2, "icon_name": "", "custom_icon_image": ""},
        ]
        for item in layout["items"]:
            if item["name"] == buying["name"]:
                item.update(folder=mixed, sequence=1, category=stock["category"])
            elif item["name"] == stock["name"]:
                item.update(folder=mixed, sequence=2, category=stock["category"])
            elif item["name"] == selling["name"]:
                item.update(folder=closed, sequence=1, category=selling["category"])
        with patch.object(frappe, "publish_realtime"):
            api.save_layout(layout)
        self._set_desktop_icon_roles(buying["name"], ["System Manager"])
        self._set_desktop_icon_roles(selling["name"], ["System Manager"])

        frappe.set_user(user_a)
        manager = api.get_layout()
        self.assertIn(buying["name"], [item["name"] for item in manager["items"]])
        self.assertIn(selling["name"], [item["name"] for item in manager["items"]])
        self.assertEqual(
            {row["folder_name"] for row in manager["folders"]},
            {mixed, closed},
        )
        frappe.set_user(user_c)
        personal = api.get_current_layout()
        self.assertNotIn(buying["name"], [item["name"] for item in personal["items"]])
        self.assertNotIn(selling["name"], [item["name"] for item in personal["items"]])
        mixed_row = next(row for row in personal["folders"] if row["folder_name"] == mixed)
        self.assertEqual(mixed_row["preview"], [stock["name"]])
        self.assertNotIn(closed, [row["folder_name"] for row in personal["folders"]])
        self.assertFalse(any(item.get("folder") == closed for item in personal["items"]))

        frappe.set_user("Administrator")
        stored = api.get_layout()
        self.assertEqual(
            {item["name"] for item in stored["items"] if item.get("folder") == mixed},
            {buying["name"], stock["name"]},
        )
        self.assertEqual(
            [item["name"] for item in stored["items"] if item.get("folder") == closed],
            [selling["name"]],
        )
        self._set_desktop_icon_roles(buying["name"], [])
        self._set_desktop_icon_roles(selling["name"], [])
        frappe.set_user(user_c)
        restored = api.get_current_layout()
        self.assertEqual(
            [item["name"] for item in restored["items"] if item.get("folder") == mixed],
            [buying["name"], stock["name"]],
        )
        self.assertIn(closed, [row["folder_name"] for row in restored["folders"]])
        self.assertEqual(
            next(row["preview"] for row in restored["folders"] if row["folder_name"] == mixed),
            [buying["name"], stock["name"]],
        )
        frappe.set_user("Administrator")
        self.assertEqual(
            self.before,
            frappe.get_all("Desktop Icon", fields=["name", "hidden", "idx", "parent_icon"], order_by="name"),
        )

    def _icon_by_label(self, label):
        return next(item for item in self.layout["items"] if item["label"] == label)

    def _names_in_order(self, layout, names):
        rows = [item for item in layout["items"] if item["name"] in names]
        return [item["name"] for item in sorted(rows, key=lambda item: (item["sequence"], item["name"]))]

    def _preference_sequence(self, user, icon_name):
        return self._preference_value(user, icon_name, "sequence")

    def _preference_value(self, user, icon_name, fieldname):
        doc = frappe.get_doc("SP Home Preference", user)
        row = next(item for item in doc.items if item.desktop_icon == icon_name)
        return row.get(fieldname)

    def _ensure_role(self, email, role):
        if role in frappe.get_roles(email):
            return
        user = frappe.get_doc("User", email)
        user.append("roles", {"role": role})
        user.save(ignore_permissions=True)

    def _set_desktop_icon_roles(self, name, roles):
        frappe.db.delete("Has Role", {"parent": name, "parenttype": "Desktop Icon", "parentfield": "roles"})
        for idx, role in enumerate(roles, start=1):
            frappe.get_doc({
                "doctype": "Has Role",
                "parent": name,
                "parenttype": "Desktop Icon",
                "parentfield": "roles",
                "role": role,
                "idx": idx,
            }).insert(ignore_permissions=True)

    def _make_user(self, email):
        if frappe.db.exists("User", email):
            return email
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": email.split("@")[0],
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "System User",
            "roles": [{"role": "Desk User"}],
        })
        user.insert(ignore_permissions=True)
        return email


def run_checks():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestHomeLayout))
    if not result.wasSuccessful():
        raise AssertionError("Home Manager checks failed")
    return {"tests": result.testsRun, "passed": True}
