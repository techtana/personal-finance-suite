from flask import render_template, redirect, url_for
from pages import pages_bp


@pages_bp.route("/")
def index():
    return redirect(url_for("pages.dashboard"))


@pages_bp.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", title="Dashboard")


@pages_bp.route("/transactions")
def transactions():
    return redirect(url_for("pages.timeline"))


@pages_bp.route("/equity")
def equity():
    return render_template("equity.html", title="Equity Compensation")


@pages_bp.route("/accounts")
def accounts():
    return render_template("accounts.html", title="Accounts & Net Worth")


@pages_bp.route("/loans")
def loans():
    return render_template("loans.html", title="Loans")


@pages_bp.route("/timeline")
def timeline():
    return render_template("timeline.html", title="Cash Flow")


@pages_bp.route("/settings")
def settings():
    return render_template("settings.html", title="Settings")
