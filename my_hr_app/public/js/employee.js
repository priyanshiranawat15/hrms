const AGENT_HIDDEN_FIELDS = [
	"gender",
	"date_of_birth",
	"salutation",
	"middle_name",
	"last_name",
	"marital_status",
	"blood_group",
	"family_background",
	"health_details",
	"personal_email",
	"prefered_contact_email",
	"create_user_automatically",
	"create_user_permission",
	"bank_name",
	"bank_ac_no",
	"iban",
	"salary_mode",
	"passport_number",
	"date_of_issue",
	"valid_upto",
	"place_of_issue",
	"current_address",
	"permanent_address",
	"current_accommodation_type",
	"permanent_accommodation_type",
	"person_to_be_contacted",
	"relation",
	"emergency_phone_number",
];

const AGENT_HIDDEN_SECTIONS = [
	"personal_details",
	"contact_details",
	"attendance_and_leave_details",
	"salary_information",
	"profile_tab",
	"employment_details",
	"exit",
	"connections_tab",
	"bank_details_section",
	"passport_details_section",
	"emergency_contact_details",
	"address_section",
];

const AGENT_SKIPPED_ASSIGNMENTS = ["Leave Policy", "Salary Structure", "Shift", "Shift Schedule"];

function show_field(frm, fieldname, show) {
	if (!frm.fields_dict[fieldname] && !frm.meta.fields.some((field) => field.fieldname === fieldname)) {
		return;
	}
	frm.set_df_property(fieldname, "hidden", show ? 0 : 1);
	frm.toggle_display(fieldname, show);
}

frappe.ui.form.on("Employee", {
	refresh(frm) {
		const agent = frm.doc.worker_type === "Agent";
		show_field(frm, "agent_profile", agent);
		show_field(frm, "operator", agent);
		AGENT_HIDDEN_FIELDS.forEach((fieldname) => show_field(frm, fieldname, !agent));
		AGENT_HIDDEN_SECTIONS.forEach((fieldname) => show_field(frm, fieldname, !agent));
		if (frm.layout) {
			frm.layout.refresh_sections();
		}
		if (!agent) {
			return;
		}
		frm.dashboard.set_headline(
			__("AI coworker. Personal, pay, leave, and attendance details stay empty.")
		);
		setTimeout(() => {
			AGENT_SKIPPED_ASSIGNMENTS.forEach((label) => {
				frm.remove_custom_button(__(label), __("Create Assignments"));
			});
		}, 600);
	},
	worker_type(frm) {
		frm.trigger("refresh");
	},
});
