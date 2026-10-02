from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / ".runtime" / "jev-explore-fixture"
ROOT.mkdir(parents=True, exist_ok=True)
files = {
    "payroll_page.py": '''"""Employee-facing payroll page, registered at /my/pay with the label My Pay."""
from pay_slip import render_payslip
from pay_history import own_pay_history

def employee_payroll_page(current_employee, month):
    """Employees open My Pay to see their net pay and payslip history."""
    records = own_pay_history(current_employee.id)
    current = next(record for record in records if record.month == month)
    return {"title": "My Pay", "net_pay": current.net_pay,
            "payslip": render_payslip(current), "history": records}

ROUTES = {"/my/pay": employee_payroll_page}
''',
    "pay_slip.py": '''"""Reusable payslip renderer called by the payroll page."""
def render_payslip(record):
    return {"gross_pay": record.gross_pay, "deductions": record.deductions,
            "net_pay": record.net_pay, "employee_id": record.employee_id}
''',
    "pay_history.py": '''"""Data access for an employee's own historical payroll records."""
def own_pay_history(employee_id):
    return payroll_records.where(employee_id=employee_id).order_by("month")
''',
    "team_pay.py": '''"""Manager-only payroll totals; employees cannot use this page to see their own pay."""
def manager_team_pay(manager):
    assert manager.role == "manager"
    return {"team_total": payroll_records.sum_for_team(manager.team_id)}
''',
    "pay_rates.py": '''"""Administrative hourly payroll rate settings, unrelated to employee payslip display."""
def update_hourly_rate(admin, employee_id, rate):
    assert admin.role == "admin"
    rate_table.save(employee_id, rate)
''',
    "payday_email.py": '''"""Notification for payroll processing; sends a reminder with no pay amount or UI."""
def send_payday_notice(employee):
    return mail.send(employee.email, "Payroll completed; your payslip is available in the app.")
''',
    "employee_page.py": '''"""Employee directory details: contact and department, no salary or payroll display."""
def employee_details(employee):
    return {"name": employee.name, "department": employee.department}
''',
    "access_rules.py": '''"""Authorization helper for payroll and unrelated app pages."""
def can_access(employee, owner_id):
    return employee.id == owner_id or employee.role == "admin"
''',
}
unrelated = ["login_page", "team_list", "my_profile", "roles_menu", "settings_page", "employee_card", "employee_list", "new_employee", "navbar", "dashboard", "holidays_page", "reports_page", "invite_form", "footer", "help_page", "time_off", "billing_page", "home_page", "admin_panel", "onboarding", "search_bar", "avatar", "theme", "logout", "notifications", "calendar", "office_locations"]
for name in unrelated:
    files[name + ".py"] = f'''"""{name.replace('_', ' ').title()} handles unrelated application navigation and records."""
def {name}(employee):
    return {{"section": "{name}", "employee_id": employee.id}}
'''
assert len(files) == 35
for name, content in files.items():
    (ROOT / name).write_text("# Synthetic discovery tag: employee payroll; tag alone is not functional evidence.\n" + content, encoding="utf-8")
print(f"Created {len(files)} synthetic source files at {ROOT}")
