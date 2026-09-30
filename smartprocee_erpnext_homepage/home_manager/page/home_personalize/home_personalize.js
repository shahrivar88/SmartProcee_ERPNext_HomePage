frappe.pages["home-personalize"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("تنظیم صفحه اصلی"),
		single_column: true,
	});
	wrapper.home_manager = new SPHomeManager(page);
};

frappe.pages["home-personalize"].on_page_show = function (wrapper) {
	if (wrapper.home_manager) {
		wrapper.home_manager.load();
	}
};
