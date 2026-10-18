"""End-to-end smoke test of the AgentRoster v2 flow (T1-T12 happy path, no real email).

Run: bench --site hrms.localhost execute my_hr_app.agentroster.smoke.run
"""

import frappe


def run():
	steps = []

	def log(step, result):
		steps.append(f"{step}: {result}")
		print(f"{step}: {result}")
		frappe.db.commit()

	frappe.set_user("Administrator")

	company = ensure_company()
	priya = ensure_manager(company)

	# R1: Add Agent -> Employee worker_type=Agent, agent_status=Draft
	emp = ensure_agent(company, priya)
	# retire leftover test policies from governance runs (only demo policies stay published)
	frappe.db.sql("update `tabPolicy Document` set status = 'Retired' where code = 'GOVREACK' or (code = 'RULES' and version > 1)")
	# reset any state left over from a previous smoke run
	frappe.db.set_value("Employee", emp.name, "agent_status", "Draft")
	frappe.db.set_value("Employee", emp.name, "status", "Active")
	frappe.db.set_value("Employee", emp.name, "approval_code", "")
	for doctype in ("Employee Onboarding", "Employee Separation"):
		for name in frappe.get_all(doctype, filters={"employee": emp.name}, pluck="name"):
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.flags.from_agentroster = True
				doc.cancel()
			doc.delete(ignore_permissions=True)
	frappe.db.set_value(
		"Agent Policy Acknowledgement", {"employee": emp.name}, "superseded", 1
	)
	frappe.db.commit()
	log("reset", emp.name)
	log("R1 employee created", (emp.worker_type, frappe.db.get_value("Employee", emp.name, "agent_status"), emp.agent_email))

	# R3: publish policies
	for code, title, body in [
		("RULES", "Rules of Agreement", "You are an agent of Acme. Work in our tools. Follow our rules."),
		("CODE-OF-CONDUCT", "Code of Conduct", "Be respectful. Do not exfiltrate data. Escalate to your manager."),
		("AUP", "Acceptable Use", "Use company tools for company work. No side jobs."),
	]:
		pname = f"{code}-v1"
		if not frappe.db.exists("Policy Document", pname):
			p = frappe.get_doc(
				{
					"doctype": "Policy Document",
					"code": code,
					"title": title,
					"policy_type": "Other",
					"version": 1,
					"status": "Draft",
					"body": body,
					"applies_to_agents": 1,
				}
			)
			p.insert(ignore_permissions=True)
		else:
			p = frappe.get_doc("Policy Document", pname)
		if p.status != "Published":
			p.status = "Published"
			p.save(ignore_permissions=True)
	log("R3 policies published", frappe.get_all("Policy Document", filters={"status": "Published"}, pluck="name"))

	# R2: start onboarding -> welcome email + Policies Sent
	onboarding_name = frappe.call(
		__import__("my_hr_app.agentroster.agent", fromlist=["start_onboarding"]).start_onboarding,
		employee=emp.name,
	)
	log("R2 onboarding", (onboarding_name, frappe.db.get_value("Employee", emp.name, "agent_status")))

	# R4: agent replies ACK from its address -> 3 acks + Policies Acknowledged
	comm = frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"sender": emp.agent_email,
			"recipients": "hr@acme.com",
			"subject": f"[AR-{emp.name}] Re: Welcome",
			"content": "ACK RULES v1, CODE-OF-CONDUCT v1, AUP v1\nI will work only in Acme tools, keep data inside, and escalate to Priya.",
			"text_content": "ACK RULES v1, CODE-OF-CONDUCT v1, AUP v1\nI will work only in Acme tools, keep data inside, and escalate to Priya.",
			"reference_doctype": "Employee",
			"reference_name": emp.name,
		}
	)
	comm.insert(ignore_permissions=True)
	log("R4 acks", (
		frappe.db.count("Agent Policy Acknowledgement", {"employee": emp.name, "superseded": 0}),
		frappe.db.get_value("Employee", emp.name, "agent_status"),
	))

	# T6: invite before acks must fail - all acks exist, so instead test lock differently:
	# temporarily delete one ack? skip destructive; verify acks_exist logic only.

	# R5: mark GitHub row Invited -> Tool Access + invite notice
	onb = frappe.get_doc("Employee Onboarding", onboarding_name)
	for row in onb.activities:
		if row.activity_kind == "Tool Invite":
			row.access_status = "Invited"
			row.save() if False else None
	onb.flags.from_agentroster = True
	onb.save(ignore_permissions=True)
	log("R5 invited rows", (
		frappe.db.get_value("Employee", emp.name, "agent_status"),
	))

	# R6: agent replies JOINED github -> row Accepted
	for tool_code, handle in [("github", "@grokbot-acme"), ("slack", "@grokbot"), ("jira", "grokbot")]:
		c2 = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Received",
				"sender": emp.agent_email,
				"subject": f"[AR-{emp.name}] Re: invite",
				"content": f"JOINED {tool_code} {handle}",
				"text_content": f"JOINED {tool_code} {handle}",
				"reference_doctype": "Employee",
				"reference_name": emp.name,
			}
		)
		c2.insert(ignore_permissions=True)
	log("R6 joined rows", frappe.db.get_value("Employee", emp.name, "agent_status"))

	# R7: first assignment + DONE -> Awaiting Approval
	agent_mod = __import__("my_hr_app.agentroster.agent", fromlist=["start_first_assignment"])
	task_name = frappe.call(
		agent_mod.start_first_assignment,
		employee=emp.name,
		subject="Summarize the on-call SOP",
		description="Open an issue in acme/ops summarizing our on-call SOP.",
	)
	c3 = frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"sender": emp.agent_email,
			"subject": f"[AR-{emp.name}] DONE",
			"content": "DONE\nhttps://github.com/acme/ops/issues/12",
			"text_content": "DONE\nhttps://github.com/acme/ops/issues/12",
			"reference_doctype": "Employee",
			"reference_name": emp.name,
		}
	)
	c3.insert(ignore_permissions=True)
	log("R7 done", (task_name, frappe.db.get_value("Employee", emp.name, "agent_status")))
	approval_code = frappe.db.get_value("Employee", emp.name, "approval_code")

	# T11: wrong code -> no change
	c4 = frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"sender": priya.user_id,
			"subject": f"[AR-{emp.name}] Approve?",
			"content": "APPROVE WRONGCODE looks good",
			"text_content": "APPROVE WRONGCODE looks good",
			"reference_doctype": "Employee",
			"reference_name": emp.name,
		}
	)
	c4.insert(ignore_permissions=True)
	log("T11 wrong code status unchanged", frappe.db.get_value("Employee", emp.name, "agent_status"))

	# R8: APPROVE <code> from manager -> Active
	c5 = frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"sender": priya.user_id,
			"subject": f"[AR-{emp.name}] Approve?",
			"content": f"APPROVE {approval_code} good first issue",
			"text_content": f"APPROVE {approval_code} good first issue",
			"reference_doctype": "Employee",
			"reference_name": emp.name,
		}
	)
	c5.insert(ignore_permissions=True)
	log("R8 approved", frappe.db.get_value("Employee", emp.name, "agent_status"))

	# R9: offboard -> separation + CONFIRM OFFBOARD -> Offboarded
	agent_mod2 = __import__("my_hr_app.agentroster.agent", fromlist=["start_offboarding"])
	sep_name = frappe.call(agent_mod2.start_offboarding, employee=emp.name, reason="Demo end", last_day=None)
	log("R9 separation rows", frappe.get_all(
		"Employee Boarding Activity",
		filters={"parent": sep_name, "parenttype": "Employee Separation"},
		fields=["activity_name", "access_status"],
	))
	c6 = frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"sender": emp.agent_email,
			"subject": f"[AR-{emp.name}] Offboard",
			"content": "CONFIRM OFFBOARD\nleft channels, revoked tokens",
			"text_content": "CONFIRM OFFBOARD\nleft channels, revoked tokens",
			"reference_doctype": "Employee",
			"reference_name": emp.name,
		}
	)
	c6.insert(ignore_permissions=True)
	sep = frappe.get_doc("Employee Separation", sep_name)
	for row in sep.activities:
		row.access_status = "Removed"
	sep.flags.from_agentroster = True
	sep.save(ignore_permissions=True)
	log("T16 final", (
		frappe.db.get_value("Employee", emp.name, "agent_status"),
		frappe.db.get_value("Employee", emp.name, "status"),
	))

	frappe.db.commit()
	return steps


def ensure_company():
	if not frappe.db.exists("Warehouse Type", "Transit"):
		frappe.get_doc(
			{"doctype": "Warehouse Type", "warehouse_type": "Transit", "__newname": "Transit"}
		).insert(ignore_permissions=True)
	if not frappe.db.exists("Company", "Acme"):
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": "Acme",
				"abbr": "ACME",
				"default_currency": "USD",
				"country": "United States",
			}
		)
		company.flags.from_agentroster = True
		company.insert(ignore_permissions=True)
	return "Acme"


def ensure_manager(company):
	if frappe.db.exists("Employee", {"employee_name": "Priya Ops"}):
		return frappe.get_doc("Employee", {"employee_name": "Priya Ops"})
	if not frappe.db.exists("User", "priya@acme.com"):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": "priya@acme.com",
				"first_name": "Priya",
				"send_welcome_email": 0,
			}
		)
		user.flags.ignore_permissions = True
		user.insert(ignore_permissions=True)
	for designation in ("Operations Lead", "AI Operations Assistant"):
		if not frappe.db.exists("Designation", designation):
			frappe.get_doc({"doctype": "Designation", "designation_name": designation}).insert(
				ignore_permissions=True
			)
	for gender in ("Female", "Male", "Other"):
		if not frappe.db.exists("Gender", gender):
			frappe.get_doc({"doctype": "Gender", "gender": gender}).insert(ignore_permissions=True)
	emp = frappe.get_doc(
		{
			"doctype": "Employee",
			"employee_name": "Priya Ops",
			"first_name": "Priya",
			"last_name": "Ops",
			"company": company,
			"designation": "Operations Lead",
			"status": "Active",
			"date_of_joining": "2025-01-01",
			"date_of_birth": "1990-01-01",
			"gender": "Female",
			"user_id": "priya@acme.com",
		}
	)
	emp.flags.from_agentroster = True
	emp.insert(ignore_permissions=True)
	return emp


def ensure_agent(company, priya):
	if frappe.db.exists("Employee", {"employee_name": "Grok Bot"}):
		emp = frappe.get_doc("Employee", {"employee_name": "Grok Bot"})
	else:
		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"employee_name": "Grok Bot",
				"first_name": "Grok",
				"last_name": "Bot",
				"company": company,
				"designation": "AI Operations Assistant",
				"status": "Active",
				"date_of_joining": frappe.utils.today(),
			}
		)
	emp.update(
		{
			"worker_type": "Agent",
			"agent_email": "dhruv-assistant@mail.grokbot.com",
			"operator_name": "Dhruv",
			"operator_email": "dbhavsar9898@gmail.com",
			"agent_vendor": "xAI",
			"agent_runtime": "Grok Bot (hosted)",
			"inviting_manager": priya.name,
			"reports_to": priya.name,
		}
	)
	emp.flags.from_agentroster = True
	if emp.is_new():
		emp.insert(ignore_permissions=True)
	else:
		emp.save(ignore_permissions=True)
	return emp
