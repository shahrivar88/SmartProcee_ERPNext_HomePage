app_name = "smartprocee_erpnext_homepage"
app_title = "SmartProcee_ERPNext_HomePage"
app_publisher = "Smart Process"
app_description = "مدیریت فارسی و مستقل صفحه اصلی Frappe/ERPNext"
app_email = "info@smartprocess.local"
app_license = "mit"
required_apps = ["frappe"]

app_include_js = ["/assets/smartprocee_erpnext_homepage/js/home_manager_desk.js?v=3"]
app_include_css = ["/assets/smartprocee_erpnext_homepage/css/home_manager_desk.css?v=3"]
boot_session = "smartprocee_erpnext_homepage.home_manager.boot.boot_session"
after_install = "smartprocee_erpnext_homepage.home_manager.install.after_install"
after_migrate = ["smartprocee_erpnext_homepage.home_manager.install.after_migrate"]
before_uninstall = "smartprocee_erpnext_homepage.home_manager.install.before_uninstall"
