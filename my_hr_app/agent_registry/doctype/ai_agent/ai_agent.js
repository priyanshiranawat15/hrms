frappe.ui.form.on("AI Agent", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frappe.call({
			method: "my_hr_app.agent_registry.api.get_budget_summary",
			args: { agent: frm.doc.name },
			callback(r) {
				const summary = r.message || {};
				const unit = summary.budget_unit || "";
				frm.dashboard.add_indicator(
					`Spend ${summary.spend} / Budget ${summary.budget} ${unit}`,
					summary.over_budget ? "red" : "green"
				);
			},
		});
	},
});
