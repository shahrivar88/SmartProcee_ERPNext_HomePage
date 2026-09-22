# SmartProcee_ERPNext_HomePage

این اپ، چیدمان و ظاهر صفحه اصلی Frappe/ERPNext را بدون تغییر سورس هسته مدیریت می‌کند. همه متن‌های قابل مشاهده فارسی هستند.

## نصب

```bash
bench get-app https://github.com/shahrivar88/SmartProcee_ERPNext_HomePage.git
bench --site SITE install-app smartprocee_erpnext_homepage
bench build --app smartprocee_erpnext_homepage
bench --site SITE migrate
```

## حذف و بازگردانی

```bash
bench --site SITE uninstall-app smartprocee_erpnext_homepage
bench build
```

قبل از نخستین نصب، وضعیت آیکون مدیریتی و مالکیت ماژول ذخیره می‌شود. هنگام حذف، همان وضعیت بازگردانده و کش‌های صفحه اصلی پاک می‌شوند.
