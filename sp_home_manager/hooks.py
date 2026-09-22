app_name = "sp_home_manager"
app_title = "مدیریت صفحه اصلی"
app_publisher = "Smart Process"
app_description = "مدیریت فارسی و مستقل صفحه اصلی Frappe/ERPNext"
app_email = "info@smartprocess.local"
app_license = "mit"
required_apps = ["frappe"]

app_include_js = ["/assets/sp_home_manager/js/home_manager_desk.js?v=1"]
app_include_css = ["/assets/sp_home_manager/css/home_manager_desk.css?v=1"]
boot_session = "sp_home_manager.home_manager.boot.boot_session"
after_install = "sp_home_manager.home_manager.install.after_install"
after_migrate = ["sp_home_manager.home_manager.install.after_migrate"]
before_uninstall = "sp_home_manager.home_manager.install.before_uninstall"

