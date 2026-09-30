const SP_HOME_GAP_MIN = window.SP_HOME_GAP_MIN;
const SP_HOME_GAP_MAX = window.SP_HOME_GAP_MAX;

class SPHomeManager {
	constructor(page) {
		this.page = page;
		this.state = null;
		this.can_publish = false;
		this.sortables = [];
		this.dragging = false;
		this.setup_actions();
		this.page.main.html(`<div class="sp-home-editor"></div>`);
		this.$root = this.page.main.find(".sp-home-editor");
		this.$root.on("pointerdown", ".sp-home-card", (event) => this.on_card_pointer_down(event));
		this.$root.on("click", ".sp-home-card", (event) => this.on_card_click(event));
		// A native image/text drag cancels the pointer stream, so the slot would stop following.
		this.$root.on("dragstart", ".sp-home-card", (event) => event.preventDefault());
	}

	setup_actions() {
		this.page.set_primary_action(__("ذخیره چیدمان من"), () => this.save());
	}

	ensure_menu() {
		if (this.menu_ready) return;
		this.menu_ready = true;
		this.page.add_menu_item(__("صفحه اصلی"), () => {})
			.attr("href", this.home_href())
			.removeAttr("onclick");
		if (this.can_publish) {
			this.page.add_menu_item(__("ذخیره به عنوان پیش‌فرض"), () => this.publish_global());
		}
		this.page.add_menu_item(__("بازنشانی چیدمان پیش‌فرض"), () => this.reset_personal());
	}

	home_href() {
		try {
			if (typeof frappe.router?.make_url === "function") {
				const url = frappe.router.make_url(["desktop"]);
				if (url) return url;
			}
		} catch (_) { /* The desk root remains a valid home link. */ }
		return "/desk";
	}

	load() {
		frappe.call({
			method: "smartprocee_erpnext_homepage.home_manager.api.get_my_layout",
			freeze: true,
			freeze_message: __("در حال بارگذاری صفحه اصلی..."),
			callback: (r) => {
				this.apply_state(r.message);
			},
		});
	}

	apply_state(message) {
		this.state = message;
		this.state.categories = this.state.categories || [];
		this.state.folders = this.state.folders || [];
		this.can_publish = !!this.state.can_publish_global;
		this.ensure_menu();
		this.remember_categories();
		this.render();
	}

	render() {
		if (!this.state) return;
		this.sortables.forEach((sortable) => sortable.destroy());
		this.sortables = [];
		const locked = this.can_publish ? "" : "disabled";
		this.$root.html(`
			<div class="sp-home-toolbar">
				<label class="sp-toggle">
					<input type="checkbox" data-field="enable_custom_styles" ${this.state.enabled ? "checked" : ""} ${locked}>
					<span>اعمال ظاهر سفارشی روی صفحه اصلی</span>
				</label>
				<label class="sp-toggle">
					<input type="checkbox" data-field="apply_to_all_users" ${this.state.apply_to_all_users ? "checked" : ""} ${locked}>
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
					حداکثر ستون
					<input type="number" min="2" max="10" data-field="columns">
				</label>
				<label>
					فاصله افقی
					<input type="number" min="${SP_HOME_GAP_MIN}" max="${SP_HOME_GAP_MAX}" step="1" data-field="gap_x">
				</label>
				<label>
					فاصله عمودی
					<input type="number" min="${SP_HOME_GAP_MIN}" max="${SP_HOME_GAP_MAX}" step="1" data-field="gap_y">
				</label>
			</div>
			${this.create_actions_html()}
			<div class="sp-home-board"></div>
		`);
		this.$root.find(".sp-home-create-actions [data-create]").on("click", (event) => {
			const kind = event.currentTarget.dataset.create;
			if (kind === "category") this.prompt_new_category();
			else if (kind === "icon") this.prompt_new_icon();
			else if (kind === "folder") this.prompt_new_folder();
		});
		this.$root.find("[data-field=default_shape]").val(this.state.default_shape);
		this.$root.find("[data-field=default_size]").val(this.state.default_size);
		this.$root.find("[data-field=icon_style]").val(this.state.icon_style);
		this.$root.find("[data-field=gap_x]").val(this.state.gap_x ?? 8);
		this.$root.find("[data-field=gap_y]").val(this.state.gap_y ?? 8);
		this.$root.find("[data-field=columns]").val(this.state.columns ?? 5);
		this.$root[0].style.setProperty("--sp-cols", this.state.columns ?? 5);
		this.$root[0].style.setProperty("--sp-gap-x", `${this.state.gap_x ?? 8}px`);
		this.$root[0].style.setProperty("--sp-gap-y", `${this.state.gap_y ?? 8}px`);

		this.$root.find("[data-field]").on("input change", (e) => {
			const $el = $(e.currentTarget);
			const field = $el.data("field");
			if (!this.can_publish && (field === "enable_custom_styles" || field === "apply_to_all_users")) return;
			if ($el.is(":checkbox")) {
				this.state[field === "enable_custom_styles" ? "enabled" : field] = $el.is(":checked") ? 1 : 0;
				return;
			}
			if (field === "gap_x" || field === "gap_y") {
				const gap = parseInt($el.val(), 10);
				if (!Number.isFinite(gap)) return;
				const clamped = Math.min(SP_HOME_GAP_MAX, Math.max(SP_HOME_GAP_MIN, gap));
				this.state[field] = clamped;
				if (e.type === "change") $el.val(clamped);
				this.$root[0].style.setProperty(field === "gap_x" ? "--sp-gap-x" : "--sp-gap-y", `${clamped}px`);
				return;
			}
			if (field === "columns") {
				let cols = parseInt($el.val(), 10);
				if (Number.isNaN(cols)) cols = 5;
				cols = Math.min(10, Math.max(2, cols));
				this.state.columns = cols;
				$el.val(cols);
				this.$root[0].style.setProperty("--sp-cols", cols);
				return;
			}
			this.state[field] = $el.val();
			this.render();
		});

		const $board = this.$root.find(".sp-home-board");
		this.category_names().forEach((category) => {
			$board.append(this.render_category(category));
		});
		this.bind_sortable();
	}

	create_actions_html() {
		const actions = [["category", "list-plus", __("دسته جدید")]];
		if (this.can_publish) {
			actions.push(["icon", "square-plus", __("آیکون جدید")], ["folder", "folder-plus", __("پوشه جدید")]);
		}
		const buttons = actions.map(([kind, icon, label]) => `
			<button type="button" class="btn btn-default btn-sm sp-home-create" data-create="${kind}">
				${frappe.utils.icon(icon, "sm")}
				<span>${frappe.utils.escape_html(label)}</span>
			</button>`).join("");
		return `<div class="sp-home-create-actions" role="group" aria-label="${frappe.utils.escape_html(__("افزودن"))}">${buttons}</div>`;
	}

	category_names() {
		const names = [];
		(this.state.categories || []).forEach((category) => {
			if (category && !names.includes(category)) names.push(category);
		});
		(this.state.items || []).forEach((item) => {
			if (item.hidden) return;
			const category = item.category || "عمومی";
			if (!names.includes(category)) names.push(category);
		});
		if (!names.length) names.push("عمومی");
		this.state.categories = names;
		return names;
	}

	effective_shape(item) {
		return item.use_custom_style ? item.shape || this.state.default_shape : this.state.default_shape || item.shape || "rounded";
	}

	effective_size(item) {
		return item.use_custom_style ? item.size || this.state.default_size : this.state.default_size || item.size || "medium";
	}

	icon_markup(item) {
		const bundled = frappe.utils.get_desktop_icon?.(item.label, (this.state.icon_style || "Solid").toLowerCase());
		const resolved = window.sp_home_resolve_icon
			? window.sp_home_resolve_icon(item, bundled)
			: { kind: "letter", value: "؟", label: item.label || "" };
		if (!window.sp_home_icon_markup) {
			return { className: "is-letter", html: `<span class="sp-home-letter">؟</span>` };
		}
		return window.sp_home_icon_markup(resolved, {
			iconStyle: this.state.icon_style,
			customColor: item.custom_color,
		});
	}

	render_category(category) {
		const items = this.state.items.filter((item) => item.icon_type !== "Folder" && (item.category || "عمومی") === category);
		const folders = (this.state.folders || []).filter((folder) => (folder.category || "عمومی") === category);
		const folder_names = new Set(folders.map((folder) => folder.folder_name));
		const entries = [
			...items.filter((item) => !folder_names.has(item.folder)).map((item) => ({ kind: "icon", sequence: Number(item.sequence) || 0, item })),
			...folders.map((folder) => ({ kind: "folder", sequence: Number(folder.sequence) || 0, folder })),
		].sort((a, b) => a.sequence - b.sequence || (a.kind === "folder" ? -1 : 1));
		const can_delete = this.can_publish && !items.length && !folders.length;
		const $section = $(`
			<section class="sp-home-category" data-category="${frappe.utils.escape_html(category)}">
				<header>
					<button class="sp-category-handle" type="button" aria-label="جابه‌جایی دسته" title="جابه‌جایی دسته">⋮⋮</button>
					<input class="sp-category-title" value="${frappe.utils.escape_html(category)}">
					<button class="btn btn-xs btn-default sp-rename-cat" type="button">تغییر نام</button>
					${can_delete ? `<button class="sp-delete-cat" type="button" title="حذف دسته" aria-label="حذف دسته">×</button>` : ""}
				</header>
				<div class="sp-home-mixed"></div>
			</section>
		`);
		const $mixed = $section.find(".sp-home-mixed");
		entries.forEach((entry) => {
			if (entry.kind === "icon") $mixed.append(this.render_card(entry.item));
			else $mixed.append(this.render_folder(entry.folder, items));
		});
		const rename = (rerender = true) => {
			const current = $section.attr("data-category") || category;
			const next = ($section.find(".sp-category-title").val() || "").trim();
			if (!next) {
				$section.find(".sp-category-title").val(current);
				return;
			}
			if (next === current) return;
			if ((this.state.categories || []).includes(next)) {
				frappe.show_alert({ message: __("این نام دسته از قبل وجود دارد."), indicator: "orange" });
				$section.find(".sp-category-title").val(current);
				return;
			}
			this.note_category_rename(current, next);
			this.state.items.forEach((item) => {
				if (item.category === current) item.category = next;
			});
			(this.state.folders || []).forEach((folder) => {
				if ((folder.category || "عمومی") === current) folder.category = next;
			});
			this.state.categories = (this.state.categories || []).map((name) => name === current ? next : name);
			$section.attr("data-category", next);
			if (rerender) this.render();
		};
		$section.find(".sp-rename-cat").on("click", () => rename(true));
		$section.find(".sp-category-title").on("change", () => rename(false));
		if (can_delete) {
			$section.find(".sp-delete-cat").on("click", () => {
				const name = $section.attr("data-category") || category;
				frappe.confirm(__("دسته «{0}» حذف شود؟", [name]), () => {
					this.state.categories = (this.state.categories || []).filter((row) => row !== name);
					if (this.category_origin) delete this.category_origin[name];
					this.render();
				});
			});
		}
		$section.find(".sp-category-title").on("keydown", (event) => {
			if (event.key === "Enter") {
				event.preventDefault();
				rename(true);
			}
		});
		return $section;
	}

	render_card(item) {
		const label = __(item.custom_label || item.label);
		const shape = this.effective_shape(item);
		const size = this.effective_size(item);
		const markup = this.icon_markup(item);
		const $card = $(`
			<article class="sp-home-card ${item.hidden ? "is-hidden" : ""}" data-name="${frappe.utils.escape_html(item.name)}" data-shape="${shape}" data-size="${size}">
				<button class="sp-home-delete" type="button" title="مخفی کردن از صفحه اصلی" aria-label="مخفی کردن از صفحه اصلی">×</button>
				<div class="sp-home-card-icon ${markup.className || ""}" style="${markup.background ? `background:${markup.background}` : ""}${markup.stroke ? `;--icon-stroke:${markup.stroke}` : ""}">${markup.html || ""}</div>
				<div class="sp-home-card-title">${frappe.utils.escape_html(label)}</div>
			</article>
		`);
		$card.find(".sp-home-delete").on("click", (event) => {
			event.preventDefault();
			event.stopPropagation();
			item.hidden = 1;
			this.render();
		});
		return $card;
	}

	folder_face(folder) {
		if (!window.sp_home_folder_face) {
			return this.icon_markup({
				label: folder.folder_name,
				custom_label: folder.folder_name,
				icon_name: folder.icon_name,
				custom_icon_image: folder.custom_icon_image,
			});
		}
		return window.sp_home_folder_face(folder, this.state.items || [], {
			iconStyle: this.state.icon_style,
			resolve: (item) => {
				const bundled = frappe.utils.get_desktop_icon?.(item.label || item.name, (this.state.icon_style || "Solid").toLowerCase());
				return window.sp_home_resolve_icon(item, bundled);
			},
		});
	}

	render_folder(folder) {
		const face = this.folder_face(folder);
		const shape = this.state.default_shape || "rounded";
		const size = this.state.default_size || "medium";
		const style = `${face.background ? `background:${face.background}` : ""}${face.stroke ? `;--icon-stroke:${face.stroke}` : ""}`;
		return $(`
			<article class="sp-home-card sp-home-folder" data-folder="${frappe.utils.escape_html(folder.folder_name)}" data-shape="${shape}" data-size="${size}">
				<div class="sp-home-card-icon ${face.className || ""}" style="${style}">${face.html || ""}</div>
				<div class="sp-home-card-title">${frappe.utils.escape_html(folder.folder_name)}</div>
			</article>
		`);
	}

	folder_dialog_actions(folder, dialog) {
		const bar = document.createElement("div");
		bar.className = "sp-folder-dialog-actions";
		[
			["edit", __("تغییر نام"), () => this.rename_folder(folder)],
			["image", __("آیکون پوشه"), () => this.edit_folder_icon(folder)],
			["trash-2", __("حذف پوشه"), () => this.delete_folder(folder)],
		].forEach(([icon, label, action]) => {
			const button = document.createElement("button");
			button.type = "button";
			button.className = "btn btn-default btn-xs";
			button.innerHTML = `${frappe.utils.icon(icon, "xs")}<span>${frappe.utils.escape_html(label)}</span>`;
			button.addEventListener("click", () => {
				dialog.hide();
				action();
			});
			bar.append(button);
		});
		return bar;
	}

	rename_folder(folder) {
		frappe.prompt(
			{ fieldname: "folder_name", fieldtype: "Data", label: __("نام پوشه"), reqd: 1, default: folder.folder_name },
			(values) => {
				const next = (values.folder_name || "").trim();
				if (!next || next === folder.folder_name) return;
				if ((this.state.folders || []).some((row) => row.folder_name === next)) {
					frappe.show_alert({ message: __("این نام پوشه از قبل وجود دارد."), indicator: "orange" });
					return;
				}
				this.state.items.forEach((item) => {
					if (item.folder === folder.folder_name) item.folder = next;
				});
				folder.folder_name = next;
				this.render();
			},
			__("تغییر نام پوشه"),
			__("اعمال")
		);
	}

	open_folder_dialog(folder) {
		const dialog = new frappe.ui.Dialog({
			title: __(folder.folder_name),
			size: "small",
		});
		dialog.$body.empty();
		const note = document.createElement("p");
		note.className = "text-muted sp-folder-dialog-note";
		note.textContent = __("ترتیب را با کشیدن تغییر دهید. برای برگرداندن آیکون به دسته، «بازگشت به دسته» را بزنید.");
		const list = document.createElement("div");
		list.className = "sp-folder-dialog-list";
		if (this.can_publish) dialog.$body.append(this.folder_dialog_actions(folder, dialog));
		dialog.$body.append(note, list);
		const members = (this.state.items || [])
			.filter((item) => item.folder === folder.folder_name)
			.sort((a, b) => (Number(a.sequence) || 0) - (Number(b.sequence) || 0)
				|| String(a.label || "").localeCompare(String(b.label || "")));
		if (!members.length) {
			const empty = document.createElement("p");
			empty.className = "text-muted";
			empty.textContent = __("این پوشه خالی است.");
			list.append(empty);
		}
		members.forEach((item) => {
			const markup = this.icon_markup(item);
			const row = document.createElement("div");
			row.className = "sp-folder-member";
			row.dataset.name = item.name;
			row.innerHTML = `
				<span class="sp-folder-member-icon ${markup.className || ""}" style="${markup.background ? `background:${markup.background}` : ""}">${markup.html || ""}</span>
				<span class="sp-folder-member-label">${frappe.utils.escape_html(__(item.custom_label || item.label))}</span>
				<button type="button" class="btn btn-xs btn-default sp-folder-eject">${frappe.utils.escape_html(__("بازگشت به دسته"))}</button>`;
			row.querySelector(".sp-folder-eject").addEventListener("click", (event) => {
				event.preventDefault();
				event.stopPropagation();
				this.release_from_folder(item, folder);
				dialog.hide();
				this.render();
			});
			list.append(row);
		});
		dialog.$wrapper.on("hidden.bs.modal", () => {
			if (this.member_sortable) {
				this.member_sortable.destroy();
				this.member_sortable = null;
			}
		});
		if (members.length && typeof Sortable !== "undefined") {
			this.member_sortable = new Sortable(list, {
				animation: 150,
				draggable: ".sp-folder-member",
				filter: ".sp-folder-eject",
				preventOnFilter: false,
				onEnd: () => {
					[...list.querySelectorAll(":scope > .sp-folder-member")].forEach((row, index) => {
						const item = this.state.items.find((entry) => entry.name === row.dataset.name);
						if (item) item.sequence = index + 1;
					});
					this.refresh_folder_face(folder);
				},
			});
		}
		dialog.show();
	}

	release_from_folder(item, folder) {
		const category = folder.category || item.category || "عمومی";
		const at = (Number(folder.sequence) || 0) + 1;
		(this.state.items || []).forEach((row) => {
			if (row === item || row.folder) return;
			if ((row.category || "عمومی") === category && (Number(row.sequence) || 0) >= at) {
				row.sequence = (Number(row.sequence) || 0) + 1;
			}
		});
		(this.state.folders || []).forEach((row) => {
			if (row === folder) return;
			if ((row.category || "عمومی") === category && (Number(row.sequence) || 0) >= at) {
				row.sequence = (Number(row.sequence) || 0) + 1;
			}
		});
		item.folder = "";
		item.category = category;
		item.sequence = at;
	}

	refresh_folder_face(folder) {
		const face = this.folder_face(folder);
		const tile = [...this.$root[0].querySelectorAll(".sp-home-folder")].find((el) => el.dataset.folder === folder.folder_name);
		const icon = tile && tile.querySelector(".sp-home-card-icon");
		if (!icon) return;
		icon.className = `sp-home-card-icon ${face.className || ""}`;
		icon.style.background = face.background || "";
		if (face.stroke) icon.style.setProperty("--icon-stroke", face.stroke);
		else icon.style.removeProperty("--icon-stroke");
		icon.innerHTML = face.html || "";
	}

	delete_folder(folder) {
		const members = this.state.items.filter((item) => item.folder === folder.folder_name);
		const finish = () => {
			members.forEach((item, index) => {
				item.folder = "";
				item.category = folder.category || item.category || "عمومی";
				item.sequence = (Number(folder.sequence) || 0) + index;
			});
			this.state.folders = (this.state.folders || []).filter((row) => row !== folder);
			this.render();
		};
		if (!members.length) {
			finish();
			return;
		}
		frappe.confirm("آیکون‌های داخل پوشه حذف نمی‌شوند و به همین دسته برمی‌گردند. پوشه حذف شود؟", finish);
	}

	edit_folder_icon(folder) {
		const dialog = new frappe.ui.Dialog({
			title: __("آیکون پوشه"),
			fields: [
				{ fieldname: "custom_icon_image", fieldtype: "Attach Image", label: __("تصویر آیکون"), default: folder.custom_icon_image || "" },
				{ fieldname: "icon_name", fieldtype: "Icon", label: __("آیکون فراپه"), default: folder.icon_name || "" },
			],
			primary_action_label: __("اعمال"),
			primary_action: (values) => {
				folder.custom_icon_image = values.custom_icon_image || "";
				folder.icon_name = values.icon_name || "";
				dialog.hide();
				this.render();
			},
		});
		dialog.set_secondary_action_label(__("پیش‌نمایش خودکار"));
		dialog.set_secondary_action(() => {
			folder.custom_icon_image = "";
			folder.icon_name = "";
			dialog.hide();
			this.render();
		});
		dialog.show();
	}

	prompt_new_folder() {
		const category = (this.state.categories || [])[0] || "عمومی";
		frappe.prompt(
			{ fieldname: "folder_name", fieldtype: "Data", label: __("نام پوشه"), reqd: 1 },
			(values) => {
				const folder_name = values.folder_name.trim();
				if (!folder_name || (this.state.folders || []).some((row) => row.folder_name === folder_name)) return;
				const sequences = [
					...(this.state.items || [])
						.filter((item) => (item.category || "عمومی") === category && !item.folder)
						.map((item) => Number(item.sequence) || 0),
					...(this.state.folders || [])
						.filter((row) => (row.category || "عمومی") === category)
						.map((row) => Number(row.sequence) || 0),
				];
				this.state.folders = this.state.folders || [];
				this.state.folders.push({
					folder_name,
					category,
					sequence: sequences.length ? Math.max(...sequences) + 1 : 1,
					icon_name: "",
					custom_icon_image: "",
				});
				this.render();
			},
			__("پوشه جدید"),
			__("ساخت")
		);
	}

	on_card_click(event) {
		if (this.dragging) {
			this.dragging = false;
			event.preventDefault();
			event.stopPropagation();
			return;
		}
		if ($(event.target).closest(".sp-home-delete").length) return;
		const card = event.currentTarget;
		if (card.classList.contains("sp-home-folder")) {
			const folder = (this.state.folders || []).find((row) => row.folder_name === card.dataset.folder);
			if (folder) this.open_folder_dialog(folder);
			return;
		}
		const item = (this.state.items || []).find((row) => row.name === card.dataset.name);
		if (item) this.edit_item(item);
	}

	bind_sortable() {
		if (typeof Sortable === "undefined") return;
		const board = this.$root.find(".sp-home-board").get(0);
		if (!board) return;
		this.sortables.push(new Sortable(board, {
			animation: 150,
			handle: ".sp-category-handle",
			draggable: ".sp-home-category",
			onEnd: () => {
				const names = [...board.querySelectorAll(":scope > .sp-home-category")].map((section) => (
					($(section).find(".sp-category-title").val() || "عمومی").trim()
				));
				this.state.categories = names.length ? names : ["عمومی"];
				this.render();
			},
		}));
	}

	on_card_pointer_down(event) {
		if (event.button !== 0) return;
		if ($(event.target).closest(".sp-home-delete, a, button, input").length) return;
		this.dragging = false;
		const card = event.currentTarget;
		this.drag_session = {
			card,
			startX: event.clientX,
			startY: event.clientY,
			moved: false,
		};
		this._drag_move = (ev) => this.on_card_pointer_move(ev);
		this._drag_up = (ev) => this.on_card_pointer_up(ev);
		this._drag_cancel = () => this.on_card_pointer_cancel();
		document.addEventListener("pointermove", this._drag_move);
		document.addEventListener("pointerup", this._drag_up);
		document.addEventListener("pointercancel", this._drag_cancel);
	}

	stop_drag_listeners() {
		document.removeEventListener("pointermove", this._drag_move);
		document.removeEventListener("pointerup", this._drag_up);
		document.removeEventListener("pointercancel", this._drag_cancel);
	}

	on_card_pointer_cancel() {
		this.stop_drag_listeners();
		const session = this.drag_session;
		this.drag_session = null;
		this.dragging = false;
		if (!session?.moved) return;
		this.clear_drop_target();
		this.release_lifted_card(session);
		this.render();
	}

	on_card_pointer_move(event) {
		const session = this.drag_session;
		if (!session) return;
		const distance = Math.hypot(event.clientX - session.startX, event.clientY - session.startY);
		if (!session.moved && distance < 5) return;
		if (!session.moved) {
			session.moved = true;
			this.dragging = true;
			this.lift_card(session);
		}
		event.preventDefault();
		this.place_insertion(session, event.clientX, event.clientY);
	}

	on_card_pointer_up() {
		this.stop_drag_listeners();
		const session = this.drag_session;
		this.drag_session = null;
		if (!session?.moved) {
			this.dragging = false;
			return;
		}
		const folder = session.folder || "";
		this.clear_drop_target();
		if (folder && !session.card.classList.contains("sp-home-folder")) {
			this.move_into_folder(session.card.dataset.name, folder);
		} else if (session.mixed) {
			this.commit_insertion(session);
		}
		this.release_lifted_card(session);
		this.render();
	}

	lift_card(session) {
		const rect = session.card.getBoundingClientRect();
		session.width = rect.width;
		session.height = rect.height;
		const slot = document.createElement("div");
		slot.className = "sp-home-slot";
		slot.style.flex = `0 0 ${rect.width}px`;
		slot.style.width = `${rect.width}px`;
		slot.style.height = `${rect.height}px`;
		slot.style.boxSizing = "border-box";
		slot.style.border = "2px dashed var(--primary)";
		slot.style.borderRadius = "12px";
		slot.style.pointerEvents = "none";
		session.card.before(slot);
		session.slot = slot;
		session.mixed = session.card.parentElement;
		const card = session.card;
		card.classList.add("is-lifted");
		card.style.position = "fixed";
		card.style.zIndex = "1000";
		card.style.pointerEvents = "none";
		card.style.margin = "0";
		card.style.width = `${rect.width}px`;
		card.style.left = `${rect.left}px`;
		card.style.top = `${rect.top}px`;
		document.body.appendChild(card);
	}

	release_lifted_card(session) {
		if (session?.card?.isConnected) session.card.remove();
	}

	place_insertion(session, x, y) {
		session.card.style.left = `${x - session.width / 2}px`;
		session.card.style.top = `${y - 24}px`;
		const folder = session.card.classList.contains("sp-home-folder") ? null : this.folder_at_point(session.card, x, y);
		this.clear_drop_target();
		session.folder = folder ? (folder.dataset.folder || "") : "";
		if (session.folder) {
			folder.classList.add("is-drop-target");
			return;
		}
		const mixed = this.mixed_under_pointer(x, y, session) || session.mixed;
		session.mixed = mixed;
		const visible = [...mixed.children].filter(
			(el) => el === session.slot || (el.classList.contains("sp-home-card") && el !== session.card)
		);
		const rects = visible.map((el) => {
			const rect = el.getBoundingClientRect();
			return { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
		});
		const rtl = document.documentElement.getAttribute("dir") !== "ltr";
		const index = window.sp_home_slot_index(rects, visible.indexOf(session.slot), { x, y }, rtl);
		const cards = visible.filter((el) => el !== session.slot);
		const anchor = cards[index];
		if (anchor) {
			if (anchor.previousElementSibling !== session.slot) anchor.before(session.slot);
		} else if (mixed.lastElementChild !== session.slot) {
			mixed.append(session.slot);
		}
	}

	mixed_under_pointer(x, y, session) {
		const stack = document.elementsFromPoint(x, y) || [];
		for (const el of stack) {
			if (!el || el === session.card || session.card.contains(el)) continue;
			const mixed = el.closest?.(".sp-home-category > .sp-home-mixed");
			if (mixed && this.$root[0].contains(mixed)) return mixed;
		}
		return session.mixed;
	}

	commit_insertion(session) {
		const category = ($(session.mixed).closest(".sp-home-category").find(".sp-category-title").val() || "عمومی").trim();
		const cards = [...session.mixed.querySelectorAll(":scope > .sp-home-card")].filter((el) => el !== session.card);
		const slot_index = [...session.mixed.children].filter((el) => el === session.slot || cards.includes(el)).indexOf(session.slot);
		const key = this.card_key(session.card);
		const moved = key.startsWith("folder:")
			? (this.state.folders || []).find((row) => `folder:${row.folder_name}` === key)
			: (this.state.items || []).find((row) => `icon:${row.name}` === key);
		if (!moved) return;
		const previous = moved.category || "عمومی";
		moved.category = category;
		if (!key.startsWith("folder:")) moved.folder = "";
		else {
			(this.state.items || []).forEach((item) => {
				if (item.folder === moved.folder_name) item.category = category;
			});
		}
		const entries = this.loose_entries(category).filter((entry) => entry.ref !== moved);
		const index = Math.max(0, Math.min(slot_index < 0 ? entries.length : slot_index, entries.length));
		entries.splice(index, 0, { ref: moved });
		entries.forEach((entry, position) => {
			entry.ref.sequence = position + 1;
		});
		if (previous !== category) {
			this.loose_entries(previous).forEach((entry, position) => {
				entry.ref.sequence = position + 1;
			});
		}
	}

	card_key(card) {
		return card.classList.contains("sp-home-folder") ? `folder:${card.dataset.folder}` : `icon:${card.dataset.name}`;
	}

	loose_entries(category) {
		const items = (this.state.items || []).filter((item) => item.icon_type !== "Folder" && (item.category || "عمومی") === category);
		const folders = (this.state.folders || []).filter((folder) => (folder.category || "عمومی") === category);
		const names = new Set(folders.map((folder) => folder.folder_name));
		return [
			...items.filter((item) => !names.has(item.folder)).map((item) => ({ kind: "icon", key: `icon:${item.name}`, sequence: Number(item.sequence) || 0, ref: item })),
			...folders.map((folder) => ({ kind: "folder", key: `folder:${folder.folder_name}`, sequence: Number(folder.sequence) || 0, ref: folder })),
		].sort((a, b) => a.sequence - b.sequence || (a.kind === "folder" ? -1 : 1));
	}

	clear_drop_target() {
		this.$root.find(".sp-home-folder.is-drop-target").removeClass("is-drop-target");
	}

	folder_face_zone(folder, x, y) {
		const rect = folder.getBoundingClientRect();
		if (!rect.width || !rect.height) return false;
		const insetX = rect.width * 0.28;
		const insetY = rect.height * 0.28;
		return x >= rect.left + insetX && x <= rect.right - insetX && y >= rect.top + insetY && y <= rect.bottom - insetY;
	}

	folder_at_point(dragged, x, y) {
		if (x == null || y == null) return null;
		const stack = document.elementsFromPoint(x, y) || [];
		for (const el of stack) {
			if (!el || el === dragged || dragged?.contains(el)) continue;
			const folder = el.closest?.(".sp-home-category > .sp-home-mixed > .sp-home-folder");
			if (!folder || folder === dragged) continue;
			if (this.folder_face_zone(folder, x, y)) return folder;
		}
		return null;
	}

	move_into_folder(item_name, folder_name) {
		const item = (this.state.items || []).find((row) => row.name === item_name);
		const folder = (this.state.folders || []).find((row) => row.folder_name === folder_name);
		if (!item || !folder || item.folder === folder.folder_name) return;
		const siblings = (this.state.items || []).filter((row) => row.folder === folder.folder_name && row !== item);
		item.folder = folder.folder_name;
		item.category = folder.category || item.category || "عمومی";
		item.sequence = siblings.reduce((max, row) => Math.max(max, Number(row.sequence) || 0), 0) + 1;
	}

	edit_item(item) {
		const fields = [
			{ fieldname: "custom_label", fieldtype: "Data", label: __("نام نمایشی"), default: item.custom_label || item.label },
			{ fieldname: "category", fieldtype: "Data", label: __("دسته"), default: item.category || "عمومی" },
		];
		if (this.can_publish) {
			fields.push({
				fieldname: "custom_link",
				fieldtype: "Data",
				label: __("لینک"),
				default: item.custom_link || "",
				description: __("خالی بماند تا لینک استاندارد همین آیکون در فرپه استفاده شود."),
			});
		}
		fields.push(
			{
				fieldname: "custom_icon_image",
				fieldtype: "Attach Image",
				label: __("تصویر آیکون"),
				default: item.custom_icon_image || "",
				description: __("اگر تصویر بگذارید، همان روی صفحه اصلی دیده می‌شود."),
			},
			{
				fieldname: "icon_name",
				fieldtype: "Icon",
				label: __("آیکون فراپه"),
				default: item.icon_name || "",
				description: item.icon ? __("اگر خالی بماند، آیکون فعلی «{0}» استفاده می‌شود.", [item.icon]) : __("اگر خالی بماند، آیکون پیش‌فرض سامانه استفاده می‌شود."),
			},
			{
				fieldname: "shape",
				fieldtype: "Select",
				label: __("شکل"),
				options: [{ value: "rounded", label: "گوشه‌گرد" }, { value: "circle", label: "دایره" }, { value: "square", label: "مربع" }],
				default: this.effective_shape(item),
			},
			{
				fieldname: "size",
				fieldtype: "Select",
				label: __("اندازه"),
				options: [{ value: "small", label: "کوچک" }, { value: "medium", label: "متوسط" }, { value: "large", label: "بزرگ" }, { value: "xlarge", label: "خیلی بزرگ" }],
				default: this.effective_size(item),
			},
			{ fieldname: "use_custom_style", fieldtype: "Check", label: "شکل و اندازهٔ اختصاصی", default: item.use_custom_style },
			{ fieldname: "custom_color", fieldtype: "Color", label: __("رنگ"), default: item.custom_color },
			{ fieldname: "hidden", fieldtype: "Check", label: __("مخفی در صفحه اصلی"), description: __("فقط نمایش در صفحه اصلی را عوض می‌کند و آیکون استاندارد را حذف نمی‌کند."), default: item.hidden }
		);
		const dialog = new frappe.ui.Dialog({
			title: __("ویرایش آیکون"),
			fields,
			primary_action_label: __("اعمال روی کارت"),
			primary_action: (values) => {
				Object.assign(item, values);
				item.hidden = values.hidden ? 1 : 0;
				item.use_custom_style = values.use_custom_style ? 1 : 0;
				const category = (values.category || "عمومی").trim();
				item.category = category;
				if (!(this.state.categories || []).includes(category)) this.state.categories.push(category);
				dialog.hide();
				this.render();
			},
		});
		if (this.can_publish && item.owned) {
			dialog.set_secondary_action_label(__("حذف دائمی آیکون سفارشی"));
			dialog.set_secondary_action(() => {
				frappe.confirm(__("آیکون سفارشی «{0}» و داده‌های وابسته در مدیریت صفحه اصلی برای همیشه حذف شوند؟ این مخفی کردن نیست.", [item.custom_label || item.label]), () => {
					frappe.call({
						method: "smartprocee_erpnext_homepage.home_manager.api.delete_owned_desktop_icon",
						args: { name: item.name },
						freeze: true,
						callback: (response) => {
							this.state = response.message;
							dialog.hide();
							this.render();
						},
					});
				});
			});
		}
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
				if (!category || (this.state.categories || []).includes(category)) return;
				this.state.categories.push(category);
				if (this.category_origin) this.category_origin[category] = category;
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
					callback: () => {
						dialog.hide();
						this.load();
					},
				});
			},
		});
		dialog.show();
	}

	payload(for_global = false) {
		const data = {
			categories: this.state.categories || [],
			folders: (this.state.folders || []).map((folder) => ({
				folder_name: folder.folder_name,
				category: folder.category || "عمومی",
				sequence: Number(folder.sequence) || 0,
				icon_name: for_global ? (folder.icon_name || "") : "",
				custom_icon_image: for_global ? (folder.custom_icon_image || "") : "",
			})),
			items: (this.state.items || []).filter((item) => item.name),
			columns: this.state.columns ?? 5,
			gap_x: this.state.gap_x ?? 8,
			gap_y: this.state.gap_y ?? 8,
			default_shape: this.state.default_shape || "rounded",
			default_size: this.state.default_size || "medium",
			icon_style: this.state.icon_style || "Solid",
		};
		if (!for_global) return data;
		Object.assign(data, {
			enable_custom_styles: this.state.enabled ? 1 : 0,
			apply_to_all_users: this.state.apply_to_all_users ? 1 : 0,
			category_renames: this.category_renames(),
		});
		return data;
	}

	remember_categories() {
		this.category_origin = {};
		(this.state.categories || []).forEach((name) => {
			this.category_origin[name] = name;
		});
	}

	note_category_rename(current, next) {
		if (!this.category_origin) this.remember_categories();
		const origin = Object.prototype.hasOwnProperty.call(this.category_origin, current)
			? this.category_origin[current]
			: current;
		delete this.category_origin[current];
		this.category_origin[next] = origin;
	}

	category_renames() {
		const current = new Set(this.state.categories || []);
		return Object.entries(this.category_origin || [])
			.filter(([name, origin]) => origin && origin !== name && current.has(name))
			.map(([name, origin]) => ({ from: origin, to: name }));
	}

	save() {
		frappe.call({
			method: "smartprocee_erpnext_homepage.home_manager.api.save_my_layout",
			args: { payload: JSON.stringify(this.payload(false)) },
			freeze: true,
			freeze_message: __("در حال ذخیره چیدمان شما..."),
			callback: (r) => {
				this.apply_state(r.message);
				this.after_save();
			},
		});
	}

	publish_global() {
		frappe.confirm(__("این چیدمان به‌عنوان پیش‌فرض عمومی ذخیره شود؟ فقط چیدمان شخصی شما پاک می‌شود."), () => {
			frappe.call({
				method: "smartprocee_erpnext_homepage.home_manager.api.save_as_global_default",
				args: { payload: JSON.stringify(this.payload(true)) },
				freeze: true,
				freeze_message: __("در حال ذخیره پیش‌فرض عمومی..."),
				callback: (r) => {
					this.apply_state(r.message);
					this.after_save(__("پیش‌فرض عمومی ذخیره شد."));
				},
			});
		});
	}

	reset_personal() {
		frappe.confirm(__("چیدمان شخصی شما پاک شود و چیدمان پیش‌فرض برگردد؟ چیدمان دیگران تغییر نمی‌کند."), () => {
			frappe.call({
				method: "smartprocee_erpnext_homepage.home_manager.api.reset_my_layout",
				freeze: true,
				callback: (r) => {
					this.apply_state(r.message);
					this.refresh_boot();
					frappe.show_alert({ message: __("به چیدمان پیش‌فرض بازگشت."), indicator: "green" });
				},
			});
		});
	}

	refresh_boot() {
		try { localStorage.setItem("sp_home_updated", `${Date.now()}`); } catch (_) { /* Optional cross-tab signal. */ }
		frappe.call({
			method: "smartprocee_erpnext_homepage.home_manager.api.get_current_layout",
			callback: (r) => {
				if (frappe.boot && r.message) frappe.boot.sp_home = r.message;
				window.sp_home_apply_layout?.();
			},
		});
	}

	after_save(message) {
		this.refresh_boot();
		frappe.show_alert({ message: message || __("ذخیره شد."), indicator: "green" });
	}
}

window.SPHomeManager = SPHomeManager;
