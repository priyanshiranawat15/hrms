frappe.ui.form.on("Agent Onboarding", {
	agent_onboarding_template(frm) {
		if (!frm.doc.agent_onboarding_template) {
			return;
		}
		frappe.call({
			method: "hrms.controllers.employee_boarding_controller.get_onboarding_details",
			args: {
				parent: frm.doc.agent_onboarding_template,
				parenttype: "Agent Onboarding Template",
			},
			callback(r) {
				frm.clear_table("activities");
				(r.message || []).forEach((row) => frm.add_child("activities", row));
				frm.refresh_field("activities");
			},
		});
	},
	ai_agent(frm) {
		if (!frm.doc.ai_agent) {
			return;
		}
		frappe.db.get_doc("AI Agent", frm.doc.ai_agent).then((agent) => {
			frm.set_value("company", agent.company);
			frm.set_value("department", agent.department);
			frm.set_value("designation", agent.designation);
			frm.set_value("employee_name", agent.agent_name);
		});
	},
});
