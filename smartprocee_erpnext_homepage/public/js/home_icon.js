// Measured on the editor: an 84px icon stays inside its card through gap -23 and crosses the card edge at -24.
globalThis.SP_HOME_GAP_MIN = -23;
globalThis.SP_HOME_GAP_MAX = 48;

(function (root, factory) {
	const api = factory();
	if (typeof module === "object" && module.exports) {
		module.exports = api;
	}
	root.sp_home_resolve_icon = api.sp_home_resolve_icon;
	root.sp_home_icon_markup = api.sp_home_icon_markup;
	root.sp_home_folder_icon_mode = api.sp_home_folder_icon_mode;
	root.sp_home_folder_members = api.sp_home_folder_members;
	root.sp_home_folder_face = api.sp_home_folder_face;
	root.sp_home_slot_index = api.sp_home_slot_index;
	root.sp_home_icon_href = api.sp_home_icon_href;
	root.sp_home_link_target = api.sp_home_link_target;
	root.sp_home_effective_items = api.sp_home_effective_items;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
	function sp_home_resolve_icon(item, bundledUrl) {
		item = item || {};
		const label = item.custom_label || item.label || item.name || "";
		if (item.custom_icon_image) {
			return { kind: "image", value: item.custom_icon_image, label, source: "upload" };
		}
		if (item.icon_name) {
			return { kind: "frappe", value: item.icon_name, label, source: "chosen" };
		}
		// Frappe's desktop template draws the bundled SVG and ignores Desktop Icon.icon
		// whenever that file exists. The Lucide sprite uses stroke: var(--icon-stroke),
		// which is dark, so it must not replace the bundled artwork.
		if (bundledUrl) {
			return { kind: "image", value: bundledUrl, label, source: "bundled" };
		}
		if (item.icon) {
			return { kind: "frappe", value: item.icon, label, source: "desktop" };
		}
		if (item.icon_image || item.logo_url) {
			return { kind: "image", value: item.icon_image || item.logo_url, label, source: "upload" };
		}
		const letter = Array.from(label || "؟")[0] || "؟";
		return { kind: "letter", value: letter, label, source: "letter" };
	}

	function escape_html(value) {
		return String(value || "")
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/"/g, "&quot;");
	}

	function normalize_color(value) {
		const match = String(value || "").match(/^#([\da-f]{3}|[\da-f]{6})$/i);
		if (!match) return "";
		const hex = match[1];
		return `#${hex.length === 3 ? hex.split("").map((part) => part + part).join("") : hex}`;
	}

	function sp_home_icon_markup(resolved, options) {
		resolved = resolved || { kind: "letter", value: "؟", label: "" };
		options = options || {};
		const custom = normalize_color(options.customColor);
		if (resolved.kind === "image") {
			return {
				className: "is-image",
				html: `<img class="app-icon" src="${escape_html(resolved.value)}" alt="${escape_html(resolved.label)}">`,
			};
		}
		const iconName = /^[A-Za-z0-9_-]{1,80}$/.test(resolved.value || "") ? resolved.value : "";
		if (resolved.kind === "frappe" && iconName && typeof frappe !== "undefined" && frappe.utils?.icon) {
			return {
				className: "is-frappe",
				html: frappe.utils.icon(iconName, "lg"),
				stroke: custom,
			};
		}
		const palette = (typeof frappe !== "undefined" && frappe.utils?.desktop_pallete) || { blue: "#0289F7" };
		const base = custom || palette.blue || "#0289F7";
		const solid = String(options.iconStyle || "Subtle").toLowerCase() === "solid";
		const background = solid ? base : `${base}1A`;
		const color = solid ? "var(--neutral-white, #fff)" : base;
		const letter = resolved.kind === "letter" ? resolved.value : Array.from(resolved.label || "؟")[0] || "؟";
		return {
			className: "is-letter",
			html: `<span class="sp-home-letter" style="color:${color}">${escape_html(letter)}</span>`,
			background,
		};
	}

	function sp_home_folder_icon_mode(folder) {
		folder = folder || {};
		if (String(folder.custom_icon_image || "").trim()) return "image";
		if (String(folder.icon_name || "").trim()) return "icon";
		return "preview";
	}

	function sp_home_folder_members(folder, items) {
		const name = (folder && folder.folder_name) || "";
		return (items || [])
			.filter((item) => (item.folder || "") === name && !item.hidden && item.icon_type !== "Folder")
			.sort((a, b) => (Number(a.sequence) || 0) - (Number(b.sequence) || 0)
				|| String(a.label || "").localeCompare(String(b.label || ""))
				|| String(a.name || "").localeCompare(String(b.name || "")))
			.slice(0, 4);
	}

	function sp_home_folder_face(folder, items, options) {
		folder = folder || {};
		options = options || {};
		const resolve = options.resolve || ((item) => sp_home_resolve_icon(item, options.bundledUrl || ""));
		const markup_for = (item) => sp_home_icon_markup(resolve(item), {
			iconStyle: options.iconStyle,
			customColor: item.custom_color,
		});
		const mode = sp_home_folder_icon_mode(folder);
		if (mode !== "preview") {
			const markup = markup_for({
				label: folder.folder_name,
				custom_label: folder.folder_name,
				custom_icon_image: folder.custom_icon_image,
				icon_name: folder.icon_name,
			});
			return Object.assign({ mode }, markup);
		}
		const members = sp_home_folder_members(folder, items);
		if (!members.length) {
			const glyph = typeof frappe !== "undefined" && frappe.utils?.icon ? frappe.utils.icon("folder", "lg") : "";
			return {
				mode: "empty",
				className: "is-folder",
				html: `<span class="sp-folder-face is-empty">${glyph}</span>`,
			};
		}
		const cells = members.map((item) => {
			const markup = markup_for(item);
			const style = `${markup.background ? `background:${markup.background};` : ""}${markup.stroke ? `--icon-stroke:${markup.stroke};` : ""}`;
			return `<span class="sp-folder-preview-cell ${markup.className || ""}" style="${style}">${markup.html || ""}</span>`;
		}).join("");
		return {
			mode: "preview",
			className: "is-folder",
			html: `<span class="sp-folder-face"><span class="sp-folder-preview" data-count="${members.length}">${cells}</span></span>`,
		};
	}

	function sp_home_insertion_index(cards, pointer, rtl) {
		const list = cards || [];
		if (!list.length) return 0;
		const x = pointer.x;
		const y = pointer.y;
		const rows = [];
		list.forEach((card, index) => {
			const previous = rows.length ? rows[rows.length - 1][0].card : null;
			const split = !previous || Math.abs(card.top - previous.top) > Math.max(card.height, previous.height) * 0.45;
			if (split) rows.push([]);
			rows[rows.length - 1].push({ index, card });
		});
		const bounds = rows.map((row) => {
			const top = Math.min(...row.map((entry) => entry.card.top));
			const bottom = Math.max(...row.map((entry) => entry.card.top + entry.card.height));
			return { top, bottom };
		});
		let chosen = 0;
		for (let i = 0; i < rows.length; i++) {
			const above = i === 0 ? Number.NEGATIVE_INFINITY : (bounds[i - 1].bottom + bounds[i].top) / 2;
			const below = i === rows.length - 1 ? Number.POSITIVE_INFINITY : (bounds[i].bottom + bounds[i + 1].top) / 2;
			if (y >= above && y < below) {
				chosen = i;
				break;
			}
		}
		const row = rows[chosen];
		const centers = row.map((entry) => entry.card.left + entry.card.width / 2);
		const start = row[0].index;
		if (rtl !== false) {
			if (x >= centers[0]) return start;
			if (x <= centers[centers.length - 1]) return row[row.length - 1].index + 1;
			for (let i = 0; i < centers.length - 1; i++) {
				if (centers[i] >= x && x >= centers[i + 1]) return row[i].index + 1;
			}
			return row[row.length - 1].index + 1;
		}
		if (x <= centers[0]) return start;
		if (x >= centers[centers.length - 1]) return row[row.length - 1].index + 1;
		for (let i = 0; i < centers.length - 1; i++) {
			if (centers[i] <= x && x <= centers[i + 1]) return row[i].index + 1;
		}
		return row[row.length - 1].index + 1;
	}

	// `rects` is the visible row as drawn, including the slot at `slotAt` (-1 when the
	// slot is in another grid). The result indexes the cards without the slot, so the
	// hit test always runs on the layout the user sees.
	function sp_home_slot_index(rects, slotAt, pointer, rtl) {
		const index = sp_home_insertion_index(rects, pointer, rtl);
		return slotAt >= 0 && index > slotAt ? index - 1 : index;
	}

	// A Desktop Icon link comes from Frappe's own resolver (Workspace Sidebar, Report,
	// URL, External). Guessing /app/<link_to> breaks icons such as "System", whose
	// sidebar has no page or workspace with that name.
	function sp_home_icon_href(item, nativeIcon, routeForIcon) {
		item = item || {};
		if (item.custom_link) return item.custom_link;
		const icon = nativeIcon || item;
		if (typeof routeForIcon === "function" && icon.label) {
			try {
				const route = routeForIcon(icon);
				if (route) return route;
			} catch (_) { /* Frappe could not resolve this icon. */ }
		}
		if (icon.link_type === "External" && icon.link) return icon.link;
		return "";
	}

	// Native Frappe keeps Desk routes in the current tab; only a URL on another origin opens a new one.
	function sp_home_link_target(href, origin) {
		if (!/^https?:\/\//i.test(href || "")) return "";
		try {
			return new URL(href).origin === origin ? "" : "_blank";
		} catch (_) {
			return "_blank";
		}
	}

	// Frappe hides a Desktop Icon it cannot route (for example an empty sidebar). Folders and
	// icons that the native grid still draws keep their own behaviour.
	function sp_home_effective_items(items, hrefFor, nativeShown) {
		return (items || []).filter(
			(item) => item.icon_type === "Folder" || (nativeShown && nativeShown(item)) || !!hrefFor(item)
		);
	}

	return {
		sp_home_resolve_icon,
		sp_home_icon_markup,
		sp_home_folder_icon_mode,
		sp_home_folder_members,
		sp_home_folder_face,
		sp_home_insertion_index,
		sp_home_slot_index,
		sp_home_icon_href,
		sp_home_link_target,
		sp_home_effective_items,
	};
});
