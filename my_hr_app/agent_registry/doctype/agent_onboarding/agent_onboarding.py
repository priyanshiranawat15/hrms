import frappe
from frappe.model.document import Document

from hrms.controllers.employee_boarding_controller import EmployeeBoardingController


class AgentOnboarding(EmployeeBoardingController):
	def validate(self):
		super().validate()
		if not self.ai_agent:
			return
		agent = frappe.db.get_value(
			"AI Agent",
			self.ai_agent,
			["agent_name", "company", "department", "designation"],
			as_dict=True,
		)
		if not agent:
			return
		self.employee_name = agent.agent_name
		self.company = self.company or agent.company
		self.department = self.department or agent.department
		self.designation = self.designation or agent.designation

	def on_submit(self):
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"{self.doctype} : {self.employee_name}",
				"expected_start_date": self.boarding_begins_on,
				"department": self.department,
				"company": self.company,
			}
		).insert(ignore_permissions=True, ignore_mandatory=True)

		self.db_set("project", project.name)
		self.db_set("boarding_status", "Pending")
		self.reload()
		self.create_task_and_notify_user()

	def get_holiday_list(self):
		if self.holiday_list:
			return self.holiday_list
		if self.company:
			return frappe.db.get_value("Company", self.company, "default_holiday_list")
		return None

	def update_if_holiday(self, date, holiday_list):
		if not holiday_list or not date:
			return date
		return super().update_if_holiday(date, holiday_list)
