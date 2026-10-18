frappe.listview_settings["Employee"] = frappe.listview_settings["Employee"] || {};

const previous_indicator = frappe.listview_settings["Employee"].get_indicator;
frappe.listview_settings["Employee"].get_indicator = function (doc) {
	if (doc.worker_type === "Agent") {
		return [__("AI"), "blue", "worker_type,=,Agent"];
	}
	if (previous_indicator) {
		return previous_indicator(doc);
	}
};
