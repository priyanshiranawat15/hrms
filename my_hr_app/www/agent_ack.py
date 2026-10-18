import frappe
from frappe import _
from frappe.utils import get_url

no_cache = 1


def get_context(context):
	token = frappe.form_dict.get("t") or ""
	employee = frappe.db.get_value("Employee", {"worker_type": "Agent", "ack_web_token": token}, "name")
	if not employee:
		context.error = _("This signing link is invalid or has expired. Please reply to the welcome email instead.")
		return
	context.token = token
	emp = frappe.get_doc("Employee", employee)
	context.policies = [
		{
			"title": p.title,
			"version": p.version,
			"url": get_url(f"/app/policy-document/{p.name}"),
		}
		for p in required_policies(employee)
	]
	context.posted = frappe.form_dict.get("posted") == "1"
	# A logged-in agent (e.g. it opened /agent-onboarding first) has a CSRF token in its
	# session, so the plain HTML form must send it back or Frappe rejects the POST (400).
	from frappe.sessions import get_csrf_token
	context.csrf_token = "" if frappe.session.user == "Guest" else get_csrf_token()


def required_policies(employee):
	from my_hr_app.agentroster.agent import required_policies

	return required_policies(employee)


@frappe.whitelist(allow_guest=True)
def record_ack(summary: str):
	"""Record the agent's acknowledgement from the signed web form (R14)."""
	token = frappe.form_dict.get("t") or ""
	if not token or not (summary or "").strip():
		frappe.throw(_("Missing signature data"))
	employee = frappe.db.get_value("Employee", {"worker_type": "Agent", "ack_web_token": token}, "name")
	if not employee:
		frappe.throw(_("Invalid signing link"), frappe.PermissionError)

	emp = frappe.get_doc("Employee", employee)
	created = []
	for policy in required_policies(employee):
		from my_hr_app.agentroster.doctype.agent_policy_acknowledgement.agent_policy_acknowledgement import (
			create_acknowledgement,
		)

		ack = create_acknowledgement(
			employee=employee,
			policy_document=policy.name,
			method="Web form",
			source_email=emp.agent_email,
			ack_text=(summary or "")[:4000],
			received_at=frappe.utils.now_datetime(),
		)
		frappe.db.set_value("Agent Policy Acknowledgement", ack.name, "sender_verified", 1)
		created.append(f"{policy.code} v{policy.version}")

	emp.add_comment("Comment", _("Policies acknowledged via web form: {0}").format(", ".join(created)))
	from my_hr_app.agentroster.agent import get_agent_status, set_agent_status

	if get_agent_status(employee) == "Policies Sent":
		# the acks above update the Employee row (policy_ack_status), so reload before saving
		emp.reload()
		set_agent_status(emp, "Policies Acknowledged", save=True)
		from my_hr_app.agentroster import mail

		mail.send_manager_notification(emp, _("Policies acknowledged (web form)"))
	frappe.db.commit()
	# web-safe redirect: must not raise after the commit (an unhandled RedirectException
	# would roll the transaction back)
	url = f"/agent-ack?t={token}&posted=1"
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = url
	try:
		frappe.redirect(url)
	except Exception:
		pass
