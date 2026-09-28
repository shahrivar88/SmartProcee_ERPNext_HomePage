(() => {
	const SP_HOME_VERSION = "24";
	try {
		if (localStorage.getItem("sp_home_version") !== SP_HOME_VERSION) {
			localStorage.removeItem("_page:home-manager");
			localStorage.removeItem("_page:home-personalize");
			localStorage.setItem("sp_home_version", SP_HOME_VERSION);
		}
	} catch (_) { /* Storage is optional. */ }

	let observer, queued = false, applying = false;
	const originals = new WeakMap();
	const has_manager_role = () => (frappe.user_roles || frappe.boot?.user?.roles || []).includes("System Manager") || frappe.session?.user === "Administrator";
	const clamp = (value, min, max, fallback) => Number.isFinite(Number(value)) && value !== null && value !== "" ? Math.max(min, Math.min(max, Math.trunc(Number(value)))) : fallback;
	const observe = () => observer?.observe(document.body, { childList: true, subtree: true });

	const clear_sections = (grid) => {
		grid.querySelectorAll(":scope > .sp-home-section").forEach((section) => {
			section.querySelectorAll(":scope > .desktop-icon").forEach((icon) => {
				if (icon.classList.contains("sp-home-folder-icon")) icon.remove();
				else grid.insertBefore(icon, section);
			});
			section.remove();
		});
		grid.querySelectorAll(":scope > .sp-home-folder-icon").forEach((icon) => icon.remove());
	};

	const remember = (el) => {
		if (originals.has(el)) return;
		const box = el.querySelector(":scope > .icon-container");
		originals.set(el, {
			html: box ? box.innerHTML : "",
			href: el.getAttribute("href"),
			caption: el.querySelector(":scope > .icon-caption")?.innerHTML,
		});
	};

	const restore = (el) => {
		const original = originals.get(el);
		if (!original) return;
		const box = el.querySelector(":scope > .icon-container");
		if (box) {
			box.innerHTML = original.html;
			box.classList.remove("is-image", "is-frappe", "is-letter");
			box.style.background = "";
			box.style.removeProperty("--icon-stroke");
		}
		if (original.href) el.setAttribute("href", original.href);
		else el.removeAttribute("href");
		const caption = el.querySelector(":scope > .icon-caption");
		if (caption && original.caption !== undefined) caption.innerHTML = original.caption;
		el.classList.remove("sp-home-icon", "sp-home-suppressed");
		["spShape", "spSize", "spStyle"].forEach((key) => delete el.dataset[key]);
		el.style.removeProperty("--sp-home-color");
	};

	const native_folder_ids = () => new Set(
		(frappe.boot?.desktop_icons || [])
			.filter((icon) => icon.icon_type === "Folder")
			.flatMap((icon) => [icon.label, icon.name].filter(Boolean))
	);

	const paint_box = (box, item, layout) => {
		if (!box) return;
		const bundled = frappe.utils.get_desktop_icon?.(item.label || item.name, (layout.icon_style || "Solid").toLowerCase());
		const resolved = (window.sp_home_resolve_icon || (() => ({ kind: "letter", value: "؟", label: "" })))(item, bundled);
		const markup = (window.sp_home_icon_markup || (() => ({ className: "is-letter", html: "" })))(resolved, {
			iconStyle: layout.icon_style,
			customColor: item.custom_color,
		});
		box.classList.remove("is-image", "is-frappe", "is-letter");
		box.classList.add(markup.className || "is-letter");
		box.replaceChildren();
		if (markup.html) box.insertAdjacentHTML("beforeend", markup.html);
		box.style.background = markup.background || "";
		if (markup.stroke) box.style.setProperty("--icon-stroke", markup.stroke);
		else box.style.removeProperty("--icon-stroke");
	};

	const paint_icon = (el, item, layout) => {
		remember(el);
		el.classList.add("sp-home-icon");
		el.classList.remove("sp-home-suppressed");
		el.dataset.spShape = item.shape || layout.default_shape || "rounded";
		el.dataset.spSize = item.size || layout.default_size || "medium";
		el.dataset.spStyle = layout.icon_style || "Solid";
		paint_box(el.querySelector(":scope > .icon-container"), item, layout);
		if (item.custom_link) el.setAttribute("href", item.custom_link);
		el.target = "_blank";
		el.rel = "noopener";
		if (/^#[\da-f]{3}([\da-f]{3})?$/i.test(item.custom_color || "")) el.style.setProperty("--sp-home-color", item.custom_color);
		else el.style.removeProperty("--sp-home-color");
		const caption = el.querySelector(":scope > .icon-caption > .icon-title");
		const label = __(item.custom_label || item.label || el.dataset.id);
		if (caption) {
			if (caption.textContent !== label) caption.textContent = label;
			caption.setAttribute("title", label);
			caption.setAttribute("data-original-title", label);
		}
		el.setAttribute("aria-label", label);
	};

	const make_folder_button = (folder, layout) => {
		const button = document.createElement("button");
		button.type = "button";
		button.className = "desktop-icon sp-home-icon sp-home-folder-icon";
		button.dataset.spFolder = folder.folder_name;
		button.dataset.spShape = layout.default_shape || "rounded";
		button.dataset.spSize = layout.default_size || "medium";
		button.dataset.spStyle = layout.icon_style || "Solid";
		const box = document.createElement("div");
		box.className = "icon-container";
		const caption = document.createElement("div");
		caption.className = "icon-caption";
		caption.innerHTML = `<div class="icon-title"></div>`;
		button.append(box, caption);
		const face = (window.sp_home_folder_face || (() => ({ className: "is-letter", html: "" })))(folder, layout.items || [], {
			iconStyle: layout.icon_style,
			resolve: (item) => (window.sp_home_resolve_icon || (() => ({ kind: "letter", value: "؟", label: "" })))(
				item,
				frappe.utils.get_desktop_icon?.(item.label || item.name, (layout.icon_style || "Solid").toLowerCase())
			),
		});
		box.classList.add(face.className || "is-letter");
		if (face.background) box.style.background = face.background;
		if (face.stroke) box.style.setProperty("--icon-stroke", face.stroke);
		box.innerHTML = face.html || "";
		const title = caption.querySelector(".icon-title");
		const label = __(folder.folder_name);
		if (title) title.textContent = label;
		button.setAttribute("aria-label", label);
		button.addEventListener("click", (event) => {
			event.preventDefault();
			event.stopPropagation();
			open_folder(folder, layout);
		});
		return button;
	};

	const open_folder = (folder, layout) => {
		const members = (layout.items || []).filter((item) => item.folder === folder.folder_name && !item.hidden);
		const dialog = new frappe.ui.Dialog({ title: __(folder.folder_name), size: "large" });
		const grid = document.createElement("div");
		grid.className = "sp-home-modal-grid";
		grid.style.setProperty("--sp-cols", clamp(layout.columns, 2, 10, 5));
		grid.style.setProperty("--sp-tile", "148px");
		grid.style.setProperty("--sp-gap-x", `${clamp(layout.gap_x, window.SP_HOME_GAP_MIN, window.SP_HOME_GAP_MAX, 8)}px`);
		grid.style.setProperty("--sp-gap-y", `${clamp(layout.gap_y, window.SP_HOME_GAP_MIN, window.SP_HOME_GAP_MAX, 8)}px`);
		members.forEach((item) => {
			const el = document.createElement("a");
			el.className = "desktop-icon sp-home-icon";
			const href = item.custom_link || item.link || (item.link_to ? `/app/${frappe.router.slug(item.link_to)}` : "");
			if (href) {
				el.href = href;
				el.target = "_blank";
				el.rel = "noopener";
			}
			const box = document.createElement("div");
			box.className = "icon-container";
			const caption = document.createElement("div");
			caption.className = "icon-caption";
			caption.innerHTML = `<div class="icon-title"></div>`;
			el.append(box, caption);
			paint_icon(el, item, layout);
			grid.append(el);
		});
		dialog.$body.empty().append(grid);
		dialog.show();
	};

	const make_runtime_icon = (template, item) => {
		const el = template.cloneNode(true);
		const label = __(item.custom_label || item.label || item.name);
		el.dataset.id = item.label || item.name;
		el.dataset.spRuntime = "1";
		el.href = item.custom_link || item.link || (item.link_to ? `/app/${frappe.router.slug(item.link_to)}` : "#");
		el.target = "_blank";
		el.rel = "noopener";
		const box = el.querySelector(":scope > .icon-container");
		if (box) box.replaceChildren();
		const title = el.querySelector(":scope > .icon-caption > .icon-title");
		if (title) title.textContent = label;
		if (!item.link && !item.link_to && !item.custom_link) el.addEventListener("click", (event) => event.preventDefault());
		return el;
	};

	const apply_home_layout = () => {
		if (applying) return false;
		document.querySelectorAll('a[href*="/sp-home-settings/"] .sidebar-item-label').forEach((el) => {
			if (el.textContent !== "تنظیمات صفحه اصلی") el.textContent = "تنظیمات صفحه اصلی";
		});
		const layout = frappe.boot?.sp_home || {};
		let container = document.querySelector(".desktop-container");
		if (!container) return false;
		if (container.getClientRects().length) document.title = "صفحه اصلی";
		document.querySelectorAll('.desktop-search-wrapper [title="Search"], #desktop-navbar-modal-search[title="Search"]').forEach((el) => { el.title = "جستجو"; });
		applying = true;
		observer?.disconnect();
		try {
			container = document.querySelector(".desktop-container");
			const grid = container?.querySelector(":scope > .icons-container > .icons");
			if (!grid) return false;
			const edit_mode = !!frappe.pages?.desktop?.desktop_page?.edit_mode;
			const active = Number(layout.active) && !edit_mode;
			clear_sections(grid);
			grid.querySelectorAll(':scope > [data-sp-runtime="1"]').forEach((el) => el.remove());
			grid.querySelectorAll(".sp-home-suppressed").forEach((el) => el.classList.remove("sp-home-suppressed"));
			container.classList.toggle("sp-home-enabled", !!active);
			grid.classList.toggle("sp-home-grid", !!active);
			if (!active) {
				grid.querySelectorAll(".sp-home-icon").forEach(restore);
				document.querySelectorAll(".sp-home-modal-grid").forEach((el) => el.classList.remove("sp-home-modal-grid"));
				document.querySelectorAll(".sp-home-manage-btn, .sp-home-personal-btn").forEach((el) => el.remove());
				grid.style.removeProperty("display");
				return true;
			}
			container.style.setProperty("--sp-gap-x", `${clamp(layout.gap_x, window.SP_HOME_GAP_MIN, window.SP_HOME_GAP_MAX, 8)}px`);
			container.style.setProperty("--sp-gap-y", `${clamp(layout.gap_y, window.SP_HOME_GAP_MIN, window.SP_HOME_GAP_MAX, 8)}px`);
			container.style.setProperty("--sp-cols", clamp(layout.columns, 2, 10, 5));
			const folders = native_folder_ids();
			const items = new Map((layout.items || []).filter((item) => item.icon_type !== "Folder").flatMap((item) => [[item.name, item], [item.label, item]]));
			const direct = new Map([...grid.querySelectorAll(":scope > a.desktop-icon")].map((el) => [el.dataset.id, el]));
			const template = grid.querySelector(":scope > a.desktop-icon");
			const claimed = new Set();
			const groups = new Map((layout.categories || []).map((category) => [category, []]));
			const place = (category, sequence, node) => {
				if (!groups.has(category)) groups.set(category, []);
				groups.get(category).push({ sequence: Number(sequence) || 0, node });
			};
			(layout.items || []).forEach((item) => {
				if (item.icon_type === "Folder" || folders.has(item.label) || folders.has(item.name) || item.folder) return;
				const category = item.category || "عمومی";
				let el = direct.get(item.label) || direct.get(item.name);
				if (el) claimed.add(el);
				else if (template) el = make_runtime_icon(template, item);
				if (!el) return;
				paint_icon(el, item, layout);
				place(category, item.sequence, el);
			});
			(layout.folders || []).forEach((folder) => {
				place(folder.category || "عمومی", folder.sequence, make_folder_button(folder, layout));
			});
			direct.forEach((el) => {
				if (!claimed.has(el) || folders.has(el.dataset.id)) {
					el.classList.add("sp-home-suppressed");
					el.classList.remove("sp-home-icon");
				}
			});
			groups.forEach((members, category) => {
				const section = document.createElement("section");
				section.className = "sp-home-section";
				const heading = document.createElement("h2");
				heading.className = "sp-home-section-title";
				heading.textContent = __(category);
				members.sort((a, b) => a.sequence - b.sequence);
				section.append(heading, ...members.map((entry) => entry.node));
				grid.append(section);
			});
			container.querySelectorAll(".folder-icon img").forEach((img) => { img.alt = __(img.alt); });
			document.querySelectorAll(".desktop-modal-body > .icons-container > .icons").forEach((modalGrid) => {
				modalGrid.classList.add("sp-home-modal-grid");
				modalGrid.style.setProperty("--sp-cols", clamp(layout.columns, 2, 10, 5));
				modalGrid.style.setProperty("--sp-gap-x", `${clamp(layout.gap_x, window.SP_HOME_GAP_MIN, window.SP_HOME_GAP_MAX, 8)}px`);
				modalGrid.style.setProperty("--sp-gap-y", `${clamp(layout.gap_y, window.SP_HOME_GAP_MIN, window.SP_HOME_GAP_MAX, 8)}px`);
				modalGrid.querySelectorAll(":scope > .desktop-icon").forEach((el) => paint_icon(el, items.get(el.dataset.id) || { label: el.dataset.id }, layout));
			});
			const wrapper = container.closest(".desktop-wrapper") || container;
			if (!document.querySelector(".sp-home-personal-btn")) {
				$("<a class='sp-home-personal-btn' href='/app/home-personalize' title='چیدمان من' aria-label='چیدمان من'>چیدمان من</a>").appendTo(wrapper);
			}
			if (has_manager_role() && !document.querySelector(".sp-home-manage-btn")) {
				$("<a class='sp-home-manage-btn' href='/app/home-manager' title='مدیریت صفحه اصلی' aria-label='مدیریت صفحه اصلی'><svg viewBox='0 0 24 24' aria-hidden='true'><path fill='currentColor' d='M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.62l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96a7.1 7.1 0 0 0-1.62-.94L14.4 2.8a.48.48 0 0 0-.48-.4h-3.84a.48.48 0 0 0-.48.4l-.36 2.54c-.58.24-1.12.56-1.62.94l-2.39-.96a.48.48 0 0 0-.59.22L2.72 8.86a.48.48 0 0 0 .12.62l2.03 1.58c-.05.31-.08.64-.08.94s.03.63.08.94l-2.03 1.58a.49.49 0 0 0-.12.62l1.92 3.32c.12.22.38.31.59.22l2.39-.96c.5.38 1.04.7 1.62.94l.36 2.54c.04.23.24.4.48.4h3.84c.24 0 .44-.17.48-.4l.36-2.54c.58-.24 1.12-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.49.49 0 0 0-.12-.62l-2.02-1.58ZM12 15.6a3.6 3.6 0 1 1 0-7.2 3.6 3.6 0 0 1 0 7.2Z'/></svg></a>").appendTo(wrapper);
			}
			return true;
		} finally {
			applying = false;
			observe();
		}
	};

	const schedule_apply = () => {
		if (queued || applying) return;
		queued = true;
		requestAnimationFrame(() => { queued = false; apply_home_layout(); });
	};

	const bind = () => {
		if (observer) return;
		observer = new MutationObserver((records) => {
			if (records.some((record) => [...record.addedNodes, ...record.removedNodes].some((node) => node.nodeType === 1 && (node.matches?.(".desktop-container, .icons-container, .icons, .desktop-icon") || node.querySelector?.(".desktop-container, .desktop-icon"))))) schedule_apply();
		});
		observe();
		$(document).on("desktop_screen.sp_home", schedule_apply);
		$(document).on("mouseenter.sp_home focusin.sp_home", "#desktop-navbar-modal-search", function () { this.title = "جستجو"; });
		frappe.realtime?.on("sp_home_layout_updated", () => { refresh(); });
		let fetching = false;
		const refresh = async () => {
			if (fetching || document.hidden || !navigator.onLine) return;
			fetching = true;
			try {
				const response = await frappe.call({ method: "smartprocee_erpnext_homepage.home_manager.api.get_current_layout" });
				if (response.message && JSON.stringify(response.message) !== JSON.stringify(frappe.boot.sp_home)) {
					frappe.boot.sp_home = response.message;
					schedule_apply();
				}
			} catch (_) { /* Keep the last usable layout. */ }
			finally { fetching = false; }
		};
		window.addEventListener("storage", (event) => { if (event.key === "sp_home_updated") refresh(); });
		window.addEventListener("focus", refresh);
		frappe.router?.on("change", schedule_apply);
		document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
		setInterval(() => { if (!frappe.realtime?.socket?.connected) refresh(); }, 15000);
		schedule_apply();
	};
	$(bind);
	window.sp_home_apply_layout = apply_home_layout;
})();
