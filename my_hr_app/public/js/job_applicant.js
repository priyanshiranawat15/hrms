frappe.ui.form.on("Job Applicant", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Accepted") {
			return;
		}
		// Run after HRMS adds "Create Employee", then replace that action with a choice.
		setTimeout(() => add_hire_choice(frm), 0);
	},
});

function add_hire_choice(frm) {
	if (frm.__agent_hire_choice) {
		return;
	}
	frm.__agent_hire_choice = true;

	frappe.db.get_value("AI Agent", { job_applicant: frm.doc.name }, "name").then((r) => {
		const existing = r.message && r.message.name;
		if (existing) {
			frm.add_custom_button(__("Show AI Agent"), () => {
				frappe.set_route("Form", "AI Agent", existing);
			});
			return;
		}
		if (frm.doc.__onload && frm.doc.__onload.employee) {
			return;
		}

		frm.add_custom_button(__("Hire as Employee or AI Agent"), () => choose_hire_kind(frm));
	});
}

function choose_hire_kind(frm) {
	const opening = frm.doc.job_title;
	const open_dialog = (worker_kind) => {
		const dialog = new frappe.ui.Dialog({
			title: __("Who are you hiring?"),
			fields: [
				{
					fieldtype: "Select",
					fieldname: "worker_kind",
					label: __("Hire as"),
					options: "Employee\nAI Agent",
					default: worker_kind === "AI Agent" ? "AI Agent" : "Employee",
					reqd: 1,
				},
			],
			primary_action_label: __("Continue"),
			primary_action(values) {
				dialog.hide();
				if (values.worker_kind === "AI Agent") {
					frappe.new_doc("AI Agent", {
						agent_name: frm.doc.applicant_name,
						company: frm.doc.company,
						designation: frm.doc.designation,
						job_opening: opening,
						job_applicant: frm.doc.name,
					});
				} else if (frm.make_methods && frm.make_methods.Employee) {
					frm.make_methods.Employee();
				}
			},
		});
		dialog.show();
	};

	if (!opening) {
		open_dialog("Employee");
		return;
	}
	frappe.db.get_value("Job Opening", opening, "worker_kind").then((r) => {
		open_dialog(r.message && r.message.worker_kind);
	});
}
