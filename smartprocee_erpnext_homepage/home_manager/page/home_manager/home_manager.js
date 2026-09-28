frappe.pages["home-manager"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("مدیریت صفحه اصلی"),
		single_column: true,
	});
	wrapper.home_manager = new SPHomeManager(page, { mode: "global" });
};

frappe.pages["home-manager"].on_page_show = function (wrapper) {
	if (wrapper.home_manager) {
		wrapper.home_manager.load();
	}
};
