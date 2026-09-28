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
		const cells = members.map((item) => {
			const markup = markup_for(item);
			const style = `${markup.background ? `background:${markup.background};` : ""}${markup.stroke ? `--icon-stroke:${markup.stroke};` : ""}`;
			return `<span class="sp-folder-preview-cell ${markup.className || ""}" style="${style}">${markup.html || ""}</span>`;
		}).join("");
		return {
			mode: members.length ? "preview" : "empty",
			className: "is-folder",
			html: `<span class="sp-folder-face"><span class="sp-folder-preview" data-count="${members.length}">${cells}</span></span>`,
		};
	}

	return {
		sp_home_resolve_icon,
		sp_home_icon_markup,
		sp_home_folder_icon_mode,
		sp_home_folder_members,
		sp_home_folder_face,
	};
});
