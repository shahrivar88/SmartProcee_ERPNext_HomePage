import hashlib
import os

app_name = "smartprocee_erpnext_homepage"
app_title = "SmartProcee_ERPNext_HomePage"
app_publisher = "Smart Process"
app_description = "مدیریت فارسی و مستقل صفحه اصلی Frappe/ERPNext"
app_email = "info@smartprocess.local"
app_license = "mit"
required_apps = ["frappe"]


def _asset(path):
	"""Browsers cache these URLs, so the query must change whenever the file content changes."""
	try:
		with open(os.path.join(os.path.dirname(__file__), "public", path), "rb") as handle:
			digest = hashlib.md5(handle.read(), usedforsecurity=False).hexdigest()[:12]
	except OSError:
		digest = "missing"
	return f"/assets/smartprocee_erpnext_homepage/{path}?v={digest}"


app_include_js = [
	_asset("js/home_icon.js"),
	_asset("js/home_manager_editor.js"),
	_asset("js/home_manager_desk.js"),
]
app_include_css = [_asset("css/home_manager_desk.css")]
boot_session = "smartprocee_erpnext_homepage.home_manager.boot.boot_session"
after_install = "smartprocee_erpnext_homepage.home_manager.install.after_install"
after_migrate = ["smartprocee_erpnext_homepage.home_manager.install.after_migrate"]
before_uninstall = "smartprocee_erpnext_homepage.home_manager.install.before_uninstall"
has_permission = {
	"SP Home Preference": [
		"smartprocee_erpnext_homepage.home_manager.permissions.has_preference_permission",
	],
}
permission_query_conditions = {
	"SP Home Preference": [
		"smartprocee_erpnext_homepage.home_manager.permissions.preference_query",
	],
}
