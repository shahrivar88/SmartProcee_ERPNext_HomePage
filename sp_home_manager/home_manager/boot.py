import frappe

from sp_home_manager.home_manager.api import get_boot_layout
from sp_home_manager.home_manager.labels import LABELS


def boot_session(bootinfo):
	bootinfo.sp_home = get_boot_layout()
	bootinfo.setdefault("__messages", {}).update(LABELS)
