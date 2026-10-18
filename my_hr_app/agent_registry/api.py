import frappe
from frappe import _
from frappe.utils import flt, get_first_day, today


@frappe.whitelist()
def log_usage(agent, calls=1, tokens=0, cost=0, task_summary=None, on_behalf_of=None):
	"""Record usage. Agent system users may only log usage for themselves."""
	agent_user = frappe.db.get_value("AI Agent", agent, "system_user")
	if frappe.db.get_value("User", frappe.session.user, "user_type") == "Agent System User":
		owned = frappe.db.get_value("AI Agent", {"system_user": frappe.session.user}, "name")
		if owned != agent:
			frappe.throw(_("An agent can only record its own usage."))

	doc = frappe.get_doc(
		{
			"doctype": "Agent Usage Log",
			"ai_agent": agent,
			"date": today(),
			"calls": cint(calls),
			"tokens": cint(tokens),
			"cost": flt(cost),
			"task_summary": task_summary,
			"on_behalf_of": on_behalf_of,
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "system_user": agent_user}


def cint(value):
	return frappe.utils.cint(value)


@frappe.whitelist()
def get_budget_summary(agent):
	doc = frappe.get_doc("AI Agent", agent)
	month_start = get_first_day(today())
	spend = frappe.db.sql(
		"""
		select coalesce(sum(cost), 0)
		from `tabAgent Usage Log`
		where ai_agent = %s and date >= %s
		""",
		(agent, month_start),
	)[0][0]
	spend = flt(spend)
	budget = flt(doc.monthly_budget)
	return {
		"spend": spend,
		"budget": budget,
		"budget_unit": doc.budget_unit,
		"over_budget": bool(budget and spend > budget),
		"remaining": budget - spend if budget else None,
	}


@frappe.whitelist()
def agents_over_budget_count(filters=None):
	month_start = get_first_day(today())
	rows = frappe.db.sql(
		"""
		select a.name
		from `tabAI Agent` a
		left join `tabAgent Usage Log` u
			on u.ai_agent = a.name and u.date >= %s
		where a.status = 'Active' and ifnull(a.monthly_budget, 0) > 0
		group by a.name, a.monthly_budget
		having coalesce(sum(u.cost), 0) > a.monthly_budget
		""",
		month_start,
	)
	return {"value": len(rows), "fieldtype": "Int"}


@frappe.whitelist()
def credentials_due_count(filters=None):
	count = frappe.db.count(
		"AI Agent",
		{"status": "Active", "credential_rotation_due": ["<=", today()]},
	)
	return {"value": count, "fieldtype": "Int"}
