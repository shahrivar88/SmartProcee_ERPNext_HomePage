"""Persian presentation labels; database identifiers and routes stay unchanged."""

LABELS = {
    "Home Manager": "مدیریت صفحه اصلی", "SP Home Settings": "تنظیمات صفحه اصلی",
    "SP Home Style": "ظاهر آیکون", "Desktop": "صفحه اصلی", "Home": "خانه",
    "Framework": "چارچوب فراپه", "ERPNext": "سامانه برنامه‌ریزی منابع",
    "ERPNext Settings": "تنظیمات سامانه", "Accounting": "حسابداری",
    "Buying": "خرید", "Banking": "بانکداری", "Stock": "انبار",
    "Invoicing": "صورتحساب‌ها", "Payments": "پرداخت‌ها", "Taxes": "مالیات",
    "Financial Reports": "گزارش‌های مالی", "Accounts Setup": "تنظیمات حساب‌ها",
    "Budget": "بودجه", "Subcontracting": "پیمانکاری فرعی", "System": "سیستم",
    "Users": "کاربران", "Data": "داده‌ها", "Build": "ساخت و توسعه",
    "Automation": "خودکارسازی", "Email": "ایمیل", "Integrations": "یکپارچه‌سازی‌ها",
    "Organization": "سازمان", "Printing": "چاپ", "Website": "وب‌سایت",
    "Assets": "دارایی‌ها", "CRM": "مدیریت ارتباط با مشتری",
    "Manufacturing": "تولید", "Projects": "پروژه‌ها", "Quality": "کیفیت",
    "Selling": "فروش", "Support": "پشتیبانی", "Share Management": "مدیریت سهام",
    "Subscription": "اشتراک‌ها", "My Workspaces": "فضاهای کاری من",
    "rounded": "گوشه‌گرد", "circle": "دایره", "square": "مربع",
    "small": "کوچک", "medium": "متوسط", "large": "بزرگ",
    "Solid": "پررنگ", "Subtle": "ملایم", "Edit Layout": "ویرایش چیدمان",
    "Reset Layout": "بازنشانی چیدمان", "Edit Profile": "ویرایش نمایه",
    "Toggle Theme": "تغییر پوسته", "About": "درباره سامانه",
    "Frappe Support": "پشتیبانی فراپه", "Reset Desktop Layout": "بازنشانی چیدمان صفحه اصلی",
    "Logout": "خروج", "Search": "جستجو", "Save": "ذخیره", "Cancel": "انصراف",
    "Close": "بستن", "Edit": "ویرایش", "Delete": "حذف", "Help": "راهنما",
}


def display_label(value):
    import frappe
    return LABELS.get(value, frappe._(value, lang="fa")) if value else ""
