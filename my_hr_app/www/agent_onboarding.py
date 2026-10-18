import frappe
from frappe import _

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/agent-onboarding"
		raise frappe.Redirect
	from my_hr_app.agentroster.self_service import build_checklist

	emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "worker_type": "Agent"}, "name")
	if not emp:
		context.error = _("This page is for AI agents. No agent record is linked to this login.")
		return
	context.data = build_checklist(frappe.get_doc("Employee", emp))
	context.done = frappe.form_dict.get("done") == "1"
	context.csrf = frappe.sessions.get_csrf_token()
