import click
import re
import json
import requests
from datetime import date, datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from cli.client import APIClient

console = Console()
client = APIClient()

CURRENCY_SYMBOLS = {
    'INR': '₹',
    'USD': '$',
    'EUR': '€',
    'GBP': '£',
    'JPY': '¥',
    'AUD': 'A$',
    'CAD': 'C$'
}

def get_currency_symbol(currency_code):
    return CURRENCY_SYMBOLS.get(currency_code or 'USD', currency_code or '$')

def check_login():
    """Helper to check if user has authenticated."""
    token = client.load_token()
    if not token:
        console.print("[bold red]Error:[/] You are not logged in. Run [bold green]expensewise-cli login[/] first.")
        raise click.Abort()
    return token


@click.group()
def cli():
    """ExpenseWise CLI - Personal Financial administration directly from your terminal.
    
    All actions communicate securely with the versioned REST API.
    """
    pass


# ==============================================================================
# USER MANAGEMENT COMMANDS
# ==============================================================================

@cli.command()
@click.option('--email', prompt='Email Address', help='Your registration email')
@click.option('--password', prompt=True, hide_input=True, help='Your password')
def login(email, password):
    """Authenticates credentials and downloads API Access Key."""
    console.print(f"Connecting to [bold cyan]{client.api_url}[/]...")
    response = client.login(email, password)
    
    if response.status_code == 200:
        data = response.json()
        token = data.get('token')
        client.save_token(token)
        console.print(f"[bold green]Success![/] Welcome back, [bold]{data['user']['name']}[/]. Access token saved locally.")
    else:
        err_msg = response.json().get('message', 'Check your credentials.')
        console.print(f"[bold red]Login Failed:[/] {err_msg}")


@cli.command(name='token-login')
@click.argument('token')
def token_login(token):
    """Authenticates using a web-generated API token copied from settings."""
    console.print("Verifying API token with server...")
    client.save_token(token)
    res = client.get_profile()
    if res.status_code == 200:
        data = res.json()
        console.print(f"[bold green]Success![/] API Token authenticated. Logged in as [bold]{data.get('name')}[/].")
    else:
        client.clear_token()
        console.print("[bold red]Authentication Failed:[/] The provided token is invalid or expired.")


@cli.command()
def logout():
    """Revokes active API key and clears local configuration."""
    if not client.load_token():
        console.print("[yellow]You are not currently logged in.[/]")
        return
        
    response = client.logout()
    if response.status_code == 200:
        console.print("[bold green]Success![/] Local token cleared and session revoked on server.")
    else:
        console.print("[bold yellow]Warning:[/] Failed to revoke token on server. Local configuration cleared anyway.")


@cli.command()
@click.option('--name', prompt='Full Name', help='User full name')
@click.option('--email', prompt='Email Address', help='User email')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Password key')
def register(name, email, password):
    """Creates a new multi-user account on ExpenseWise."""
    response = client.register(name, email, password)
    if response.status_code == 201:
        console.print("[bold green]Success![/] Account created. Run [bold green]expensewise-cli login[/] to authenticate.")
    else:
        err_msg = response.json().get('message', 'Registration failed.')
        console.print(f"[bold red]Error:[/] {err_msg}")


@cli.command(name='change-password')
@click.option('--current-password', prompt=True, hide_input=True, help='Current password')
@click.option('--new-password', prompt=True, hide_input=True, confirmation_prompt=True, help='New password')
def change_password(current_password, new_password):
    """Changes password securely via the REST API."""
    check_login()
    console.print("Updating password on server...")
    response = client.change_password(current_password, new_password)
    if response.status_code == 200:
        console.print("[bold green]Success![/] Your password has been changed successfully.")
    else:
        err = response.json().get('message', 'Failed to update password.')
        console.print(f"[bold red]Error:[/] {err}")


@cli.command()
def profile():
    """Displays active user profile settings."""
    check_login()
    response = client.get_profile()
    if response.status_code == 200:
        data = response.json()
        table = Table(title="User Account Details", title_style="bold magenta")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Name", data.get('name'))
        table.add_row("Username", data.get('username'))
        table.add_row("Email", data.get('email'))
        table.add_row("Default Currency", data.get('default_currency'))
        table.add_row("Admin Status", "Administrator" if data.get('is_admin') else "Standard User")
        table.add_row("Joined On", data.get('created_at').split('T')[0])
        console.print(table)
    else:
        console.print("[bold red]Failed to load profile details.[/]")


# ==============================================================================
# EXPENSE MANAGEMENT COMMANDS
# ==============================================================================

@cli.command(name='list')
@click.option('--search', default='', help='Search description or payee')
@click.option('--category', default='', help='Filter category')
@click.option('--start-date', default='', help='Format: YYYY-MM-DD')
@click.option('--end-date', default='', help='Format: YYYY-MM-DD')
def list_expenses(search, category, start_date, end_date):
    """Displays user's expenses in a neat table with interactive pagination."""
    check_login()
    
    page = 1
    while True:
        response = client.list_expenses(page=page, search=search, category=category, start_date=start_date, end_date=end_date)
        if response.status_code != 200:
            console.print("[bold red]Failed to fetch expenses.[/]")
            break
            
        data = response.json()
        expenses = data.get('expenses', [])
        default_currency = data.get('default_currency', 'USD')
        symbol = get_currency_symbol(default_currency)
        
        if not expenses:
            console.print("[yellow]No records found.[/]")
            break
            
        total_pages = data.get('pagination', {}).get('total_pages', 1)
        table = Table(title=f"Expenses Ledger - Page {page} of {total_pages}")
        table.add_column("UUID / ID", style="dim", no_wrap=True)
        table.add_column("Date", style="cyan")
        table.add_column("Category", style="magenta")
        table.add_column("Payee", style="green")
        table.add_column("Amount", style="bold yellow", justify="right")
        table.add_column("Payment Mode", style="blue")
        table.add_column("Description", style="white")
        
        for exp in expenses:
            amt_str = f"{symbol}{float(exp.get('amount', 0.0)):,.2f}"
            table.add_row(
                exp.get('id'),
                exp.get('expense_date'),
                exp.get('category'),
                exp.get('payee') or '-',
                amt_str,
                exp.get('payment_mode') or '-',
                exp.get('description') or '-'
            )
            
        console.print(table)
        
        if page >= total_pages:
            console.print("[blue]End of records.[/]")
            break
            
        from rich.prompt import Prompt
        val = Prompt.ask("Press [bold green]Enter[/] for next page, or type [bold red]q[/] to quit", default='', show_default=False)
        if val.strip().lower() == 'q':
            break
        page += 1


@cli.command()
@click.option('--amount', prompt=True, type=float, help='Money spent')
@click.option('--category', prompt=True, help='Category name')
@click.option('--date-str', default=lambda: date.today().isoformat(), prompt='Date (YYYY-MM-DD)', help='Transaction date')
@click.option('--payee', default='', help='Merchant recipient')
@click.option('--mode', default='', help='Payment channel')
@click.option('--description', default='', help='Notes/Message')
def add(amount, category, date_str, payee, mode, description):
    """Adds a new expense record."""
    check_login()
    
    payee_val = payee.strip() or None
    mode_val = mode.strip() or None
    desc_val = description.strip() or None
    
    response = client.add_expense(amount, category, date_str, payee_val, mode_val, desc_val)
    if response.status_code == 201:
        console.print("[bold green]Success![/] Expense recorded successfully.")
    else:
        err = response.json().get('message', 'Validation failed.')
        console.print(f"[bold red]Failed to save expense:[/] {err}")


@cli.command()
@click.argument('uuid_str')
@click.option('--amount', type=float, help='Update amount')
@click.option('--category', help='Update category')
@click.option('--date-str', help='Update date (YYYY-MM-DD)')
@click.option('--payee', help='Update payee')
@click.option('--mode', help='Update payment mode')
@click.option('--description', help='Update description')
def update(uuid_str, amount, category, date_str, payee, mode, description):
    """Updates fields of an existing expense by UUID."""
    check_login()
    
    payload = {}
    if amount is not None:
        payload['amount'] = amount
    if category:
        payload['category'] = category
    if date_str:
        payload['expense_date'] = date_str
    if payee is not None:
        payload['payee'] = payee.strip() or None
    if mode:
        payload['payment_mode'] = mode
    if description is not None:
        payload['description'] = description.strip() or None

    if not payload:
        console.print("[yellow]No modifications specified. Specify at least one field parameter.[/]")
        return

    response = client.update_expense(uuid_str, payload)
    if response.status_code == 200:
        console.print("[bold green]Success![/] Expense record updated.")
    else:
        err = response.json().get('message', 'Update failed.')
        console.print(f"[bold red]Failed to update:[/] {err}")


@cli.command()
@click.argument('uuid_str')
def delete(uuid_str):
    """Deletes an expense record by UUID."""
    check_login()
    
    if not click.confirm("Are you sure you want to delete this expense?"):
        return
        
    response = client.delete_expense(uuid_str)
    if response.status_code == 200:
        console.print("[bold green]Success![/] Expense record deleted.")
    else:
        err = response.json().get('message', 'Failed to delete record.')
        console.print(f"[bold red]Error:[/] {err}")


# ==============================================================================
# CATEGORY MANAGEMENT COMMANDS
# ==============================================================================

@cli.command(name='list-categories')
def list_categories():
    """Lists all user expense categories."""
    check_login()
    res = client.list_categories()
    if res.status_code == 200:
        categories = res.json()
        table = Table(title="Expense Categories")
        table.add_column("UUID", style="dim", max_width=12)
        table.add_column("Category Name", style="bold cyan")
        table.add_column("Color Badge", style="white")
        
        for c in categories:
            table.add_row(c.get('id'), c.get('name'), f"[background {c.get('color')}]  [/] {c.get('color')}")
        console.print(table)
    else:
        console.print("[bold red]Failed to retrieve categories.[/]")


@cli.command(name='add-category')
@click.option('--name', prompt=True, help='Category name')
@click.option('--color', default='#475569', help='HEX color code')
def add_category(name, color):
    """Adds a custom category."""
    check_login()
    res = client.add_category(name, color)
    if res.status_code == 201:
        console.print("[bold green]Success![/] Custom category created successfully.")
    else:
        console.print(f"[bold red]Failed to create:[/] {res.json().get('message', 'Invalid parameters.')}")


@cli.command(name='update-category')
@click.argument('uuid_str')
@click.option('--name', help='Category name')
@click.option('--color', help='HEX color code')
def update_category(uuid_str, name, color):
    """Updates parameters of a category by UUID."""
    check_login()
    res = client.update_category(uuid_str, name, color)
    if res.status_code == 200:
        console.print("[bold green]Success![/] Category details updated.")
    else:
        console.print(f"[bold red]Failed to update:[/] {res.json().get('message', 'Modification error.')}")


@cli.command(name='delete-category')
@click.argument('uuid_str')
def delete_category(uuid_str):
    """Deletes a custom category by UUID."""
    check_login()
    if not click.confirm("Are you sure you want to delete this category?"):
        return
    res = client.delete_category(uuid_str)
    if res.status_code == 200:
        console.print("[bold green]Success![/] Category deleted.")
    else:
        console.print(f"[bold red]Error:[/] {res.json().get('message', 'Deletion denied.')}")


# ==============================================================================
# PAYMENT METHOD MANAGEMENT COMMANDS
# ==============================================================================

@cli.command(name='list-payments')
def list_payments():
    """Lists all user payment channels."""
    check_login()
    res = client.list_payment_methods()
    if res.status_code == 200:
        pms = res.json()
        table = Table(title="Payment Channels")
        table.add_column("UUID", style="dim", max_width=12)
        table.add_column("Payment Mode", style="bold blue")
        table.add_column("Color Badge", style="white")
        
        for pm in pms:
            table.add_row(pm.get('id'), pm.get('name'), f"[background {pm.get('color')}]  [/] {pm.get('color')}")
        console.print(table)
    else:
        console.print("[bold red]Failed to retrieve payment channels.[/]")


@cli.command(name='add-payment')
@click.option('--name', prompt=True, help='Payment channel name')
@click.option('--color', default='#475569', help='HEX color code')
def add_payment(name, color):
    """Adds a custom payment channel."""
    check_login()
    res = client.add_payment_method(name, color)
    if res.status_code == 201:
        console.print("[bold green]Success![/] Custom payment method created successfully.")
    else:
        console.print(f"[bold red]Failed to create:[/] {res.json().get('message', 'Invalid parameters.')}")


@cli.command(name='update-payment')
@click.argument('uuid_str')
@click.option('--name', help='Payment method name')
@click.option('--color', help='HEX color code')
def update_payment(uuid_str, name, color):
    """Updates parameters of a payment channel by UUID."""
    check_login()
    res = client.update_payment_method(uuid_str, name, color)
    if res.status_code == 200:
        console.print("[bold green]Success![/] Payment channel details updated.")
    else:
        console.print(f"[bold red]Failed to update:[/] {res.json().get('message', 'Modification error.')}")


@cli.command(name='delete-payment')
@click.argument('uuid_str')
def delete_payment(uuid_str):
    """Deletes a custom payment method by UUID."""
    check_login()
    if not click.confirm("Are you sure you want to delete this payment method?"):
        return
    res = client.delete_payment_method(uuid_str)
    if res.status_code == 200:
        console.print("[bold green]Success![/] Payment method deleted.")
    else:
        console.print(f"[bold red]Error:[/] {res.json().get('message', 'Deletion denied.')}")


# ==============================================================================
# BUDGET PLANNING COMMANDS
# ==============================================================================

@cli.command(name='budget-show')
@click.option('--month', default='', help='Target month (YYYY-MM)')
def budget_show(month):
    """Displays budgets vs actual spending comparison for target month."""
    check_login()
    res = client.get_budget(month)
    if res.status_code == 200:
        data = res.json()
        target_month = data.get('month')
        
        # Load profile for symbol
        p_res = client.get_profile()
        currency = p_res.json().get('default_currency', 'USD') if p_res.status_code == 200 else 'USD'
        symbol = get_currency_symbol(currency)
        
        table = Table(title=f"Allowance Tracker - {target_month}")
        table.add_column("Category", style="bold cyan")
        table.add_column("Budgeted Limit", style="yellow", justify="right")
        table.add_column("Actual Spent", style="magenta", justify="right")
        table.add_column("Usage Progress Bar", style="white")
        table.add_column("Status / Left", style="white")
        
        for item in data.get('categories', []):
            b_val = item.get('budgeted')
            s_val = item.get('spent')
            pct = item.get('pct', 0)
            
            b_str = f"{symbol}{b_val:,.2f}" if b_val > 0 else "-"
            s_str = f"{symbol}{s_val:,.2f}"
            
            # Progress bar
            bar_len = min(15, int((pct / 100) * 15)) if b_val > 0 else 0
            bar = "█" * bar_len + "░" * (15 - bar_len)
            
            if b_val > 0:
                is_over = s_val > b_val
                if is_over:
                    status = f"[bold red]Over limit by {symbol}{(s_val - b_val):,.2f} ({pct}%)[/]"
                    bar_style = f"[red]{bar}[/]"
                else:
                    status = f"[green]Left: {symbol}{(b_val - s_val):,.2f} ({pct}%)[/]"
                    bar_style = f"[green]{bar}[/]"
            else:
                status = "[dim]No spending limit[/]"
                bar_style = f"[dim]{bar}[/]"
                
            table.add_row(
                item.get('category'),
                b_str,
                s_str,
                bar_style,
                status
            )
            
        console.print(table)
        
        # Display Totals Panel
        t_bud = data.get('total_budgeted', 0.0)
        t_sp = data.get('total_spent', 0.0)
        rem_str = f"{symbol}{(t_bud - t_sp):,.2f}" if t_bud >= t_sp else f"-{symbol}{(t_sp - t_bud):,.2f}"
        rem_style = "green" if t_bud >= t_sp else "bold red"
        
        console.print(Panel(
            f"Total Budgeted Limit : [bold yellow]{symbol}{t_bud:,.2f}[/]\n"
            f"Total Actual Spent   : [bold magenta]{symbol}{t_sp:,.2f}[/]\n"
            f"Remaining Allowance  : [{rem_style}]{rem_str}[/]",
            title="Monthly Budget Summary",
            border_style="cyan"
        ))
    else:
        console.print(f"[bold red]Failed to retrieve budget statistics:[/] {res.json().get('message', 'Error')}")


@cli.command(name='budget-suggest')
@click.option('--month', default='', help='Target month (YYYY-MM)')
def budget_suggest(month):
    """Displays category budget recommendations based on past 3-month spending."""
    check_login()
    res = client.get_budget(month)
    if res.status_code == 200:
        data = res.json()
        target_month = data.get('month')
        months_hist = data.get('months_history', 3)
        
        p_res = client.get_profile()
        currency = p_res.json().get('default_currency', 'USD') if p_res.status_code == 200 else 'USD'
        symbol = get_currency_symbol(currency)

        table = Table(title=f"Intelligent Recommendations for {target_month} (Based on past {months_hist}-month history)")
        table.add_column("Category", style="bold cyan")
        table.add_column("Suggested Limit", style="bold green", justify="right")
        table.add_column("Current Configured Limit", style="yellow", justify="right")
        
        for item in data.get('categories', []):
            table.add_row(
                item.get('category'),
                f"{symbol}{item.get('suggested'):,.2f}",
                f"{symbol}{item.get('budgeted'):,.2f}" if item.get('budgeted') > 0 else "-"
            )
        console.print(table)
        console.print("\n[dim]Note: You can apply these suggestions using `expensewise-cli budget-set`.[/]")
    else:
        console.print("[bold red]Failed to load suggestions.[/]")


@cli.command(name='budget-set')
@click.option('--month', prompt=True, help='Target month (YYYY-MM)')
@click.option('--category', prompt=True, help='Category name')
@click.option('--amount', prompt=True, type=float, help='Target budget amount')
def budget_set(month, category, amount):
    """Sets or updates budget limits for a category."""
    check_login()
    payload = {category: amount}
    res = client.update_budget(month, payload)
    if res.status_code == 200:
        console.print(f"[bold green]Success![/] Budget limit of [bold]{amount:.2f}[/] set for [bold]{category}[/] ({month}).")
    else:
        console.print(f"[bold red]Failed to update budget:[/] {res.json().get('message', 'Error')}")


@cli.command(name='budget-delete')
@click.argument('month')
@click.argument('category')
def budget_delete(month, category):
    """Deletes/clears budget limits for a category."""
    check_login()
    if not click.confirm(f"Are you sure you want to clear budget limits for {category} ({month})?"):
        return
    payload = {category: ""}
    res = client.update_budget(month, payload)
    if res.status_code == 200:
        console.print(f"[bold green]Success![/] Budget limits for {category} ({month}) have been cleared.")
    else:
        console.print("[bold red]Error clearing budget limit details.[/]")


# ==============================================================================
# DATA PORTABILITY COMMANDS (IMPORT / EXPORT)
# ==============================================================================

@cli.command(name='export-backup')
@click.argument('output_file', type=click.Path(writable=True))
def export_backup(output_file):
    """Exports entire data backup to a local JSON v2.0 file."""
    check_login()
    console.print("Downloading backup data from server...")
    url = f"{client.api_url}/v1/export"
    res = requests.get(url, headers=client.get_headers())
    if res.status_code == 200:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(res.json(), f, indent=2)
        console.print(f"[bold green]Success![/] Backup written to [bold cyan]{output_file}[/].")
    else:
        console.print(f"[bold red]Failed to export:[/] {res.json().get('message', 'Access denied.')}")


@cli.command(name='import-backup')
@click.argument('input_file', type=click.Path(exists=True))
def import_backup(input_file):
    """Restores/merges database from a local JSON v2.0 backup file."""
    check_login()
    if not click.confirm("WARNING: This will overwrite or merge categories, payment methods, and expenses. Proceed?"):
        return
    
    console.print(f"Reading backup from {input_file}...")
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
    except Exception as e:
        console.print(f"[bold red]Failed to read JSON:[/] {str(e)}")
        return
        
    console.print("Uploading and restoring backup on server...")
    url = f"{client.api_url}/v1/import"
    res = requests.post(url, json=backup_data, headers=client.get_headers())
    if res.status_code == 200:
        console.print("[bold green]Success![/] Database backup restored and synced successfully on server.")
    else:
        console.print(f"[bold red]Failed to restore:[/] {res.json().get('message', 'Server error.')}")


# ==============================================================================
# ANALYTICS & TERMINAL CHARTS
# ==============================================================================

@cli.command()
def analytics():
    """Displays rollups, MoM comparison changes, and projections in the terminal."""
    check_login()
    
    sum_res = client.get_analytics_summary()
    fore_res = client.get_analytics_forecast()
    trend_res = client.get_analytics_trends()
    
    if sum_res.status_code != 200 or fore_res.status_code != 200 or trend_res.status_code != 200:
        console.print("[bold red]Failed to retrieve analytics metrics.[/]")
        return
        
    sum_data = sum_res.json()
    metrics = sum_data.get('metrics', {})
    comp = sum_data.get('comparison', {})
    forecast = fore_res.json().get('predicted_next_month_spending', 0.0)
    trends = trend_res.json().get('category_distribution', {})
    default_currency = sum_data.get('default_currency', 'USD')
    symbol = get_currency_symbol(default_currency)
    
    # 1. Metric Cards panel
    metrics_panel = (
        f"Total Filtered Spending : [bold yellow]{symbol}{metrics.get('total_spending', 0.0):,.2f}[/]\n"
        f"Daily Averaged Spending : [bold magenta]{symbol}{metrics.get('daily_average', 0.0):,.2f}[/]\n"
        f"Transactions Count      : [bold]{metrics.get('total_count', 0)}[/]"
    )
    console.print(Panel(metrics_panel, title="Spending Metrics Overview", border_style="cyan"))
    
    # 2. Month-over-Month Comparison Card
    diff = comp.get('difference', 0.0)
    pct = comp.get('percentage_change', 0.0)
    sign = "+" if diff > 0 else "-"
    style = "bold red" if diff > 0 else "bold green"
    comp_panel = (
        f"Budget Difference : [{style}]{sign}{symbol}{abs(diff):,.2f}[/]\n"
        f"Percentage Change : [{style}]{pct:,.1f}% change MoM[/]"
    )
    console.print(Panel(comp_panel, title="Vs. Previous Month", border_style="cyan"))

    # 3. Forecast
    console.print(Panel(
        f"Projected Spending Next Month: [bold yellow]{symbol}{forecast:,.2f}[/]",
        title="Linear Regression Spending Forecast",
        border_style="magenta"
    ))


@cli.command(name='chart')
@click.option('--category', default='', help='Filter by category name')
@click.option('--start-date', default='', help='Format: YYYY-MM-DD')
@click.option('--end-date', default='', help='Format: YYYY-MM-DD')
def display_chart(category, start_date, end_date):
    """Generates colorful terminal-based spending charts."""
    check_login()
    
    page = 1
    all_expenses = []
    while True:
        res = client.list_expenses(page=page, search='', category=category, start_date=start_date, end_date=end_date)
        if res.status_code != 200:
            break
        data = res.json()
        exps = data.get('expenses', [])
        if not exps:
            break
        all_expenses.extend(exps)
        total_pages = data.get('pagination', {}).get('total_pages', 1)
        if page >= total_pages:
            break
        page += 1

    if not all_expenses:
        console.print("[yellow]No expense data found in the specified range.[/]")
        return

    # Group expenses by category
    group_data = {}
    for exp in all_expenses:
        cat = exp.get('category', 'Other')
        amt = float(exp.get('amount', 0.0))
        group_data[cat] = group_data.get(cat, 0.0) + amt

    total_spent = sum(group_data.values())
    
    # Render chart title
    p_res = client.get_profile()
    currency = p_res.json().get('default_currency', 'USD') if p_res.status_code == 200 else 'USD'
    symbol = get_currency_symbol(currency)

    console.print(Panel(
        f"[bold]Spending Distribution Chart[/]\n"
        f"Total Filtered Spending: [bold green]{symbol}{total_spent:,.2f}[/]",
        border_style="cyan"
    ))

    # Plot custom terminal bar/pie representation
    max_cat_len = max(len(c) for c in group_data.keys()) if group_data else 10
    sorted_groups = sorted(group_data.items(), key=lambda x: x[1], reverse=True)
    
    max_amt = max(group_data.values()) if group_data else 1.0

    for cat, amt in sorted_groups:
        pct = (amt / total_spent) * 100 if total_spent > 0 else 0
        # Normalize to a bar width of 30 characters
        bar_len = int((amt / max_amt) * 30) if max_amt > 0 else 0
        bar = "█" * bar_len + "░" * (30 - bar_len)
        
        color_map = ["red", "green", "yellow", "blue", "magenta", "cyan"]
        idx = sorted_groups.index((cat, amt)) % len(color_map)
        color = color_map[idx]
        
        console.print(
            f"[bold {color}]{cat.ljust(max_cat_len)}[/] | "
            f"[{color}]{bar}[/] | "
            f"[bold]{symbol}{amt:,.2f}[/] ({pct:.1f}%)"
        )


if __name__ == '__main__':
    cli()
