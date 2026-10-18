"""AI-governance validation suite: Layer 1/2/3 enforcement cases beyond the happy path.

Run: bench --site hrms.localhost execute my_hr_app.agentroster.governance.run
"""

import frappe

from my_hr_app.agentroster.agent import acks_exist, get_agent_status
from my_hr_app.agentroster.mail import first_line

STEPS = []


def log(step, ok, detail=""):
	STEPS.append((step, ok, detail))
	marker = "PASS" if ok else "FAIL"
	print(f"[{marker}] {step} {detail}")


def expect_throw(step, fn, needle=""):
	try:
		fn()
	except Exception as e:
		ok = needle.lower() in str(e).lower() if needle else True
		log(step, ok, f"(threw: {str(e)[:90]})")
		return
	log(step, False, "(no exception raised)")


def run():
	frappe.set_user("Administrator")
	from my_hr_app.agentroster import agent as agent_mod
	from my_hr_app.agentroster import smoke as smoke_mod

	company = smoke_mod.ensure_company()
	priya = smoke_mod.ensure_manager(company)
	emp = smoke_mod.ensure_agent(company, priya)
	frappe.db.set_value("Employee", emp.name, "agent_status", "Draft")
	frappe.db.set_value("Employee", emp.name, "policy_ack_status", "Pending")
	frappe.db.set_value("Employee", emp.name, "status", "Active")
	frappe.db.commit()

	# ---- Layer 1: tamper-evident policies (on a disposable policy, not demo data)
	if frappe.db.exists("Policy Document", "GOVTEST-v1"):
		frappe.delete_doc("Policy Document", "GOVTEST-v1", force=True, ignore_permissions=True)
	gp = frappe.get_doc(
		{
			"doctype": "Policy Document",
			"code": "GOVTEST",
			"title": "Governance Test Policy",
			"policy_type": "Other",
			"version": 1,
			"status": "Draft",
			"body": "Test body.",
			"applies_to_agents": 0,
		}
	)
	gp.insert(ignore_permissions=True)
	gp.status = "Published"
	gp.save(ignore_permissions=True)
	gp.body = "Test body. TAMPERED"
	expect_throw("L1 published policy body is frozen", lambda: gp.save(ignore_permissions=True))
	gp.reload()
	log("L1 hash unchanged", gp.content_hash == frappe.db.get_value("Policy Document", "GOVTEST-v1", "content_hash"))
	frappe.delete_doc("Policy Document", "GOVTEST-v1", force=True, ignore_permissions=True)

	# ---- Layer 1: ACK only counts published versions (T5)
	before = frappe.db.count("Agent Policy Acknowledgement", {"employee": emp.name})
	insert_comm(emp, "ACK RULES v9\nI comply.")
	after = frappe.db.count("Agent Policy Acknowledgement", {"employee": emp.name})
	log("L1 T5 unknown version -> no ack", after == before)

	# ---- Layer 1: spoofed sender gets no ack (T4)
	before = frappe.db.count("Agent Policy Acknowledgement", {"employee": emp.name})
	insert_comm(emp, "ACK RULES v1\nSigned!", sender="spoofed@evil.com", subject_tag=False)
	after = frappe.db.count("Agent Policy Acknowledgement", {"employee": emp.name})
	log("L1 T4 spoofed sender -> no ack", after == before)

	# ---- happy ack: Policies Sent -> Policies Acknowledged
	frappe.db.set_value("Employee", emp.name, "agent_status", "Policies Sent")
	frappe.db.commit()
	insert_comm(emp, "ACK RULES v1, CODE-OF-CONDUCT v1, AUP v1\nI will follow all Acme rules.")
	log("L1 T3 ack recorded", get_agent_status(emp.name) == "Policies Acknowledged")
	log("L1 sender_verified", bool(
		frappe.db.get_value(
			"Agent Policy Acknowledgement",
			{"employee": emp.name, "policy_code": "RULES", "superseded": 0},
			"sender_verified",
		)
	))
	ack = frappe.get_doc(
		"Agent Policy Acknowledgement",
		{"employee": emp.name, "policy_code": "RULES", "superseded": 0},
	)
	ack.ack_text = f"tampered {frappe.utils.now()}"
	expect_throw("L1 T18 ack evidence immutable", lambda: ack.save(ignore_permissions=True))

	# ---- Layer 3: invite lock before acks (T6)
	emp2 = create_second_agent(company, priya)
	agent_mod.start_onboarding(employee=emp2.name)
	expect_throw(
		"L3 T6 invites locked without acks",
		lambda: frappe.call(agent_mod.send_tool_invites, employee=emp2.name),
		needle="acknowledged",
	)

	# ---- Layer 3: evidence required on manual Accept
	onboarding = frappe.db.get_value("Employee Onboarding", {"employee": emp2.name, "docstatus": ["!=", 2]}, "name")
	onb = frappe.get_doc("Employee Onboarding", onboarding)
	row = next(r for r in onb.activities if (r.activity_kind or "") == "Tool Invite")
	row.access_status = "Accepted"
	expect_throw(
		"L3 evidence required for Accepted",
		lambda: onb.save(ignore_permissions=True),
		needle="evidence",
	)

	# ---- Layer 2: approval gate on check result
	frappe.db.set_value("Employee", emp.name, "agent_status", "Ready for Assignment")
	frappe.db.commit()
	task = frappe.call(
		agent_mod.start_first_assignment,
		employee=emp.name,
		subject="Demo task",
		description="Do the thing",
	)
	insert_comm(emp, "DONE\nhttps://example.com/pr/1")
	frappe.db.set_value("Employee", emp.name, "check_result", "Needs follow-up")
	expect_throw(
		"L2 approval blocked while check needs follow-up",
		lambda: frappe.call(agent_mod.approve_agent, employee=emp.name),
		needle="follow-up",
	)
	frappe.db.set_value("Employee", emp.name, "check_result", "Pass")
	frappe.call(agent_mod.approve_agent, employee=emp.name, note="checked: summary consistent")
	log("L2 approved after check Pass", get_agent_status(emp.name) == "Active")

	# ---- Layer 3: emergency suspension + resume
	frappe.call(agent_mod.suspend_agent, employee=emp.name, reason="test suspension")
	log(
		"L3 suspend",
		frappe.db.get_value("Employee", emp.name, "status") == "Suspended",
	)
	frappe.call(agent_mod.resume_agent, employee=emp.name)
	log("L3 resume", frappe.db.get_value("Employee", emp.name, "status") == "Active")

	# ---- re-ack on policy update (T14): fresh version each run
	frappe.db.set_value("Employee", emp.name, "policy_ack_status", "Current")
	test_version = (
		frappe.db.sql("select max(version) from `tabPolicy Document` where code = 'GOVREACK'")[0][0] or 0
	) + 1
	p2 = frappe.get_doc(
		{
			"doctype": "Policy Document",
			"code": "GOVREACK",
			"title": "Governance Re-ack Test",
			"policy_type": "Other",
			"version": test_version,
			"status": "Draft",
			"body": f"Re-ack test body v{test_version}: stricter data handling.",
			"applies_to_agents": 1,
			"change_summary": "stricter data handling",
		}
	)
	p2.insert(ignore_permissions=True)
	p2.status = "Published"
	p2.save(ignore_permissions=True)
	log(
		"L1 T14 re-ack flag set",
		frappe.db.get_value("Employee", emp.name, "policy_ack_status") == "Re-ack Required",
	)
	log("L1 old ack kept", frappe.db.exists(
		"Agent Policy Acknowledgement", {"employee": emp.name, "policy_code": "RULES", "policy_version": 1, "superseded": 0}
	))
	# old acks for RULES now superseded? spec: old one kept; new ack supersedes
	insert_comm(emp, f"ACK GOVREACK v{test_version}\nData handling: keep data in org tools only.")
	log(
		"L1 T14 re-ack recorded",
		bool(frappe.db.exists(
			"Agent Policy Acknowledgement", {"employee": emp.name, "policy_code": "GOVREACK", "policy_version": test_version, "superseded": 0}
		)),
	)

	# cleanup second agent
	frappe.db.commit()
	return STEPS


def create_second_agent(company, priya):
	if frappe.db.exists("Employee", {"employee_name": "Agent Two"}):
		emp = frappe.get_doc("Employee", {"employee_name": "Agent Two"})
	else:
		emp = frappe.new_doc("Employee")
	emp.update(
		{
			"employee_name": "Agent Two",
			"first_name": "Agent",
			"last_name": "Two",
			"company": company,
			"designation": "AI Operations Assistant",
			"status": "Active",
			"date_of_joining": frappe.utils.today(),
			"worker_type": "Agent",
			"agent_email": "agent-two@acme.test",
			"operator_name": "Dhruv",
			"reports_to": priya.name,
		}
	)
	emp.flags.from_agentroster = True
	if emp.is_new():
		emp.insert(ignore_permissions=True)
	else:
		emp.save(ignore_permissions=True)
	# reset any boarding state from previous runs
	frappe.db.set_value("Employee", emp.name, "agent_status", "Draft")
	for doctype in ("Employee Onboarding", "Employee Separation"):
		for name in frappe.get_all(doctype, filters={"employee": emp.name}, pluck="name"):
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.cancel()
			doc.delete(ignore_permissions=True)
	frappe.db.commit()
	return emp


def insert_comm(emp, content, sender=None, subject_tag=True):
	sender = sender or emp.agent_email
	subject = (f"[AR-{emp.name}] Re: x" if subject_tag else "random subject")
	comm = frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"sender": sender,
			"recipients": "hr@acme.com",
			"subject": subject,
			"content": content,
			"text_content": content,
			"reference_doctype": "Employee",
			"reference_name": emp.name,
		}
	)
	comm.insert(ignore_permissions=True)
	return comm
