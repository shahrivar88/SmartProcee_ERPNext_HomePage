# مدیریت مستقل صفحه اصلی ERPNext

این اپ، چیدمان و ظاهر صفحه اصلی Frappe/ERPNext را بدون تغییر سورس هسته مدیریت می‌کند. همه متن‌های قابل مشاهده فارسی هستند.

## نصب

```bash
bench get-app https://github.com/shahrivar88/sp-home-manager.git
bench --site SITE install-app sp_home_manager
bench build --app sp_home_manager
bench --site SITE migrate
```

## حذف و بازگردانی

```bash
bench --site SITE uninstall-app sp_home_manager
bench build
```

قبل از نخستین نصب، وضعیت آیکون مدیریتی و مالکیت ماژول ذخیره می‌شود. هنگام حذف، همان وضعیت بازگردانده و کش‌های صفحه اصلی پاک می‌شوند.
