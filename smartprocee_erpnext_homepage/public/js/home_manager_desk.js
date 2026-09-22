(() => {
	const SP_HOME_VERSION = "14";
	try {
		if (localStorage.getItem("sp_home_version") !== SP_HOME_VERSION) {
			localStorage.removeItem("_page:home-manager");
			localStorage.setItem("sp_home_version", SP_HOME_VERSION);
		}
	} catch (_) { /* Storage is optional. */ }
	let observer, queued = false, applying = false;
	const originals = new WeakMap(), nativeLayouts = new WeakMap();
	const has_manager_role = () => (frappe.user_roles || frappe.boot?.user?.roles || []).includes("System Manager") || frappe.session?.user === "Administrator";
	const enabled = layout => Number(layout.enabled) && (Number(layout.apply_to_all_users) || has_manager_role());
	const clamp = (value, min, max, fallback) => Number.isFinite(Number(value)) && value !== null && value !== "" ? Math.max(min, Math.min(max, Math.trunc(Number(value)))) : fallback;
	const observe = () => observer?.observe(document.body, { childList: true, subtree: true });
	const clear_sections = grid => {
		grid.querySelectorAll(":scope > .sp-home-section").forEach(section => {
			section.querySelectorAll(":scope > .desktop-icon").forEach(icon => grid.insertBefore(icon, section));
			section.remove();
		});
	};
	// Merge only icons authorized by Frappe. Keep native folders and user layout.
	const sync_visibility = layout => {
		const page = frappe.pages?.desktop?.desktop_page;
		if (page?.edit_mode) { nativeLayouts.delete(page); return; }
		if (!page || !Array.isArray(frappe.desktop_icons)) return;
		if (!nativeLayouts.has(page)) nativeLayouts.set(page, frappe.desktop_icons.map(icon => ({ ...icon })));
		const base = nativeLayouts.get(page).map(icon => ({ ...icon }));
		if (enabled(layout)) {
			const names = new Set(base.map(icon => icon.name || icon.label));
			(frappe.boot.desktop_icons || []).forEach(icon => {
				if (!names.has(icon.name || icon.label)) base.push({ ...icon });
			});
			const settings = new Map((layout.items || []).flatMap(item => [[item.name, item], [item.label, item]]));
			base.forEach(icon => {
				const item = settings.get(icon.name) || settings.get(icon.label);
				if (icon.icon_type === "Folder") icon.hidden = 1;
				if (item) {
					icon.hidden = Number(item.hidden) ? 1 : 0;
					// Render the same flat list as the settings page without changing Desktop Icon records.
					icon.parent_icon = "";
				}
			});
		}
		const signature = icons => JSON.stringify(icons.map(icon => [icon.name || icon.label, Number(icon.hidden) || 0, icon.parent_icon || ""]));
		if (signature(base) !== signature(frappe.desktop_icons)) { page.data = base; page.update(); }
	};
	const remember = el => {
		if (originals.has(el)) return;
		const box = el.querySelector(":scope > .icon-container");
		originals.set(el, { src: box?.querySelector(":scope > img")?.getAttribute("src"), caption: el.querySelector(":scope > .icon-caption")?.innerHTML });
	};
	const restore = el => {
		const original = originals.get(el);
		if (!original) return;
		const img = el.querySelector(":scope > .icon-container > img");
		if (img && original.src) img.setAttribute("src", original.src);
		const caption = el.querySelector(":scope > .icon-caption");
		if (caption && original.caption !== undefined) caption.innerHTML = original.caption;
		el.classList.remove("sp-home-icon");
		el.querySelector(":scope > .icon-container > .sp-home-letter")?.remove();
		["spShape", "spSize", "spStyle"].forEach(key => delete el.dataset[key]);
		el.style.removeProperty("--sp-home-color");
	};
	const apply_icon_style = (el, item, layout) => {
		remember(el);
		el.classList.add("sp-home-icon");
		const custom = Number(item.use_custom_style);
		el.dataset.spShape = (custom && item.shape) || layout.default_shape || "rounded";
		el.dataset.spSize = (custom && item.size) || layout.default_size || "medium";
		el.dataset.spStyle = layout.icon_style || "Solid";
		const img = el.querySelector(":scope > .icon-container > img.app-icon");
		const box = el.querySelector(":scope > .icon-container");
		if (img && item.icon_type !== "Folder") {
			const url = frappe.utils.get_desktop_icon?.(item.label || item.name, (layout.icon_style || "Solid").toLowerCase());
			if (url && img.getAttribute("src") !== url) img.setAttribute("src", url);
		}
		if (/^#[\da-f]{3}([\da-f]{3})?$/i.test(item.custom_color || "")) el.style.setProperty("--sp-home-color", item.custom_color);
		else el.style.removeProperty("--sp-home-color");
		const caption = el.querySelector(":scope > .icon-caption > .icon-title");
		const label = __(item.custom_label || item.label || el.dataset.id);
		if (box?.querySelector(":scope > svg.desktop-alphabet")) {
			let letter = box.querySelector(".sp-home-letter");
			if (!letter) { letter = document.createElement("span"); letter.className = "sp-home-letter"; box.append(letter); }
			letter.textContent = label.slice(0, 1);
		}
		if (caption) {
			if (caption.textContent !== label) caption.textContent = label;
			caption.setAttribute("title", label);
			caption.setAttribute("data-original-title", label);
		}
		if (img) img.alt = label;
		el.setAttribute("aria-label", label);
		if (item.link === "/app/home-manager" || item.name === "مدیریت صفحه اصلی") {
			el.target = "_blank";
			el.rel = "noopener";
		}
	};
	const add_runtime_icons = (grid, layout) => {
		const existing = new Set([...grid.querySelectorAll(":scope > a.desktop-icon")].map(el => el.dataset.id));
		const template = grid.querySelector(":scope > a.desktop-icon");
		if (!template) return;
		(layout.items || []).filter(item => !Number(item.hidden) && !existing.has(item.name)).forEach(item => {
			const el = template.cloneNode(true);
			const label = __(item.custom_label || item.label || item.name);
			el.dataset.id = item.name;
			el.dataset.spRuntime = "1";
			el.href = item.link || (item.link_to ? `/app/${frappe.router.slug(item.link_to)}` : "#");
			const box = el.querySelector(":scope > .icon-container");
			if (box) box.innerHTML = `<span class="sp-home-letter">${frappe.utils.escape_html(label.slice(0, 1))}</span>`;
			const title = el.querySelector(":scope > .icon-caption > .icon-title");
			if (title) title.textContent = label;
			if (!item.link && !item.link_to) el.addEventListener("click", event => event.preventDefault());
			grid.append(el);
			existing.add(item.name);
		});
	};
	const apply_home_layout = () => {
		if (applying) return false;
		document.querySelectorAll('a[href*="/sp-home-settings/"] .sidebar-item-label').forEach(el => { if (el.textContent !== "تنظیمات صفحه اصلی") el.textContent = "تنظیمات صفحه اصلی"; });
		const layout = frappe.boot?.sp_home || {};
		let container = document.querySelector(".desktop-container");
		if (!container) return false;
		if (container.getClientRects().length) document.title = "صفحه اصلی";
		document.querySelectorAll('.desktop-search-wrapper [title="Search"], #desktop-navbar-modal-search[title="Search"]').forEach(el => el.title = "جستجو");
		applying = true;
		observer?.disconnect();
		try {
			sync_visibility(layout);
			container = document.querySelector(".desktop-container");
			const grid = container?.querySelector(":scope > .icons-container > .icons");
			if (!grid) return false;
			const active = enabled(layout) && !frappe.pages?.desktop?.desktop_page?.edit_mode;
			clear_sections(grid);
			grid.querySelectorAll(':scope > [data-sp-runtime="1"]').forEach(el => el.remove());
			container.classList.toggle("sp-home-enabled", !!active);
			grid.classList.toggle("sp-home-grid", !!active);
			if (!active) {
				document.querySelectorAll(".sp-home-icon").forEach(restore);
				document.querySelectorAll(".sp-home-modal-grid").forEach(el => el.classList.remove("sp-home-modal-grid"));
				document.querySelectorAll(".sp-home-manage-btn").forEach(el => el.remove());
				return true;
			}
			container.style.setProperty("--sp-gap-x", `${clamp(layout.gap_x, -50, 100, 8)}px`);
			container.style.setProperty("--sp-gap-y", `${clamp(layout.gap_y, -50, 100, 8)}px`);
			container.style.setProperty("--sp-cols", clamp(layout.columns, 2, 10, 5));
			const items = new Map((layout.items || []).flatMap(item => [[item.name, item], [item.label, item]]));
			add_runtime_icons(grid, layout);
			// All configured icons are top-level runtime copies, matching the settings preview.
			const icons = [...grid.querySelectorAll(":scope > a.desktop-icon")];
			const groups = new Map();
			icons.sort((a, b) => (items.get(a.dataset.id)?.sequence || 0) - (items.get(b.dataset.id)?.sequence || 0));
			icons.forEach(el => {
				const item = items.get(el.dataset.id) || { label: el.dataset.id };
				apply_icon_style(el, item, layout);
				const category = __(item.category || "عمومی");
				if (!groups.has(category)) groups.set(category, []);
				groups.get(category).push(el);
			});
			const categoryOrder = [...new Set((layout.items || []).map(item => __(item.category || "عمومی")))];
			[...groups].sort((a, b) => categoryOrder.indexOf(a[0]) - categoryOrder.indexOf(b[0])).forEach(([category, members]) => {
				const section = document.createElement("section");
				section.className = "sp-home-section";
				const heading = document.createElement("h2");
				heading.className = "sp-home-section-title";
				heading.textContent = category;
				members.forEach((member, index) => {
					member.style.setProperty("--sp-col", index % clamp(layout.columns, 2, 10, 5));
					member.style.setProperty("--sp-row", Math.floor(index / clamp(layout.columns, 2, 10, 5)));
				});
				section.append(heading, ...members);
				grid.append(section);
			});
			container.querySelectorAll(".folder-icon img").forEach(img => { img.alt = __(img.alt); });
			document.querySelectorAll(".desktop-modal-body > .icons-container > .icons").forEach(modalGrid => {
				modalGrid.classList.add("sp-home-modal-grid");
				modalGrid.style.setProperty("--sp-cols", clamp(layout.columns, 2, 10, 5));
				modalGrid.style.setProperty("--sp-gap-x", `${clamp(layout.gap_x, -50, 100, 8)}px`);
				modalGrid.style.setProperty("--sp-gap-y", `${clamp(layout.gap_y, -50, 100, 8)}px`);
				modalGrid.querySelectorAll(":scope > .desktop-icon").forEach(el => apply_icon_style(el, items.get(el.dataset.id) || {label: el.dataset.id}, layout));
			});
			if (has_manager_role() && !document.querySelector(".sp-home-manage-btn")) $("<a class='sp-home-manage-btn' href='/app/home-manager' target='_blank' rel='noopener' title='مدیریت صفحه اصلی' aria-label='مدیریت صفحه اصلی'><svg viewBox='0 0 24 24' aria-hidden='true'><path fill='currentColor' d='M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.62l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96a7.1 7.1 0 0 0-1.62-.94L14.4 2.8a.48.48 0 0 0-.48-.4h-3.84a.48.48 0 0 0-.48.4l-.36 2.54c-.58.24-1.12.56-1.62.94l-2.39-.96a.48.48 0 0 0-.59.22L2.72 8.86a.48.48 0 0 0 .12.62l2.03 1.58c-.05.31-.08.64-.08.94s.03.63.08.94l-2.03 1.58a.49.49 0 0 0-.12.62l1.92 3.32c.12.22.38.31.59.22l2.39-.96c.5.38 1.04.7 1.62.94l.36 2.54c.04.23.24.4.48.4h3.84c.24 0 .44-.17.48-.4l.36-2.54c.58-.24 1.12-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.49.49 0 0 0-.12-.62l-2.02-1.58ZM12 15.6a3.6 3.6 0 1 1 0-7.2 3.6 3.6 0 0 1 0 7.2Z'/></svg></a>").appendTo(container.closest(".desktop-wrapper"));
			return true;
		} finally { applying = false; observe(); }
	};
	const schedule_apply = () => {
		if (queued || applying) return;
		queued = true;
		requestAnimationFrame(() => { queued = false; apply_home_layout(); });
	};
	const bind = () => {
		if (observer) return;
		// The desktop container itself is replaced on route changes.
		observer = new MutationObserver(records => {
			if (records.some(record => [...record.addedNodes, ...record.removedNodes].some(node => node.nodeType === 1 && (node.matches?.(".desktop-container, .icons-container, .icons, .desktop-icon") || node.querySelector?.(".desktop-container, .desktop-icon"))))) schedule_apply();
		});
		observe();
		$(document).on("desktop_screen.sp_home", schedule_apply);
		$(document).on("mouseenter.sp_home focusin.sp_home", "#desktop-navbar-modal-search", function () { this.title = "جستجو"; });
		frappe.realtime?.on("sp_home_layout_updated", layout => { frappe.boot.sp_home = layout; schedule_apply(); });
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
			} catch (_) { /* Reconnect/focus will retry; keep the last usable layout. */ }
			finally { fetching = false; }
		};
		window.addEventListener("storage", event => { if (event.key === "sp_home_updated") refresh(); });
		window.addEventListener("focus", refresh);
		frappe.router?.on("change", schedule_apply);
		document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
		// Network fallback only, not a render timer. Unchanged data never rebuilds DOM.
		setInterval(() => { if (!frappe.realtime?.socket?.connected) refresh(); }, 15000);
		schedule_apply();
	};
	$(bind);
	window.sp_home_apply_layout = apply_home_layout;
})();
