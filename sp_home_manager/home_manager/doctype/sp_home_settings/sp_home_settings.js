frappe.ui.form.on("SP Home Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Open Visual Editor"), () => {
			frappe.set_route("home-manager");
		});
	},
});
