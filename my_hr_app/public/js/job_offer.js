frappe.ui.form.on("Job Offer", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Accepted" || frm.doc.docstatus !== 1) {
			return;
		}
		setTimeout(() => add_offer_hire_choice(frm), 0);
	},
});

function add_offer_hire_choice(frm) {
	if (frm.__agent_hire_choice) {
		return;
	}
	frm.__agent_hire_choice = true;

	frappe.db.get_value("AI Agent", { job_offer: frm.doc.name }, "name").then((r) => {
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
		frm.add_custom_button(__("Hire as Employee or AI Agent"), () => choose_offer_hire_kind(frm));
	});
}

function choose_offer_hire_kind(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Who are you hiring?"),
		fields: [
			{
				fieldtype: "Select",
				fieldname: "worker_kind",
				label: __("Hire as"),
				options: "Employee\nAI Agent",
				default: "Employee",
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
					department: frm.doc.department,
					designation: frm.doc.designation,
					job_applicant: frm.doc.job_applicant,
					job_offer: frm.doc.name,
				});
				return;
			}
			if (erpnext.job_offer && erpnext.job_offer.make_employee) {
				erpnext.job_offer.make_employee(frm);
			}
		},
	});

	const opening_source = frm.doc.job_applicant;
	if (!opening_source) {
		dialog.show();
		return;
	}
	frappe.db.get_value("Job Applicant", opening_source, "job_title").then((applicant) => {
		const opening = applicant.message && applicant.message.job_title;
		if (!opening) {
			dialog.show();
			return;
		}
		frappe.db.get_value("Job Opening", opening, "worker_kind").then((opening_doc) => {
			if (opening_doc.message && opening_doc.message.worker_kind === "AI Agent") {
				dialog.set_value("worker_kind", "AI Agent");
			}
			dialog.show();
		});
	});
}
