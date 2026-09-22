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
        for columns, gap_x, gap_y, size, shape in [(3, -50, 100, "small", "circle"), (5, 30, 0, "medium", "square"), (7, 8, 8, "large", "rounded"), (6, -25, -10, "xlarge", "square")]:
            payload = copy.deepcopy(self.layout)
            payload.update(columns=columns, gap_x=gap_x, gap_y=gap_y, default_size=size, default_shape=shape)
            with patch.object(frappe, "publish_realtime") as publish:
                result = api.save_layout(payload)
                publish.assert_any_call("sp_home_layout_updated", result, after_commit=True)
                self.assertEqual(sum(call.args[0] == "sp_home_layout_updated" for call in publish.call_args_list), 1)
            reloaded = api.get_layout()
            for field in ("columns", "gap_x", "gap_y", "default_size", "default_shape"):
                self.assertEqual(reloaded[field], payload[field])
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


def run_checks():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestHomeLayout))
    if not result.wasSuccessful():
        raise AssertionError("Home Manager checks failed")
    return {"tests": result.testsRun, "passed": True}
