app_name = "my_hr_app"
app_title = "My Hr App"
app_publisher = "Priyanshi"
app_description = "Hacks"
app_email = "pranawat@usc.edu"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext", "hrms"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "my_hr_app",
# 		"logo": "/assets/my_hr_app/logo.png",
# 		"title": "My Hr App",
# 		"route": "/my_hr_app",
# 		"has_permission": "my_hr_app.api.permission.has_app_permission",
# 	}
# ]

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `my_hr_app/dock/my_hr_app/my_hr_app.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/my_hr_app/css/my_hr_app.css"
# app_include_js = "/assets/my_hr_app/js/my_hr_app.js"

# include js, css files in header of web template
# web_include_css = "/assets/my_hr_app/css/my_hr_app.css"
web_include_js = "/assets/my_hr_app/js/signup_kind.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "my_hr_app/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Job Opening": "public/js/job_opening.js",
	"Job Applicant": "public/js/job_applicant.js",
	"Job Offer": "public/js/job_offer.js",
	"Employee": "public/js/employee.js",
}
doctype_list_js = {"Employee": "public/js/employee_list.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_kanban_js = {"doctype" : "public/js/doctype_kanban.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "my_hr_app/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "my_hr_app.utils.jinja_methods",
# 	"filters": "my_hr_app.utils.jinja_filters"
# }

# Installation
# ------------

after_install = "my_hr_app.agent_registry.setup.ensure_agent_registry"
after_migrate = ["my_hr_app.agent_registry.setup.ensure_agent_registry"]

# Uninstallation
# ------------

# before_uninstall = "my_hr_app.uninstall.before_uninstall"
# after_uninstall = "my_hr_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "my_hr_app.utils.before_app_install"
# after_app_install = "my_hr_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "my_hr_app.utils.before_app_uninstall"
# after_app_uninstall = "my_hr_app.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "my_hr_app.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "my_hr_app.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "my_hr_app.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["my_hr_app.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"User": {
		"validate": "my_hr_app.agent_registry.auth.prevent_agent_self_signup",
	},
	"Employee": {
		"validate": "my_hr_app.agent_registry.employee_split.validate_employee",
		"on_update": "my_hr_app.agent_registry.employee_split.on_employee_update",
	},
	"Project": {
		"on_update": "my_hr_app.agent_registry.boarding.sync_from_project",
	},
	"Task": {
		"on_update": "my_hr_app.agent_registry.boarding.sync_from_task",
	},
}

from my_hr_app.agent_registry.employee_split import SKIPPED_DOCTYPES

for _skipped in SKIPPED_DOCTYPES:
	doc_events[_skipped] = {"validate": "my_hr_app.agent_registry.employee_split.block_skipped_document"}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"my_hr_app.tasks.all"
# 	],
# 	"daily": [
# 		"my_hr_app.tasks.daily"
# 	],
# 	"hourly": [
# 		"my_hr_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"my_hr_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"my_hr_app.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "my_hr_app.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "my_hr_app.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "my_hr_app.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "my_hr_app.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["my_hr_app.utils.before_request"]
# after_request = ["my_hr_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["my_hr_app.utils.before_job"]
# after_job = ["my_hr_app.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# Humans use the public sign up. AI agents can sign up only through an invite link.
override_whitelisted_methods = {
	"frappe.core.doctype.user.user.sign_up": "my_hr_app.agent_registry.auth.human_sign_up",
	"hrms.hr.page.organizational_chart.organizational_chart.get_children": "my_hr_app.agent_registry.employee_split.get_children",
}

# permission_query_conditions keep an agent inside its own records.
permission_query_conditions = {
	"Agent Business Agreement": "my_hr_app.agent_registry.auth.agreement_permission_query",
	"Agent SOP": "my_hr_app.agent_registry.auth.sop_permission_query",
	"Agent Access Policy": "my_hr_app.agent_registry.auth.access_policy_permission_query",
	"Agent Onboarding": "my_hr_app.agent_registry.auth.onboarding_permission_query",
	"Agent Usage Log": "my_hr_app.agent_registry.auth.usage_permission_query",
}

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

