import frappe
from frappe.model.document import Document


class SPHomePreference(Document):
	def validate(self):
		user = frappe.session.user
		if user == "Guest":
			frappe.throw("برای ذخیره چیدمان باید وارد سامانه شوید.", frappe.PermissionError)
		if user != "Administrator":
			self.user = user
		if not self.user:
			self.user = user
		if self.user != user and user != "Administrator":
			frappe.throw("چیدمان کاربر دیگری قابل ویرایش نیست.", frappe.PermissionError)
