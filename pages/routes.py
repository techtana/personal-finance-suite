from flask import redirect, render_template, request, url_for

from pages import pages_bp


def _page(path, template, endpoint, title, role, note):
    def view():
        return render_template(template, page_title=title, role=role, role_note=note)

    pages_bp.add_url_rule(path, endpoint, view)


# Your picture (read-only)
_page("/overview", "overview.html", "overview", "Overview", "view",
      "Where you stand today. Everything here is computed from your Plan and Balances.")
_page("/forecast", "forecast.html", "forecast", "Forecast", "view",
      "Where your plan takes you. Computed from your Plan, starting at today's Balances.")
_page("/then-vs-now", "then_vs_now.html", "then_vs_now", "Then vs. Now", "view",
      "How past decisions turned out. Computed from your equity rules, assets and share prices.")
_page("/taxes", "taxes.html", "taxes", "Taxes", "mixed",
      "An estimate from your Plan. The tax profile is yours to edit; the charts and findings are computed.")
# Your inputs
_page("/plan", "plan.html", "plan", "Plan", "manage",
      "What you expect to earn and spend. You enter and edit everything here; the Forecast is built from it.")
_page("/balances", "balances.html", "balances", "Balances", "manage",
      "What you have and owe right now. Record current values here; a quick monthly check keeps the rest accurate.")
_page("/import", "import.html", "import_files", "Import", "manage",
      "Bring in statements, receipts and pay stubs. Nothing is saved until you review and accept it.")
# Guidance
_page("/insights", "insights.html", "insights", "Insights", "guidance",
      "What the app notices in your data. Observations with their basis, not advice.")
_page("/settings", "settings.html", "settings", "Settings", "",
      "Preferences, categories, backup and the AI assistant.")


@pages_bp.route("/")
def index():
    return redirect(url_for("pages.overview"))


# Addresses from before the pages were regrouped by role.
OLD_PATHS = {
    "/dashboard": ("pages.overview", {}),
    "/timeline": ("pages.forecast", {}),
    "/transactions": ("pages.plan", {}),
    "/accounts": ("pages.balances", {"type": "cash"}),
    "/equity": ("pages.balances", {"type": "asset"}),
    "/loans": ("pages.balances", {"type": "liability"}),
}


def _redirect_old():
    endpoint, params = OLD_PATHS[request.path]
    return redirect(url_for(endpoint, **params))


for _old in OLD_PATHS:
    pages_bp.add_url_rule(_old, "old_" + _old.strip("/"), _redirect_old)
