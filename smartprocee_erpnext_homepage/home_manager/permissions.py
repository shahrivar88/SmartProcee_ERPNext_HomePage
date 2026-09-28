import frappe


def has_preference_permission(doc, ptype="read", user=None, debug=False):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	owner = getattr(doc, "user", None) if doc else None
	if ptype == "create":
		return not owner or owner == user
	return owner == user


def preference_query(user, doctype=None):
	if user == "Administrator":
		return ""
	return f"`tabSP Home Preference`.user = {frappe.db.escape(user)}"
