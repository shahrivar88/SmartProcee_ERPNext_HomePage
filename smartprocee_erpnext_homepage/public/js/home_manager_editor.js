const SP_HOME_GAP_MIN = window.SP_HOME_GAP_MIN;
const SP_HOME_GAP_MAX = window.SP_HOME_GAP_MAX;

class SPHomeManager {
	constructor(page, options) {
		this.page = page;
		this.mode = options?.mode === "personal" ? "personal" : "global";
		this.state = null;
		this.sortables = [];
		this.drop_folder = "";
		this.suppress_folder_click = false;
		this.setup_actions();
		this.page.main.html(`<div class="sp-home-editor"></div>`);
		this.$root = this.page.main.find(".sp-home-editor");
	}

	setup_actions() {
		const save_label = this.mode === "personal" ? __("ذخیره چیدمان من") : __("ذخیره و اعمال");
		this.page.set_primary_action(save_label, () => this.save());
		this.install_home_link();
		if (this.mode === "global") {
			this.page.add_inner_button(__("آیکون جدید"), () => this.prompt_new_icon());
			this.page.add_inner_button(__("پوشه جدید"), () => this.prompt_new_folder());
		} else {
			this.page.add_inner_button(__("بازنشانی به چیدمان پیش‌فرض"), () => this.reset_personal());
		}
		this.page.add_inner_button(__("دسته جدید"), () => this.prompt_new_category());
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

	install_home_link() {
		const actions = this.page.standard_actions;
		if (!actions || !actions.length) return;
		actions.find(".sp-home-go-desktop").remove();
		const link = document.createElement("a");
		link.className = "btn btn-secondary btn-default btn-sm sp-home-go-desktop";
		link.href = this.home_href();
		link.textContent = __("رفتن به صفحه اصلی");
		actions.prepend(link);
	}

	load() {
		const method = this.mode === "personal"
			? "smartprocee_erpnext_homepage.home_manager.api.get_my_layout"
			: "smartprocee_erpnext_homepage.home_manager.api.get_layout";
		frappe.call({
			method,
			freeze: true,
			freeze_message: __("در حال بارگذاری صفحه اصلی..."),
			callback: (r) => {
				this.state = r.message;
				this.state.categories = this.state.categories || [];
				this.state.folders = this.state.folders || [];
				this.remember_categories();
				this.render();
			},
		});
	}

	render() {
		if (!this.state) return;
		this.sortables.forEach((sortable) => sortable.destroy());
		this.sortables = [];
		const personal = this.mode === "personal";
		const disabled = personal ? "disabled" : "";
		this.$root.html(`
			<div class="sp-home-toolbar">
				${personal ? "" : `
				<label class="sp-toggle">
					<input type="checkbox" data-field="enable_custom_styles" ${this.state.enabled ? "checked" : ""}>
					<span>اعمال ظاهر سفارشی روی صفحه اصلی</span>
				</label>
				<label class="sp-toggle">
					<input type="checkbox" data-field="apply_to_all_users" ${this.state.apply_to_all_users ? "checked" : ""}>
					<span>اعمال برای همه کاربران</span>
				</label>`}
				<label>
					شکل پیش‌فرض
					<select data-field="default_shape" ${disabled}>
						<option value="rounded">گوشه‌گرد</option>
						<option value="circle">دایره</option>
						<option value="square">مربع</option>
					</select>
				</label>
				<label>
					اندازه پیش‌فرض
					<select data-field="default_size" ${disabled}>
						<option value="small">کوچک</option>
						<option value="medium">متوسط</option>
						<option value="large">بزرگ</option>
						<option value="xlarge">خیلی بزرگ</option>
					</select>
				</label>
				<label>
					سبک آیکون
					<select data-field="icon_style" ${disabled}>
						<option value="Solid">پررنگ</option>
						<option value="Subtle">ملایم</option>
					</select>
				</label>
				<label>
					حداکثر ستون
					<input type="number" min="2" max="10" data-field="columns" ${disabled}>
				</label>
				<label>
					فاصله افقی
					<input type="number" min="${SP_HOME_GAP_MIN}" max="${SP_HOME_GAP_MAX}" step="1" data-field="gap_x" ${disabled}>
				</label>
				<label>
					فاصله عمودی
					<input type="number" min="${SP_HOME_GAP_MIN}" max="${SP_HOME_GAP_MAX}" step="1" data-field="gap_y" ${disabled}>
				</label>
			</div>
			<div class="sp-home-hint">${personal
				? "این چیدمان فقط برای شما ذخیره می‌شود. دستهٔ خالی باقی می‌ماند. بازنشانی، چیدمان مدیر را برمی‌گرداند."
				: "این صفحه پیش‌فرض همهٔ کاربرانی است که چیدمان شخصی ندارند. دسته را از دستگیره جابه‌جا کنید. دستهٔ خالی را می‌توان حذف کرد."}</div>
			<div class="sp-home-board"></div>
		`);
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
			if (personal) return;
			const $el = $(e.currentTarget);
			const field = $el.data("field");
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
		const can_delete = this.mode === "global" && !items.length && !folders.length;
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
				<button class="sp-home-delete" type="button" title="مخفی کردن آیکون" aria-label="مخفی کردن آیکون">×</button>
				<div class="sp-home-card-icon ${markup.className || ""}" style="${markup.background ? `background:${markup.background}` : ""}${markup.stroke ? `;--icon-stroke:${markup.stroke}` : ""}">${markup.html || ""}</div>
				<div class="sp-home-card-title">${frappe.utils.escape_html(label)}</div>
			</article>
		`);
		$card.on("click", () => this.edit_item(item));
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
		const personal = this.mode === "personal";
		const face = this.folder_face(folder);
		const shape = this.state.default_shape || "rounded";
		const size = this.state.default_size || "medium";
		const style = `${face.background ? `background:${face.background}` : ""}${face.stroke ? `;--icon-stroke:${face.stroke}` : ""}`;
		const tools = personal ? "" : `
			<div class="sp-folder-tools">
				<button class="sp-folder-rename" type="button" title="تغییر نام" aria-label="تغییر نام">✎</button>
				<button class="sp-folder-icon" type="button" title="آیکون پوشه" aria-label="آیکون پوشه">▣</button>
				<button class="sp-folder-delete" type="button" title="حذف پوشه" aria-label="حذف پوشه">×</button>
			</div>`;
		const $folder = $(`
			<article class="sp-home-card sp-home-folder" data-folder="${frappe.utils.escape_html(folder.folder_name)}" data-shape="${shape}" data-size="${size}">
				${tools}
				<div class="sp-home-card-icon ${face.className || ""}" style="${style}">${face.html || ""}</div>
				<div class="sp-home-card-title">${frappe.utils.escape_html(folder.folder_name)}</div>
			</article>
		`);
		$folder.on("click", (event) => {
			if (this.suppress_folder_click) return;
			if ($(event.target).closest(".sp-folder-tools").length) return;
			this.open_folder_dialog(folder);
		});
		if (!personal) {
			$folder.find(".sp-folder-rename").on("click", (event) => {
				event.preventDefault();
				event.stopPropagation();
				this.rename_folder(folder);
			});
			$folder.find(".sp-folder-delete").on("click", (event) => {
				event.preventDefault();
				event.stopPropagation();
				this.delete_folder(folder);
			});
			$folder.find(".sp-folder-icon").on("click", (event) => {
				event.preventDefault();
				event.stopPropagation();
				this.edit_folder_icon(folder);
			});
		}
		return $folder;
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

	bind_sortable() {
		if (typeof Sortable === "undefined") return;
		const board = this.$root.find(".sp-home-board").get(0);
		if (board) {
			this.sortables.push(new Sortable(board, {
				animation: 150,
				handle: ".sp-category-handle",
				draggable: ".sp-home-category",
				onEnd: () => this.sync_from_dom(),
			}));
		}
		const icon_group = {
			name: "sp-home-icons",
			pull: true,
			put: (to, from, drag) => drag.classList.contains("sp-home-card"),
		};
		this.$root.find(".sp-home-category > .sp-home-mixed").each((_, el) => {
			this.sortables.push(new Sortable(el, {
				group: icon_group,
				animation: 150,
				forceFallback: true,
				fallbackOnBody: true,
				fallbackTolerance: 4,
				draggable: ".sp-home-card, .sp-home-folder",
				filter: ".sp-folder-tools, .sp-folder-tools *, .sp-home-delete",
				preventOnFilter: false,
				onStart: (evt) => {
					this.drop_folder = "";
					const point = evt.originalEvent || {};
					this.drag_origin = { x: point.clientX || 0, y: point.clientY || 0 };
				},
				onMove: (evt) => {
					if (evt.dragged.classList.contains("sp-home-folder")) {
						this.clear_drop_target();
						return true;
					}
					const folder = this.folder_under_pointer(evt);
					this.clear_drop_target();
					if (!folder) {
						this.drop_folder = "";
						return true;
					}
					folder.classList.add("is-drop-target");
					this.drop_folder = folder.dataset.folder || "";
					return false;
				},
				onEnd: (evt) => {
					const target = this.drop_folder;
					const point = evt.originalEvent || {};
					const origin = this.drag_origin || { x: point.clientX || 0, y: point.clientY || 0 };
					const moved = Math.abs((point.clientX || 0) - origin.x) > 4 || Math.abs((point.clientY || 0) - origin.y) > 4;
					this.clear_drop_target();
					this.drop_folder = "";
					if (moved || target) this.suppress_folder_click = true;
					setTimeout(() => {
						this.suppress_folder_click = false;
					}, 0);
					const dragged_item = (this.state.items || []).find((row) => row.name === evt.item.dataset.name);
					if (target && evt.item.classList.contains("sp-home-card") && (!dragged_item || dragged_item.folder !== target)) {
						this.move_into_folder(evt.item.dataset.name, target);
						this.render();
						return;
					}
					this.sync_from_dom();
				},
			}));
		});
	}

	clear_drop_target() {
		this.$root.find(".sp-home-folder.is-drop-target").removeClass("is-drop-target");
	}

	folder_under_pointer(evt) {
		const event = evt.originalEvent;
		if (!event || event.clientX == null) return null;
		const dragged = evt.dragged;
		const stack = document.elementsFromPoint(event.clientX, event.clientY) || [];
		for (const el of stack) {
			if (!el || el === dragged || dragged.contains(el)) continue;
			const folder = el.closest?.(".sp-home-category > .sp-home-mixed > .sp-home-folder");
			if (folder) return folder;
		}
		const related = evt.related;
		const folder = related && (related.classList?.contains("sp-home-folder") ? related : related.closest?.(".sp-home-folder"));
		if (!folder || dragged.contains(folder)) return null;
		const rect = folder.getBoundingClientRect();
		if (event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom) {
			return folder;
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

	sync_from_dom() {
		const categories = [];
		const next = [];
		const seen = new Set();
		this.$root.find(".sp-home-category").each((_, section) => {
			const category = ($(section).find(".sp-category-title").val() || "عمومی").trim();
			if (!categories.includes(category)) categories.push(category);
			let sequence = 1;
			$(section).children(".sp-home-mixed").children().each((__, node) => {
				if (node.classList.contains("sp-home-card") && !node.classList.contains("sp-home-folder")) {
					const item = this.state.items.find((row) => row.name === node.dataset.name);
					if (!item || seen.has(item)) return;
					item.category = category;
					item.folder = "";
					item.sequence = sequence++;
					seen.add(item);
					next.push(item);
					return;
				}
				if (!node.classList.contains("sp-home-folder")) return;
				const folder = (this.state.folders || []).find((row) => row.folder_name === node.dataset.folder);
				if (!folder) return;
				folder.category = category;
				folder.sequence = sequence++;
				this.state.items.forEach((item) => {
					if (item.folder === folder.folder_name) item.category = category;
				});
			});
		});
		this.$root.find(".sp-home-folder-members").each((_, grid) => {
			const folder_name = grid.dataset.folder || "";
			let inner = 1;
			$(grid).children(".sp-home-card").each((__, card) => {
				const item = this.state.items.find((row) => row.name === card.dataset.name);
				if (!item || seen.has(item)) return;
				item.folder = folder_name;
				item.sequence = inner++;
				seen.add(item);
				next.push(item);
			});
		});
		this.state.items.forEach((item) => {
			if (seen.has(item)) return;
			if (!item.folder) item.sequence = 10000 + (Number(item.sequence) || 0);
			next.push(item);
		});
		this.state.categories = categories.length ? categories : ["عمومی"];
		this.state.items = next;
	}

	edit_item(item) {
		const fields = [
			{ fieldname: "custom_label", fieldtype: "Data", label: __("نام نمایشی"), default: item.custom_label || item.label },
			{ fieldname: "category", fieldtype: "Data", label: __("دسته"), default: item.category || "عمومی" },
		];
		if (this.mode === "global") {
			fields.push({
				fieldname: "custom_link",
				fieldtype: "Data",
				label: __("لینک"),
				default: item.custom_link || item.link || (item.link_to ? `/app/${frappe.router.slug(item.link_to)}` : ""),
				description: __("برای حفظ لینک فعلی تغییری ندهید."),
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
			{ fieldname: "hidden", fieldtype: "Check", label: __("مخفی شود"), default: item.hidden }
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

	payload() {
		this.sync_from_dom();
		const data = {
			categories: this.state.categories || [],
			folders: (this.state.folders || []).map((folder) => ({
				folder_name: folder.folder_name,
				category: folder.category || "عمومی",
				sequence: Number(folder.sequence) || 0,
				icon_name: this.mode === "personal" ? "" : (folder.icon_name || ""),
				custom_icon_image: this.mode === "personal" ? "" : (folder.custom_icon_image || ""),
			})),
			items: (this.state.items || []).filter((item) => item.name),
		};
		if (this.mode === "global") {
			for (const field of ["columns", "gap_x", "gap_y"]) {
				const value = Number(this.$root.find(`[data-field=${field}]`).val());
				const minimum = field === "columns" ? 2 : SP_HOME_GAP_MIN;
				const maximum = field === "columns" ? 10 : SP_HOME_GAP_MAX;
				this.state[field] = Number.isFinite(value)
					? Math.max(minimum, Math.min(maximum, Math.trunc(value)))
					: (field === "columns" ? 5 : 8);
			}
			Object.assign(data, {
				enable_custom_styles: this.state.enabled ? 1 : 0,
				apply_to_all_users: this.state.apply_to_all_users ? 1 : 0,
				default_shape: this.state.default_shape,
				default_size: this.state.default_size,
				icon_style: this.state.icon_style,
				gap_x: this.state.gap_x ?? 8,
				gap_y: this.state.gap_y ?? 8,
				columns: this.state.columns ?? 5,
				category_renames: this.category_renames(),
			});
		}
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
		const method = this.mode === "personal"
			? "smartprocee_erpnext_homepage.home_manager.api.save_my_layout"
			: "smartprocee_erpnext_homepage.home_manager.api.save_layout";
		frappe.call({
			method,
			args: { payload: JSON.stringify(this.payload()) },
			freeze: true,
			freeze_message: __("در حال اعمال روی صفحه اصلی..."),
			callback: (r) => {
				this.state = r.message;
				this.remember_categories();
				this.after_save();
			},
		});
	}

	reset_personal() {
		frappe.confirm(__("چیدمان شخصی حذف شود و چیدمان پیش‌فرض مدیر برگردد؟"), () => {
			frappe.call({
				method: "smartprocee_erpnext_homepage.home_manager.api.reset_my_layout",
				freeze: true,
				callback: (r) => {
					this.state = r.message;
					this.remember_categories();
					this.after_save(__("به چیدمان پیش‌فرض بازگشت."));
				},
			});
		});
	}

	after_save(message) {
		try { localStorage.setItem("sp_home_updated", `${Date.now()}`); } catch (_) { /* Optional cross-tab signal. */ }
		frappe.call({
			method: "smartprocee_erpnext_homepage.home_manager.api.get_current_layout",
			callback: (r) => {
				if (frappe.boot && r.message) frappe.boot.sp_home = r.message;
				window.sp_home_apply_layout?.();
			},
		});
		this.render();
		frappe.show_alert({ message: message || __("ذخیره شد."), indicator: "green" });
	}
}

window.SPHomeManager = SPHomeManager;
