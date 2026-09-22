frappe.pages["home-manager"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("مدیریت صفحه اصلی"),
		single_column: true,
	});
	wrapper.home_manager = new SPHomeManager(page);
};

frappe.pages["home-manager"].on_page_show = function (wrapper) {
	if (wrapper.home_manager) {
		wrapper.home_manager.load();
	}
};

class SPHomeManager {
	constructor(page) {
		this.page = page;
		this.state = null;
		this.empty_categories = [];
		this.sortables = [];
		this.setup_actions();
		this.page.main.html(`<div class="sp-home-editor"></div>`);
		this.$root = this.page.main.find(".sp-home-editor");
	}

	setup_actions() {
		this.page.set_primary_action(__("ذخیره و اعمال"), () => this.save());
		this.page.set_secondary_action(__("رفتن به صفحه اصلی"), () => {
			window.open("/desk", "_blank", "noopener");
		});
		this.page.add_inner_button(__("آیکون جدید"), () => this.prompt_new_icon());
		this.page.add_inner_button(__("دسته جدید"), () => this.prompt_new_category());
	}

	load() {
		frappe.call({
			method: "smartprocee_erpnext_homepage.home_manager.api.get_layout",
			freeze: true,
			freeze_message: __("در حال بارگذاری صفحه اصلی..."),
			callback: (r) => {
				this.state = r.message;
				this.render();
			},
		});
	}

	render() {
		if (!this.state) return;
		this.sortables.forEach(sortable => sortable.destroy());
		this.sortables = [];
		const categories = this.get_categories();
		this.$root.html(`
			<div class="sp-home-toolbar">
				<label class="sp-toggle">
					<input type="checkbox" data-field="enable_custom_styles" ${this.state.enabled ? "checked" : ""}>
					<span>اعمال ظاهر سفارشی روی صفحه اصلی</span>
				</label>
				<label class="sp-toggle">
					<input type="checkbox" data-field="apply_to_all_users" ${this.state.apply_to_all_users ? "checked" : ""}>
					<span>اعمال برای همه کاربران</span>
				</label>
				<label>
					شکل پیش‌فرض
					<select data-field="default_shape">
						<option value="rounded">گوشه‌گرد</option>
						<option value="circle">دایره</option>
						<option value="square">مربع</option>
					</select>
				</label>
				<label>
					اندازه پیش‌فرض
					<select data-field="default_size">
						<option value="small">کوچک</option>
						<option value="medium">متوسط</option>
						<option value="large">بزرگ</option>
						<option value="xlarge">خیلی بزرگ</option>
					</select>
				</label>
				<label>
					سبک آیکون
					<select data-field="icon_style">
						<option value="Solid">پررنگ</option>
						<option value="Subtle">ملایم</option>
					</select>
				</label>
				<label>
					تعداد ستون
					<input type="number" min="2" max="10" data-field="columns">
				</label>
				<label>
					فاصله افقی
					<input type="number" min="-50" max="100" step="1" data-field="gap_x">
				</label>
				<label>
					فاصله عمودی
					<input type="number" min="-50" max="100" step="1" data-field="gap_y">
				</label>
			</div>
			<div class="sp-home-hint">این پیش‌نمایش اندازه، شکل و فاصله‌ها را نشان می‌دهد. تنظیم اختصاصی هر آیکون حفظ می‌شود. دستهٔ خالی پس از ذخیره باقی نمی‌ماند؛ ابتدا آیکونی به آن منتقل کنید.</div>
			<div class="sp-home-board"></div>
		`);
		this.$root.find("[data-field=default_shape]").val(this.state.default_shape);
		this.$root.find("[data-field=default_size]").val(this.state.default_size);
		this.$root.find("[data-field=icon_style]").val(this.state.icon_style);
		this.$root.find("[data-field=gap_x]").val(this.state.gap_x ?? 8);
		this.$root.find("[data-field=gap_y]").val(this.state.gap_y ?? 8);
		this.$root.find("[data-field=columns]").val(this.state.columns ?? 5);

		this.$root.find("[data-field]").on("input change", (e) => {
			const $el = $(e.currentTarget);
			const field = $el.data("field");
			if ($el.is(":checkbox")) {
				this.state[field === "enable_custom_styles" ? "enabled" : field] = $el.is(":checked") ? 1 : 0;
				return;
			}
			if (field === "gap_x" || field === "gap_y") {
				let gap = parseInt($el.val(), 10);
				if (Number.isNaN(gap)) gap = 8;
				gap = Math.min(100, Math.max(-50, gap));
				this.state[field] = gap;
				$el.val(gap);
				this.update_preview();
				return;
			}
			if (field === "columns") {
				let cols = parseInt($el.val(), 10);
				if (Number.isNaN(cols)) cols = 5;
				cols = Math.min(10, Math.max(2, cols));
				this.state.columns = cols;
				$el.val(cols);
				this.update_preview();
				return;
			}
			this.state[field] = $el.val();
			this.render();
		});

		const $board = this.$root.find(".sp-home-board");
		categories.forEach((category) => {
			$board.append(this.render_category(category));
		});
		this.bind_sortable();
		this.update_preview();
	}

	update_preview() {
		const root = this.$root[0];
		root.style.setProperty("--sp-cols", this.state.columns ?? 5);
		root.style.setProperty("--sp-gap-x", `${this.state.gap_x ?? 8}px`);
		root.style.setProperty("--sp-gap-y", `${this.state.gap_y ?? 8}px`);
		this.$root.find(".sp-home-cards").each((_, grid) => {
			[...grid.querySelectorAll(":scope > .sp-home-card")].forEach((card, index) => {
				card.style.setProperty("--sp-col", index % (this.state.columns ?? 5));
				card.style.setProperty("--sp-row", Math.floor(index / (this.state.columns ?? 5)));
			});
		});
	}

	render_category(category) {
		const items = this.state.items.filter((item) => !item.hidden && item.icon_type !== "Folder" && (item.category || "عمومی") === category);
		const $section = $(`
			<section class="sp-home-category" data-category="${frappe.utils.escape_html(category)}">
				<header>
					<input class="sp-category-title" value="${frappe.utils.escape_html(category)}">
					<button class="btn btn-xs btn-default sp-rename-cat" type="button">تغییر نام دسته</button>
				</header>
				<div class="sp-home-cards"></div>
			</section>
		`);
		const $cards = $section.find(".sp-home-cards");
		items.forEach((item) => $cards.append(this.render_card(item)));
		$section.find(".sp-rename-cat").on("click", () => {
			const next = ($section.find(".sp-category-title").val() || "").trim();
			if (!next || next === category) return;
			this.state.items.forEach((item) => {
				if (item.category === category) item.category = next;
			});
			this.render();
		});
		return $section;
	}

	effective_shape(item) {
		return item.use_custom_style ? item.shape || this.state.default_shape : this.state.default_shape || item.shape || "rounded";
	}

	effective_size(item) {
		return item.use_custom_style ? item.size || this.state.default_size : this.state.default_size || item.size || "medium";
	}

	render_card(item) {
		const label = __(item.custom_label || item.label);
		const image = item.icon_type !== "Folder" && (frappe.utils.get_desktop_icon?.(item.label, (this.state.icon_style || "Solid").toLowerCase()) || item.icon_image || item.logo_url);
		const shape = this.effective_shape(item);
		const size = this.effective_size(item);
		const $card = $(`
			<article class="sp-home-card ${item.hidden ? "is-hidden" : ""}" data-name="${frappe.utils.escape_html(item.name)}" data-shape="${shape}" data-size="${size}">
				<button class="sp-home-delete" type="button" title="حذف آیکون" aria-label="حذف آیکون">×</button>
				<div class="sp-home-card-icon" style="${/^#[\da-f]{3}([\da-f]{3})?$/i.test(item.custom_color || "") ? `background:${item.custom_color}` : ""}">
					${image ? `<img src="${frappe.utils.escape_html(image)}" alt="${frappe.utils.escape_html(label)}">` : `<span>${frappe.utils.escape_html((label || "؟").slice(0, 1))}</span>`}
				</div>
				<div class="sp-home-card-title">${frappe.utils.escape_html(label)}</div>
				<div class="sp-home-card-meta">${item.hidden ? "مخفی" : __(shape)} · ${__(size)}${item.parent_icon ? ` · در پوشهٔ ${frappe.utils.escape_html(__(item.parent_icon))}` : ""}</div>
			</article>
		`);
		$card.on("click", () => this.edit_item(item));
		$card.find(".sp-home-delete").on("click", (event) => {
			event.preventDefault();
			event.stopPropagation();
			item.hidden = 1;
			this.empty_categories = this.empty_categories.filter(category => category !== (item.category || "عمومی"));
			this.render();
		});
		return $card;
	}

	bind_sortable() {
		if (typeof Sortable === "undefined") {
			return;
		}
		this.$root.find(".sp-home-cards").each((_, el) => {
			this.sortables.push(new Sortable(el, {
				group: "sp-home-icons",
				animation: 150,
				onEnd: () => this.sync_from_dom(),
			}));
		});
	}

	sync_from_dom() {
		const next = [];
		this.$root.find(".sp-home-category").each((_, section) => {
			const category = ($(section).find(".sp-category-title").val() || "عمومی").trim();
			$(section)
				.find(".sp-home-card")
				.each((index, card) => {
					const name = card.dataset.name;
					const item = this.state.items.find((row) => row.name === name);
					if (!item) return;
					item.category = category;
					item.sequence = next.length + 1;
					next.push(item);
				});
		});
		const leftover = this.state.items.filter((item) => !next.includes(item));
		this.state.items = next.concat(leftover);
	}

	edit_item(item) {
		const dialog = new frappe.ui.Dialog({
			title: __("ویرایش آیکون"),
			fields: [
				{ fieldname: "custom_label", fieldtype: "Data", label: __("نام نمایشی"), default: item.custom_label || item.label },
				{
					fieldname: "category",
					fieldtype: "Data",
					label: __("دسته"),
					default: item.category || "عمومی",
				},
				{
					fieldname: "shape",
					fieldtype: "Select",
					label: __("شکل"),
					options: [{value: "rounded", label: "گوشه‌گرد"}, {value: "circle", label: "دایره"}, {value: "square", label: "مربع"}],
					default: this.effective_shape(item),
				},
				{
					fieldname: "size",
					fieldtype: "Select",
					label: __("اندازه"),
					options: [{value: "small", label: "کوچک"}, {value: "medium", label: "متوسط"}, {value: "large", label: "بزرگ"}, {value: "xlarge", label: "خیلی بزرگ"}],
					default: this.effective_size(item),
				},
				{ fieldname: "use_custom_style", fieldtype: "Check", label: "شکل و اندازهٔ اختصاصی", default: item.use_custom_style },
				{ fieldname: "custom_color", fieldtype: "Color", label: __("رنگ"), default: item.custom_color },
				{ fieldname: "hidden", fieldtype: "Check", label: __("مخفی شود"), default: item.hidden },
			],
			primary_action_label: __("اعمال روی کارت"),
			primary_action: (values) => {
								Object.assign(item, values);
				item.hidden = values.hidden ? 1 : 0;
				item.use_custom_style = values.use_custom_style ? 1 : 0;
				dialog.hide();
				this.render();
			},
		});
		dialog.show();
		for (const name of ["shape", "size"]) {
			dialog.fields_dict[name].$input.on("change.sp_home", () => dialog.set_value("use_custom_style", 1));
		}
	}

	prompt_new_category() {
		frappe.prompt(
			{ fieldname: "category", fieldtype: "Data", label: __("نام دسته"), reqd: 1 },
			(values) => {
				const category = values.category.trim();
				if (!category) return;
				if (!this.get_categories().includes(category)) this.empty_categories.push(category);
				this.render();
			},
			__("دسته جدید"),
			__("ساخت")
		);
	}

	prompt_new_icon() {
		const dialog = new frappe.ui.Dialog({
			title: __("آیکون جدید"),
			fields: [
				{ fieldname: "label", fieldtype: "Data", label: __("نام"), reqd: 1 },
				{ fieldname: "link", fieldtype: "Data", label: __("لینک"), default: "/app" },
			],
			primary_action_label: __("بساز"),
			primary_action: (values) => {
				frappe.call({
					method: "smartprocee_erpnext_homepage.home_manager.api.create_desktop_icon",
					args: values,
					freeze: true,
					callback: (r) => {
						this.state = r.message;
						dialog.hide();
						this.render();
					},
				});
			},
		});
		dialog.show();
	}

	get_categories() {
		const seen = [...this.empty_categories];
		(this.state.items || []).filter(item => !item.hidden && item.icon_type !== "Folder").forEach((item) => {
			const category = item.category || "عمومی";
			if (!seen.includes(category)) seen.push(category);
		});
		if (!seen.length) seen.push("عمومی");
		return seen;
	}

	save() {
		// Read live controls as well: Save may precede a number input's blur/change.
		for (const field of ["columns", "gap_x", "gap_y"]) {
			const value = Number(this.$root.find(`[data-field=${field}]`).val());
			this.state[field] = Number.isFinite(value) ? Math.max(field === "columns" ? 2 : -50, Math.min(field === "columns" ? 10 : 100, Math.trunc(value))) : (field === "columns" ? 5 : 8);
		}
		this.sync_from_dom();
		this.empty_categories = [];
		const payload = {
			enable_custom_styles: this.state.enabled ? 1 : 0,
			apply_to_all_users: this.state.apply_to_all_users ? 1 : 0,
			default_shape: this.state.default_shape,
			default_size: this.state.default_size,
			icon_style: this.state.icon_style,
			gap_x: this.state.gap_x ?? 8,
			gap_y: this.state.gap_y ?? 8,
			columns: this.state.columns ?? 5,
			items: (this.state.items || []).filter((item) => !item.placeholder && item.name),
		};
		frappe.call({
			method: "smartprocee_erpnext_homepage.home_manager.api.save_layout",
			args: { payload: JSON.stringify(payload) },
			freeze: true,
			freeze_message: __("در حال اعمال روی صفحه اصلی..."),
			callback: (r) => {
				this.state = r.message;
				if (window.frappe && frappe.boot) {
					frappe.boot.sp_home = r.message;
				}
				try { localStorage.setItem("sp_home_updated", `${Date.now()}`); } catch (_) { /* Optional cross-tab signal. */ }
				this.render();
				frappe.show_alert({
					message: __("ذخیره شد و روی صفحه اصلی اعمال شد."),
					indicator: "green",
				});
				window.sp_home_apply_layout?.();
			},
		});
	}
}
