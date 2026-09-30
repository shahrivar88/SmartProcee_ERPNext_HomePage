"""Database round-trip checks, rolled back after each test; no core fixtures."""
import copy
import json
import os
import shutil
import subprocess
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

    def test_personal_save_does_not_change_global_or_other_users(self):
        user_a = self._make_user("sp-home-only-a@example.com")
        user_b = self._make_user("sp-home-only-b@example.com")
        frappe.set_user("Administrator")
        before = api.get_layout()
        frappe.set_user(user_a)
        payload = copy.deepcopy(api.get_my_layout())
        self.assertEqual(payload["can_publish_global"], 0)
        target = payload["items"][0]["name"]
        payload["user"] = "Administrator"
        payload["columns"] = 2 if before["columns"] != 2 else 3
        payload["items"][0]["custom_label"] = "فقط کاربر الف"
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(payload)
        with self.assertRaises(frappe.PermissionError):
            api.save_as_global_default(payload)
        with self.assertRaises(frappe.PermissionError):
            api.delete_owned_desktop_icon("Selling")
        frappe.set_user("Administrator")
        again = api.get_layout()
        self.assertEqual(again["columns"], before["columns"])
        admin_label = next(row["custom_label"] for row in again["items"] if row["name"] == target)
        self.assertNotEqual(admin_label, "فقط کاربر الف")
        frappe.set_user(user_a)
        self.assertEqual(api.get_my_layout()["columns"], payload["columns"])
        self.assertEqual(frappe.db.get_value("SP Home Preference", user_a, "columns_override"), str(payload["columns"]))
        frappe.set_user(user_b)
        theirs = api.get_my_layout()
        self.assertEqual(theirs["personalized"], 0)
        self.assertNotEqual(
            next(row.get("custom_label") for row in theirs["items"] if row["name"] == target),
            "فقط کاربر الف",
        )

    def test_save_as_global_resets_only_current_manager(self):
        user_keep = self._make_user("sp-home-keep@example.com")
        user_plain = self._make_user("sp-home-plain@example.com")
        before_preferences = set(frappe.get_all("SP Home Preference", pluck="name"))
        frappe.set_user(user_keep)
        kept = copy.deepcopy(api.get_my_layout())
        kept_name = kept["items"][0]["name"]
        kept["items"][0]["custom_label"] = "باقی بماند"
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(kept)
        frappe.set_user("Administrator")
        published = copy.deepcopy(api.get_my_layout())
        published["columns"] = 7
        published["items"][0]["custom_label"] = "پیش‌فرض تازه"
        if len(published["categories"]) > 1:
            published["categories"] = published["categories"][1:] + published["categories"][:1]
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(copy.deepcopy(published))
            result = api.save_as_global_default(published)
        self.assertEqual(result["can_publish_global"], 1)
        self.assertEqual(result["personalized"], 0)
        self.assertEqual(result["columns"], 7)
        self.assertFalse(frappe.db.exists("SP Home Preference", "Administrator"))
        after_preferences = set(frappe.get_all("SP Home Preference", pluck="name"))
        self.assertIn(user_keep, after_preferences)
        self.assertTrue(before_preferences - {"Administrator"} <= after_preferences)
        global_layout = api.get_layout()
        self.assertEqual(global_layout["columns"], 7)
        self.assertEqual(result["categories"], global_layout["categories"])
        frappe.set_user(user_plain)
        plain = api.get_my_layout()
        self.assertEqual(plain["personalized"], 0)
        self.assertEqual(plain["columns"], 7)
        self.assertEqual(plain["can_publish_global"], 0)
        frappe.set_user(user_keep)
        kept_again = api.get_my_layout()
        label = next(row for row in kept_again["items"] if row["name"] == kept_name)
        self.assertEqual(label["custom_label"], "باقی بماند")
        self.assertEqual(kept_again["personalized"], 1)
        self.assertEqual(kept_again["columns"], 7)

    def test_reset_affects_only_the_current_user(self):
        user_a = self._make_user("sp-home-reset-a@example.com")
        user_b = self._make_user("sp-home-reset-b@example.com")
        frappe.set_user("Administrator")
        columns = api.get_layout()["columns"]
        frappe.set_user(user_a)
        payload_a = copy.deepcopy(api.get_my_layout())
        name = payload_a["items"][0]["name"]
        payload_a["items"][0]["custom_label"] = "الف موقت"
        frappe.set_user(user_b)
        payload_b = copy.deepcopy(api.get_my_layout())
        payload_b["items"][0]["custom_label"] = "ب ماند"
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(payload_b)
            frappe.set_user(user_a)
            api.save_my_layout(payload_a)
            api.reset_my_layout()
        self.assertFalse(frappe.db.exists("SP Home Preference", user_a))
        self.assertTrue(frappe.db.exists("SP Home Preference", user_b))
        frappe.set_user("Administrator")
        self.assertEqual(api.get_layout()["columns"], columns)
        frappe.set_user(user_b)
        kept = api.get_my_layout()
        self.assertEqual(next(row["custom_label"] for row in kept["items"] if row["name"] == name), "ب ماند")

    def test_personal_visual_settings_round_trip(self):
        user_a = self._make_user("sp-home-metrics-a@example.com")
        user_b = self._make_user("sp-home-metrics-b@example.com")
        frappe.set_user("Administrator")
        before = api.get_layout()
        admin_before = {
            key: api.get_my_layout()[key]
            for key in ("columns", "gap_x", "gap_y", "default_shape", "default_size", "icon_style")
        }
        frappe.set_user(user_a)
        payload = copy.deepcopy(api.get_my_layout())
        first = payload["items"][0]["name"]
        second = payload["items"][1]["name"]
        payload["items"][0]["sequence"] = 2
        payload["items"][1]["sequence"] = 1
        payload.update(columns=4, gap_x=10, gap_y=12, default_shape="circle", default_size="large", icon_style="Subtle")
        with patch.object(frappe, "publish_realtime"):
            saved = api.save_my_layout(payload)
        self.assertEqual(
            (saved["columns"], saved["gap_x"], saved["gap_y"], saved["default_shape"], saved["default_size"], saved["icon_style"]),
            (4, 10, 12, "circle", "large", "Subtle"),
        )
        plain = next(row for row in saved["items"] if not row.get("use_custom_style"))
        self.assertEqual((plain["shape"], plain["size"]), ("circle", "large"))
        order = [row["name"] for row in saved["items"] if row["category"] == payload["items"][0]["category"] and not row.get("folder")]
        self.assertLess(order.index(second), order.index(first))
        preference = frappe.get_doc("SP Home Preference", user_a)
        self.assertEqual(preference.columns_override, "4")
        self.assertEqual(preference.gap_x_override, "10")
        self.assertEqual(preference.gap_y_override, "12")
        self.assertEqual(preference.default_shape_override, "circle")
        self.assertEqual(preference.default_size_override, "large")
        self.assertEqual(preference.icon_style_override, "Subtle")
        frappe.set_user("Administrator")
        global_after = api.get_layout()
        for key in ("columns", "gap_x", "gap_y", "default_shape", "default_size", "icon_style"):
            self.assertEqual(global_after[key], before[key])
            self.assertEqual(api.get_my_layout()[key], admin_before[key])
        frappe.set_user(user_b)
        other = api.get_my_layout()
        self.assertEqual(other["default_shape"], before["default_shape"])
        self.assertEqual(other["columns"], before["columns"])
        self.assertEqual(other["gap_x"], before["gap_x"])
        frappe.set_user(user_a)
        again = api.get_my_layout()
        self.assertEqual(again["default_shape"], "circle")
        self.assertEqual(again["default_size"], "large")
        self.assertEqual((again["columns"], again["gap_x"], again["gap_y"]), (4, 10, 12))
        restored = copy.deepcopy(again)
        for key in ("columns", "gap_x", "gap_y", "default_shape", "default_size", "icon_style"):
            restored[key] = before[key]
        with patch.object(frappe, "publish_realtime"):
            matched = api.save_my_layout(restored)
        self.assertEqual(matched["default_shape"], before["default_shape"])
        cleared = frappe.get_doc("SP Home Preference", user_a)
        self.assertFalse(cleared.default_shape_override)
        self.assertFalse(cleared.columns_override)
        self.assertFalse(cleared.gap_x_override)
        self.assertFalse(cleared.gap_y_override)
        self.assertFalse(cleared.default_size_override)
        with patch.object(frappe, "publish_realtime"):
            reset = api.reset_my_layout()
        self.assertFalse(frappe.db.exists("SP Home Preference", user_a))
        for key in ("columns", "gap_x", "gap_y", "default_shape", "default_size"):
            self.assertEqual(reset[key], before[key])

    def test_global_visual_settings_round_trip(self):
        user_override = self._make_user("sp-home-metrics-keep@example.com")
        user_plain = self._make_user("sp-home-metrics-plain@example.com")
        frappe.set_user("Administrator")
        before = {
            key: api.get_layout()[key]
            for key in ("columns", "gap_x", "gap_y", "default_shape", "default_size", "icon_style")
        }
        frappe.set_user(user_override)
        personal = copy.deepcopy(api.get_my_layout())
        personal.update(default_shape="square", columns=3)
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(personal)
        frappe.set_user("Administrator")
        published = copy.deepcopy(api.get_my_layout())
        published.update(columns=4, gap_x=10, gap_y=12, default_shape="circle", default_size="large", icon_style="Subtle")
        with patch.object(frappe, "publish_realtime"):
            result = api.save_as_global_default(published)
        self.assertFalse(frappe.db.exists("SP Home Preference", "Administrator"))
        self.assertEqual(
            (result["columns"], result["gap_x"], result["gap_y"], result["default_shape"], result["default_size"], result["icon_style"]),
            (4, 10, 12, "circle", "large", "Subtle"),
        )
        stored = api.get_layout()
        for key, value in (
            ("columns", 4), ("gap_x", 10), ("gap_y", 12),
            ("default_shape", "circle"), ("default_size", "large"), ("icon_style", "Subtle"),
        ):
            self.assertEqual(stored[key], value)
        frappe.set_user(user_plain)
        plain = api.get_my_layout()
        self.assertEqual(plain["default_shape"], "circle")
        self.assertEqual(plain["columns"], 4)
        self.assertEqual(plain["gap_y"], 12)
        frappe.set_user(user_override)
        kept = api.get_my_layout()
        self.assertEqual(kept["default_shape"], "square")
        self.assertEqual(kept["columns"], 3)
        self.assertEqual(kept["default_size"], "large")
        self.assertEqual(kept["gap_x"], 10)
        self.assertEqual(kept["gap_y"], 12)
        frappe.set_user("Administrator")
        current = api.get_layout()
        current.update(before)
        with patch.object(frappe, "publish_realtime"):
            api.save_layout(current)

    def test_guest_cannot_customize_home(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            api.get_my_layout()
        with self.assertRaises(frappe.PermissionError):
            api.save_my_layout({"items": []})
        with self.assertRaises(frappe.PermissionError):
            api.save_as_global_default({"items": []})
        with self.assertRaises(frappe.PermissionError):
            api.reset_my_layout()

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
        if len(settings.styles) < 2:
            # A fresh install has no style rows until the first layout save.
            with patch.object(frappe, "publish_realtime"):
                api.save_layout(copy.deepcopy(self.layout))
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
        api._drop_missing_icon_rows(settings)
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
        with self.assertRaises(frappe.PermissionError):
            api.delete_owned_desktop_icon("Selling")

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
        self.assertIn("sp-home-slot", css)
        self.assertIn("is-drop-target", css)
        self.assertNotIn("sp-home-folder-cards", editor)
        self.assertNotIn("sp-folder-drawer", editor)
        self.assertNotIn("forceFallback", editor)
        self.assertNotIn("invertSwap", editor)
        self.assertNotIn("suppress_folder_click", editor)
        self.assertNotIn("setTimeout", editor)
        self.assertNotIn("ghostClass", editor)
        self.assertNotIn("onMove:", editor)
        self.assertIn("sp_home_slot_index", editor)
        self.assertIn("sp-home-slot", editor)
        self.assertIn("this.dragging", editor)
        self.assertIn("ذخیره چیدمان من", editor)
        self.assertNotIn("ذخیره این چیدمان به‌عنوان پیش‌فرض عمومی", editor)
        self.assertNotIn("بازنشانی به چیدمان پیش‌فرض", editor)
        self.assertNotIn("رفتن به صفحه اصلی", editor)
        menu = editor[editor.index("ensure_menu() {"):]
        menu = menu[:menu.index("\n\t}\n")]
        home = menu.index('add_menu_item(__("صفحه اصلی")')
        publish = menu.index('add_menu_item(__("ذخیره به عنوان پیش‌فرض")')
        reset = menu.index('add_menu_item(__("بازنشانی چیدمان پیش‌فرض")')
        self.assertLess(home, publish)
        self.assertLess(publish, reset)
        self.assertIn("if (this.can_publish)", menu[home:publish])
        self.assertIn("this.publish_global()", menu)
        self.assertIn("this.reset_personal()", menu)
        self.assertNotIn("add_inner_button", editor)
        self.assertNotIn("this.page.set_secondary_action", editor)
        self.assertNotIn("بازنشانی چیدمان من", editor)
        self.assertNotIn("چیدمان پیش‌فرض عمومی", editor)
        self.assertNotIn(">چیدمان من<", desk)
        self.assertIn("تنظیم صفحه اصلی", desk)
        self.assertIn("sp-home-gear-btn", desk)
        self.assertNotIn("sp-home-personal-btn' href", desk)
        self.assertIn("display: flex", css)
        self.assertIn(".sp-home-editor .sp-home-mixed", css)
        self.assertIn("save_as_global_default", open(f"{root}/home_manager/api.py", encoding="utf-8").read())
        self.assertIn("بازگشت به دسته", editor)
        self.assertNotIn('frappe.set_route("desktop")', editor)
        self.assertNotIn("sp-home-go-desktop", editor)
        self.assertIn("make_url", editor)
        self.assertIn('.attr("href", this.home_href())', editor)
        mode = icon_js.index("function sp_home_folder_icon_mode")
        members = icon_js.index("function sp_home_folder_members")
        face = icon_js.index("function sp_home_folder_face")
        self.assertLess(mode, face)
        self.assertIn(".slice(0, 4)", icon_js[members:members + 700])
        self.assertIn("sp_home_resolve_icon", icon_js[face:face + 1200])
        self.assertIn("sp_home_folder_face", desk)
        self.assertIn("delete_owned_desktop_icon", editor)
        self.assertIn("item.owned", editor)
        self.assertIn("item.hidden = 1", editor)
        self.assertIn("مخفی کردن از صفحه اصلی", editor)
        self.assertIn("حذف دائمی آیکون سفارشی", editor)
        self.assertIn("این مخفی کردن نیست", editor)
        self.assertIn("sp_home_folder_face", editor)

    def test_mixed_order_insertion_boundaries(self):
        insertion_index = _js_insertion_index

        def center(col, track=100, origin_right=1000):
            return origin_right - (col + 1) * track + track / 2

        def row_y(row, row_height=80, gap=0):
            return row * (row_height + gap) + row_height / 2

        def drop(order, moving, columns, boundary, row, track=100):
            names = [name for name in order if name != moving]
            rects = _wrapped_rects(len(names), columns, track=track)
            start = row * columns
            row_count = min(columns, max(len(names) - start, 1))
            if boundary <= 0:
                x = center(0, track=track) + track * 0.2
            elif boundary >= row_count:
                x = center(row_count - 1, track=track) - track * 0.2
            else:
                x = (center(boundary - 1, track=track) + center(boundary, track=track)) / 2
            index = insertion_index(rects, {"x": x, "y": row_y(row)}, True)
            names.insert(index, moving)
            return "".join(names)

        one_row = _wrapped_rects(6, 6)
        y = row_y(0)
        self.assertEqual(insertion_index(one_row, {"x": center(0) + 8, "y": y}, True), 0)
        self.assertEqual(insertion_index(one_row, {"x": center(5) - 8, "y": y}, True), 6)
        for boundary in range(1, 6):
            midpoint = (center(boundary - 1) + center(boundary)) / 2
            self.assertEqual(insertion_index(one_row, {"x": midpoint, "y": y}, True), boundary)
        # RTL: right of a card's center is before it, left of it is after it.
        self.assertEqual(insertion_index(one_row, {"x": center(3) + 5, "y": y}, True), 3)
        self.assertEqual(insertion_index(one_row, {"x": center(3) - 5, "y": y}, True), 4)
        ltr = [dict(rect, left=900 - rect["left"]) for rect in one_row]
        self.assertEqual(insertion_index(ltr, {"x": ltr[3]["left"] + 45, "y": y}, False), 3)
        self.assertEqual(insertion_index(ltr, {"x": ltr[3]["left"] + 55, "y": y}, False), 4)

        self.assertEqual(drop("ABCDEF", "F", 6, 2, 0), "ABFCDE")
        self.assertEqual(drop("ABCDEF", "A", 6, 3, 0), "BCDAEF")
        self.assertEqual(drop("ABCDEF", "A", 6, 5, 0), "BCDEFA")
        self.assertEqual(drop("ABCDEF", "F", 6, 0, 0), "FABCDE")

        grid = "ABCDEFGHIJKL"
        self.assertEqual(drop(grid, "F", 6, 2, 0), "ABFCDEGHIJKL")
        self.assertEqual(drop(grid, "A", 6, 3, 0), "BCDAEFGHIJKL")
        self.assertEqual(drop(grid, "A", 6, 5, 1), "BCDEFGHIJKLA")
        self.assertEqual(drop(grid, "F", 6, 0, 0), "FABCDEGHIJKL")
        self.assertEqual(drop(grid, "A", 6, 2, 1), "BCDEFGHIAJKL")
        self.assertEqual(drop(grid, "L", 6, 3, 0), "ABCLDEFGHIJK")
        self.assertEqual(drop(grid, "C", 6, 3, 0), "ABDCEFGHIJKL")
        self.assertEqual(drop(grid, "D", 6, 1, 1), "ABCEFGHDIJKL")
        self.assertEqual(drop(grid, "I", 6, 2, 0), "ABICDEFGHJKL")
        # Middle sources: the lifted card is removed before geometry is measured.
        self.assertEqual(drop(grid, "D", 6, 1, 0), "ADBCEFGHIJKL")
        self.assertEqual(drop(grid, "D", 6, 4, 0), "ABCEDFGHIJKL")
        self.assertEqual(drop(grid, "D", 6, 3, 0), "ABCDEFGHIJKL")
        self.assertEqual(drop(grid, "J", 6, 0, 1), "ABCDEFJGHIKL")
        self.assertEqual(drop(grid, "J", 6, 2, 0), "ABJCDEFGHIKL")
        self.assertEqual(drop(grid, "C", 6, 4, 1), "ABDEFGHIJKCL")

        for columns, track in ((6, 98), (5, 110), (4, 120), (3, 90), (6, 140), (4, 70)):
            count = columns * 2
            names = "".join(chr(65 + index) for index in range(count))
            moving = names[columns - 1]
            placed = drop(names, moving, columns, 1, 0, track=track)
            expected = names[:1] + moving + names[1:columns - 1] + names[columns:]
            self.assertEqual(placed, expected)

        root = frappe.get_app_path("smartprocee_erpnext_homepage")
        editor = open(f"{root}/public/js/home_manager_editor.js", encoding="utf-8").read()
        self.assertIn("sp_home_slot_index", editor)
        self.assertIn("commit_insertion", editor)
        self.assertNotIn("onMove:", editor)
        self.assertNotIn("ghostClass", editor)
        self.assertIn("document.body.appendChild", editor)
        move = editor.index("on_card_pointer_move")
        up = editor.index("on_card_pointer_up")
        self.assertNotIn("this.render()", editor[move:up])
        lift = editor.index("lift_card(session) {")
        self.assertIn('style.position = "fixed"', editor[lift:lift + 1200])
        self.assertIn("slot.style.width", editor[lift:lift + 1200])

    def test_live_drag_sequence_from_middle_source(self):
        """Each pointer step hit-tests the layout as drawn (slot included), so neighbours move
        when the pointer crosses their centre and release equals the last visible slot."""
        simulate = """(input) => input.map((scenario) => {
            const cols = scenario.columns;
            let visible = scenario.order.split("").map((name) => name === scenario.moving ? "_" : name);
            const trace = [];
            for (const [over, side] of scenario.steps) {
                const rects = visible.map((_, i) => ({left: 1000 - (i % cols + 1) * 100, top: Math.floor(i / cols) * 80, width: 100, height: 80}));
                const at = visible.indexOf(over);
                const center = 1000 - (at % cols) * 100 - 50;
                const pointer = {x: side === "before" ? center + 20 : center - 20, y: Math.floor(at / cols) * 80 + 40};
                const index = api.sp_home_slot_index(rects, visible.indexOf("_"), pointer, true);
                visible = visible.filter((name) => name !== "_");
                visible.splice(index, 0, "_");
                trace.push(visible.join(""));
            }
            return {trace, final: visible.join("").replace("_", scenario.moving)};
        })"""
        scenarios = [
            ("ABCDE", "C", 5, [("D", "after"), ("_", "after"), ("_", "before"), ("E", "after"), ("B", "before"), ("A", "before")],
                ["ABD_E", "ABD_E", "ABD_E", "ABDE_", "A_BDE", "_ABDE"], "CABDE"),
            ("ABCDE", "A", 5, [("C", "after"), ("C", "before")], ["BC_DE", "B_CDE"], "BACDE"),
            ("ABCDE", "E", 5, [("B", "before"), ("C", "after")], ["A_BCD", "ABC_D"], "ABCED"),
            ("ABCDEFGHIJKL", "D", 6, [("G", "before"), ("I", "after"), ("B", "before"), ("L", "after"), ("F", "after")],
                ["ABCEF_GHIJKL", "ABCEFGHI_JKL", "A_BCEFGHIJKL", "ABCEFGHIJKL_", "ABCEF_GHIJKL"], "ABCEFDGHIJKL"),
            ("ABCDEFGHIJKL", "J", 6, [("C", "before"), ("E", "after")], ["AB_CDEFGHIKL", "ABCDE_FGHIKL"], "ABCDEJFGHIKL"),
        ]
        results = _run_home_icon_js(simulate, [
            {"order": order, "moving": moving, "columns": columns, "steps": steps}
            for order, moving, columns, steps, _trace, _final in scenarios
        ])
        for (order, moving, _columns, _steps, trace, final), result in zip(scenarios, results):
            self.assertEqual(result["trace"], trace, f"{moving} from {order}")
            self.assertEqual(result["final"], final, f"{moving} from {order}")
            self.assertEqual(result["final"], result["trace"][-1].replace("_", moving))

        # The former hit test measured the row with the slot removed; for a middle source that
        # shifts every later card one track back, so the pointer over D resolved to "after E".
        packed = _js_insertion_index(_wrapped_rects(4, 5), {"x": 1000 - 3 * 100 - 70, "y": 40})
        self.assertEqual(packed, 4)

        root = frappe.get_app_path("smartprocee_erpnext_homepage")
        editor = open(f"{root}/public/js/home_manager_editor.js", encoding="utf-8").read()
        place = editor[editor.index("place_insertion(session, x, y) {"):editor.index("mixed_under_pointer(x, y, session) {")]
        self.assertNotIn("slot.hidden", editor)
        self.assertIn("el === session.slot ||", place)
        self.assertIn("visible.indexOf(session.slot)", place)
        self.assertLess(place.index("getBoundingClientRect"), place.index("sp_home_slot_index"))
        self.assertIn('on("dragstart", ".sp-home-card", (event) => event.preventDefault())', editor)
        self.assertIn('addEventListener("pointercancel", this._drag_cancel)', editor)
        cancel = editor[editor.index("on_card_pointer_cancel() {"):editor.index("on_card_pointer_move(event) {")]
        self.assertNotIn("commit_insertion", cancel)
        self.assertNotIn("move_into_folder", cancel)
        self.assertIn("this.dragging = false", cancel)
        css = open(f"{root}/public/css/home_manager_desk.css", encoding="utf-8").read()
        self.assertIn("-webkit-user-drag: none", css)
        self.assertIn("user-select: none", css)

    def test_desktop_icon_links_follow_native_route(self):
        fields = ["name", "label", "icon_type", "link_type", "link", "link_to", "parent_icon"]
        system = frappe.db.get_value("Desktop Icon", "System", fields, as_dict=True)
        self.assertIsNotNone(system)
        self.assertEqual(system.link_type, "Workspace Sidebar")
        self.assertFalse(frappe.db.exists("Page", "system"))
        native_app = frappe.db.get_value("Desktop Icon", "Users", fields, as_dict=True) or frappe.db.get_value(
            "Desktop Icon", {"link_type": "Workspace Sidebar", "standard": 1, "name": ["!=", "System"]}, fields, as_dict=True
        )
        page_icon = frappe.db.get_value(
            "Desktop Icon", {"link_type": "External", "link": ["like", "/app/%"]}, fields, as_dict=True
        ) or {"name": "sp-page", "label": "sp-page", "link_type": "External", "link": "/app/home-personalize"}
        external = {"name": "sp-external", "label": "sp-external", "link_type": "External", "link": "https://example.com/erp"}
        cases = [
            {"key": "system_native", "item": system, "native": system, "resolved": True},
            {"key": "system_unresolved", "item": system, "native": system, "resolved": False},
            {"key": "native_app", "item": native_app, "native": native_app, "resolved": True},
            {"key": "page", "item": page_icon, "native": None, "resolved": False},
            {"key": "external", "item": external, "native": None, "resolved": False},
            {"key": "custom_link", "item": dict(system, custom_link="/desk/build"), "native": system, "resolved": True},
        ]
        result = _run_home_icon_js(
            """(input) => Object.fromEntries(input.map((c) => {
                const route = (icon) => c.resolved && icon.link_type === "Workspace Sidebar" ? `native:${icon.name}` : undefined;
                return [c.key, api.sp_home_icon_href(c.item, c.native, route)];
            }))""",
            json.loads(frappe.as_json(cases)),
        )
        self.assertEqual(result["system_native"], "native:System")
        self.assertEqual(result["system_unresolved"], "")
        self.assertNotIn("/system", json.dumps(result))
        self.assertEqual(result["native_app"], f"native:{native_app.name}")
        self.assertEqual(result["page"], page_icon["link"])
        self.assertEqual(result["external"], "https://example.com/erp")
        self.assertEqual(result["custom_link"], "/desk/build")

        root = frappe.get_app_path("smartprocee_erpnext_homepage")
        desk = open(f"{root}/public/js/home_manager_desk.js", encoding="utf-8").read()
        editor = open(f"{root}/public/js/home_manager_editor.js", encoding="utf-8").read()
        for source in (desk, editor):
            self.assertNotIn("/app/${frappe.router.slug(", source)
        self.assertIn("frappe.utils?.get_route_for_icon", desk)
        self.assertIn("frappe.boot?.desktop_icons", desk)
        runtime = desk[desk.index("const make_runtime_icon"):desk.index("const apply_home_layout")]
        self.assertIn("icon_href(item)", runtime)
        folder = desk[desk.index("const make_folder_button"):desk.index("const open_folder")]
        self.assertIn('button.type = "button"', folder)
        self.assertIn("open_folder(folder, layout)", folder)
        self.assertNotIn("href", folder)
        dialog = desk[desk.index("const open_folder"):desk.index("const make_runtime_icon")]
        self.assertIn("icon_href(item)", dialog)

    def test_include_urls_change_with_file_content(self):
        import hashlib

        from smartprocee_erpnext_homepage import hooks

        public = os.path.join(frappe.get_app_path("smartprocee_erpnext_homepage"), "public")
        urls = hooks.app_include_js + hooks.app_include_css
        self.assertEqual(len(urls), 4)
        for url in urls:
            path, version = url.split("/assets/smartprocee_erpnext_homepage/", 1)[1].split("?v=")
            with open(os.path.join(public, path), "rb") as handle:
                self.assertEqual(version, hashlib.md5(handle.read(), usedforsecurity=False).hexdigest()[:12])
            self.assertEqual(hooks._asset(path), url)
        self.assertTrue(hooks._asset("js/sp-home-not-shipped.js").endswith("?v=missing"))

    def test_deleted_desktop_icon_row_does_not_block_save(self):
        missing = "sp-home-missing-icon-test"
        self.assertFalse(frappe.db.exists("Desktop Icon", missing))
        settings = frappe.get_single("SP Home Settings")
        existing = [row.desktop_icon for row in settings.styles if frappe.db.exists("Desktop Icon", row.desktop_icon)]
        settings.append("styles", {"desktop_icon": missing, "category": "عمومی", "shape": "rounded", "size": "medium"})
        settings.append("owned_icons", {"desktop_icon": missing})
        api._drop_missing_icon_rows(settings)
        self.assertEqual([row.desktop_icon for row in settings.styles], existing)
        self.assertEqual([row.idx for row in settings.styles], list(range(1, len(existing) + 1)))
        self.assertNotIn(missing, [row.desktop_icon for row in settings.get("owned_icons") or []])
        root = frappe.get_app_path("smartprocee_erpnext_homepage")
        source = open(f"{root}/home_manager/api.py", encoding="utf-8").read()
        for function in ("def _record_owned_icon", "def _forget_removed_categories", "def _retarget_preferences"):
            body = source[source.index(function):]
            body = body[:body.index("\ndef ", 1)]
            self.assertLess(body.index("_drop_missing_icon_rows"), body.index(".save(ignore_permissions=True)"))

    def test_stale_preference_row_is_dropped_on_save(self):
        missing = "sp-home-renamed-icon-test"
        self.assertFalse(frappe.db.exists("Desktop Icon", missing))
        user = self._make_user("sp-home-stale@example.com")
        frappe.set_user(user)
        payload = copy.deepcopy(api.get_my_layout())
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(payload)
        frappe.set_user("Administrator")

        def rows():
            doc = frappe.get_doc("SP Home Preference", user)
            return [
                (row.desktop_icon, row.category, row.folder, row.shape, row.size, row.hidden, row.sequence, row.custom_label)
                for row in doc.items
            ]

        def inject_stale_row():
            doc = frappe.get_doc("SP Home Preference", user)
            doc.append("items", {"desktop_icon": missing, "category": "عمومی", "shape": "rounded", "size": "medium"})
            doc.flags.ignore_links = True
            doc.save(ignore_permissions=True)
            self.assertIn(missing, [row[0] for row in rows()])

        valid = rows()
        self.assertTrue(valid)
        inject_stale_row()
        doc = frappe.get_doc("SP Home Preference", user)
        api._drop_missing_icon_rows(doc)
        doc.save(ignore_permissions=True)
        self.assertEqual(rows(), valid)

        inject_stale_row()
        frappe.set_user(user)
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(payload)
        frappe.set_user("Administrator")
        self.assertEqual(rows(), valid)

    def test_home_links_follow_native_tab_and_visibility(self):
        origin = "http://erp.local:8080"
        hrefs = {
            "/desk/system-health-report/System Health Report": "",
            "/desk/users": "",
            "/desk/doctype": "",
            "/app/home": "",
            "/desk/persian-translation-manager": "",
            "http://erp.local:8080/desk/build": "",
            "https://example.com/erp": "_blank",
            "http://other.local:8080/desk/build": "_blank",
            "": "",
        }
        items = [
            {"name": "System"},
            {"name": "My Workspaces"},
            {"name": "sp-folder", "icon_type": "Folder"},
            {"name": "sp-native-app"},
            {"name": "sp-custom", "custom_link": "https://example.com/erp"},
        ]
        result = _run_home_icon_js(
            """(input) => ({
                targets: Object.fromEntries(Object.keys(input.hrefs).map((href) => [href, api.sp_home_link_target(href, input.origin)])),
                visible: api.sp_home_effective_items(
                    input.items,
                    (item) => item.custom_link || input.routes[item.name] || "",
                    (item) => input.drawn.includes(item.name),
                ).map((item) => item.name),
            })""",
            {
                "origin": origin,
                "hrefs": hrefs,
                "items": items,
                "routes": {"System": "/desk/system-health-report/System Health Report"},
                "drawn": ["sp-native-app"],
            },
        )
        self.assertEqual(result["targets"], hrefs)
        self.assertEqual(result["visible"], ["System", "sp-folder", "sp-native-app", "sp-custom"])

        root = frappe.get_app_path("smartprocee_erpnext_homepage")
        desk = open(f"{root}/public/js/home_manager_desk.js", encoding="utf-8").read()
        self.assertNotIn("_blank", desk)
        paint = desk[desk.index("const paint_icon"):desk.index("const make_folder_button")]
        self.assertIn("window.sp_home_link_target(", paint)
        self.assertIn('"noopener noreferrer"', paint)
        restore = desk[desk.index("const restore"):desk.index("const set_target")]
        self.assertIn("set_target(el, original.target, original.rel)", restore)
        runtime = desk[desk.index("const make_runtime_icon"):desk.index("const apply_home_layout")]
        self.assertNotIn('"#"', runtime)
        self.assertNotIn("preventDefault", runtime)
        apply = desk[desk.index("const apply_home_layout"):desk.index("const schedule_apply")]
        self.assertIn("window.sp_home_effective_items(layout.items, icon_href, drawn)", apply)
        self.assertIn("view.items.forEach", apply)
        self.assertIn("make_folder_button(folder, view)", apply)

    def test_create_actions_and_single_folder_preview(self):
        root = frappe.get_app_path("smartprocee_erpnext_homepage")
        editor = open(f"{root}/public/js/home_manager_editor.js", encoding="utf-8").read()
        css = open(f"{root}/public/css/home_manager_desk.css", encoding="utf-8").read()
        template = editor[editor.index("render() {"):editor.index("category_names() {")]
        self.assertLess(template.index('<div class="sp-home-toolbar">'), template.index("this.create_actions_html()"))
        self.assertLess(template.index("this.create_actions_html()"), template.index('<div class="sp-home-board">'))
        actions = editor[editor.index("create_actions_html() {"):editor.index("category_names() {")]
        category = actions.index('"list-plus", __("دسته جدید")')
        guard = actions.index("if (this.can_publish)")
        self.assertLess(category, guard)
        self.assertLess(guard, actions.index('"square-plus", __("آیکون جدید")'))
        self.assertLess(guard, actions.index('"folder-plus", __("پوشه جدید")'))
        self.assertIn("frappe.utils.icon(icon", actions)
        self.assertIn(".sp-home-create-actions", css)
        self.assertNotIn("sp-folder-tools", editor)
        self.assertNotIn("sp-folder-tools", css)
        folder = editor[editor.index("render_folder(folder) {"):editor.index("folder_dialog_actions(folder, dialog) {")]
        self.assertEqual(folder.count("sp-home-card-icon"), 1)
        self.assertNotIn("<button", folder)
        self.assertIn("if (this.can_publish) dialog.$body.append(this.folder_dialog_actions(folder, dialog))", editor)
        face = _run_home_icon_js(
            """(input) => ({
                empty: api.sp_home_folder_face({folder_name: "F"}, [], {}),
                filled: api.sp_home_folder_face({folder_name: "F"}, input, {}),
            })""",
            [{"name": "a", "label": "A", "folder": "F", "sequence": 1}, {"name": "b", "label": "B", "folder": "F", "sequence": 2}],
        )
        self.assertEqual(face["empty"]["mode"], "empty")
        self.assertEqual(face["empty"]["html"].count("sp-folder-preview-cell"), 0)
        self.assertEqual(face["empty"]["html"].count("sp-folder-face"), 1)
        self.assertIn("is-empty", face["empty"]["html"])
        self.assertEqual(face["filled"]["html"].count("sp-folder-face"), 1)
        self.assertEqual(face["filled"]["mode"], "preview")
        self.assertEqual(face["filled"]["html"].count("sp-folder-preview-cell"), 2)

    def test_personal_rename_does_not_restore_empty_global_category(self):
        user = self._make_user("sp-home-rename@example.com")
        frappe.set_user(user)
        payload = copy.deepcopy(api.get_my_layout())
        old = next(
            name for name in payload["categories"]
            if any(item["category"] == name and not item.get("hidden") for item in payload["items"])
        )
        new = f"{old} تازه"
        moved = [item["name"] for item in payload["items"] if item["category"] == old]
        self.assertTrue(moved)
        for item in payload["items"]:
            if item["category"] == old:
                item["category"] = new
        for folder in payload.get("folders") or []:
            if folder.get("category") == old:
                folder["category"] = new
        payload["categories"] = [new if name == old else name for name in payload["categories"]]
        with patch.object(frappe, "publish_realtime"):
            saved = api.save_my_layout(payload)
        self.assertIn(new, saved["categories"])
        self.assertNotIn(old, saved["categories"])
        self.assertFalse(any(item["category"] == old for item in saved["items"]))
        self.assertTrue(all(item["category"] == new for item in saved["items"] if item["name"] in set(moved)))
        frappe.set_user("Administrator")
        self.assertIn(old, api.get_layout()["categories"])
        self.assertNotIn(new, api.get_layout()["categories"])
        frappe.set_user(user)
        again = api.get_my_layout()
        self.assertIn(new, again["categories"])
        self.assertNotIn(old, again["categories"])
        self.assertFalse(any(item["category"] == old for item in again["items"]))
        self.assertEqual(
            sorted(item["name"] for item in again["items"] if item["name"] in set(moved)),
            sorted(moved),
        )
        preference = frappe.get_doc("SP Home Preference", user)
        self.assertFalse(any((row.category_name or "") == old for row in preference.categories))
        self.assertTrue(any((row.category_name or "") == new for row in preference.categories))

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

    def test_owned_custom_icon_delete_does_not_touch_foreign_icons(self):
        selling = "Selling"
        self.assertTrue(frappe.db.exists("Desktop Icon", selling))
        self.assertEqual(frappe.db.get_value("Desktop Icon", selling, "app"), "erpnext")
        label = "آیکون مالکیت آزمون"
        with patch.object(frappe, "publish_realtime"):
            created = api.create_desktop_icon(label, "/app/owned-icon-test")
        owned = next(row for row in created["items"] if row["label"] == label)
        self.assertEqual(owned["owned"], 1)
        self.assertEqual(next(row["owned"] for row in created["items"] if row["name"] == selling), 0)
        self.assertIn(owned["name"], api._owned_icon_names())

        payload = api.get_layout()
        target = next(row for row in payload["items"] if row["name"] == owned["name"])
        folder_name = "پوشه مالکیت آزمون"
        payload["folders"] = list(payload.get("folders") or []) + [{
            "folder_name": folder_name,
            "category": target["category"],
            "sequence": 4,
            "icon_name": "folder",
            "custom_icon_image": "",
        }]
        target["folder"] = folder_name
        target["hidden"] = 0
        old_category = payload["categories"][0]
        renamed = old_category + " بدون حذف"
        for item in payload["items"]:
            if item["category"] == old_category:
                item["category"] = renamed
        for folder in payload["folders"]:
            if folder["category"] == old_category:
                folder["category"] = renamed
        payload["categories"][0] = renamed
        payload["category_renames"] = [{"from": old_category, "to": renamed}]
        with patch.object(frappe, "publish_realtime"):
            renamed_layout = api.save_layout(payload)
        self.assertTrue(frappe.db.exists("Desktop Icon", owned["name"]))
        self.assertTrue(frappe.db.exists("Desktop Icon", selling))
        self.assertIn(owned["name"], api._owned_icon_names())
        self.assertIn(renamed, renamed_layout["categories"])

        hidden_payload = api.get_layout()
        hidden_row = next(row for row in hidden_payload["items"] if row["name"] == owned["name"])
        hidden_row["hidden"] = 1
        with patch.object(frappe, "publish_realtime"):
            api.save_layout(hidden_payload)
        self.assertTrue(frappe.db.exists("Desktop Icon", owned["name"]))
        self.assertEqual(
            frappe.db.get_value("SP Home Style", {"desktop_icon": owned["name"]}, "hidden"),
            1,
        )

        user = self._make_user("sp-home-owned@example.com")
        frappe.set_user(user)
        personal = api.get_my_layout()
        visible = next(row for row in personal["items"] if row["name"] != owned["name"])
        visible["sequence"] = 11
        with patch.object(frappe, "publish_realtime"):
            api.save_my_layout(personal)
        frappe.set_user("Administrator")

        self._set_desktop_icon_roles(selling, ["System Manager"])
        frappe.set_user(user)
        blocked = api.get_current_layout()
        self.assertNotIn(selling, [row["name"] for row in blocked["items"]])
        self.assertTrue(frappe.db.exists("Desktop Icon", selling))
        self.assertTrue(frappe.db.exists("Desktop Icon", owned["name"]))
        frappe.set_user("Administrator")
        self._set_desktop_icon_roles(selling, [])
        frappe.set_user(user)
        restored = api.get_current_layout()
        self.assertIn(selling, [row["name"] for row in restored["items"]])
        frappe.set_user("Administrator")

        settings = frappe.get_single("SP Home Settings")
        settings.append("owned_icons", {"desktop_icon": selling})
        settings.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            api.delete_owned_desktop_icon(selling)
        self.assertTrue(frappe.db.exists("Desktop Icon", selling))

        with patch.object(frappe, "publish_realtime"):
            deleted = api.delete_owned_desktop_icon(owned["name"])
        self.assertFalse(frappe.db.exists("Desktop Icon", owned["name"]))
        self.assertFalse(any(row["name"] == owned["name"] for row in deleted["items"]))
        self.assertFalse(frappe.db.exists("SP Home Style", {"desktop_icon": owned["name"]}))
        self.assertFalse(frappe.get_all("SP Home Preference Item", filters={"desktop_icon": owned["name"]}))
        self.assertNotIn(owned["name"], api._owned_icon_names())
        self.assertTrue(any(row["folder_name"] == folder_name for row in deleted["folders"]))
        self.assertTrue(frappe.db.exists("Desktop Icon", selling))
        self.assertEqual(self._preference_value(user, visible["name"], "sequence"), 11)
        self.assertEqual(
            [row.name for row in self.before],
            [row.name for row in frappe.get_all("Desktop Icon", fields=["name"], order_by="name")],
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


def _run_home_icon_js(script, payload):
    """Run public/js/home_icon.js in node so tests exercise the browser code itself."""
    node = shutil.which("node") or os.path.expanduser("~/.nvm/current/bin/node")
    source = os.path.join(frappe.get_app_path("smartprocee_erpnext_homepage"), "public", "js", "home_icon.js")
    code = (
        f"const api = require({json.dumps(source)});"
        "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        f"process.stdout.write(JSON.stringify(({script})(input)));"
    )
    result = subprocess.run([node, "-e", code], input=json.dumps(payload), capture_output=True, text=True, timeout=60, check=True)
    return json.loads(result.stdout)


def _js_insertion_index(cards, pointer, rtl=True):
    return _run_home_icon_js(
        "(input) => api.sp_home_insertion_index(input.cards, input.pointer, input.rtl)",
        {"cards": cards, "pointer": pointer, "rtl": rtl},
    )


def _wrapped_rects(count, columns, track=100, row_height=80, origin_right=1000):
    rects = []
    for index in range(count):
        row, col = divmod(index, columns)
        rects.append({"left": origin_right - (col + 1) * track, "top": row * row_height, "width": track, "height": row_height})
    return rects


def run_checks():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestHomeLayout))
    if not result.wasSuccessful():
        raise AssertionError("Home Manager checks failed")
    return {"tests": result.testsRun, "passed": True}
