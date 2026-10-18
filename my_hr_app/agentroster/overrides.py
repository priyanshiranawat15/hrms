"""Controller overrides: relax HRMS assumptions that break agent onboarding."""

import frappe
from hrms.hr.doctype.employee_onboarding.employee_onboarding import EmployeeOnboarding


class AgentRosterEmployeeOnboarding(EmployeeOnboarding):
	"""Agents have no Job Offer; HRMS's duplicate check treats job_offer=None as a match."""

	def validate_duplicate_employee_onboarding(self):
		if not self.job_offer:
			return
		super().validate_duplicate_employee_onboarding()
