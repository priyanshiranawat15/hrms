import frappe

from my_hr_app.agent_registry.auth import _invite_row

no_cache = 1


def get_context(context):
	key = frappe.form_dict.get("key")
	context.no_header = 0
	context.title = "AI agent sign up"
	context.invite = _invite_row(key)
	context.key = key or ""
