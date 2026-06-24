import click
from datetime import date
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
        console.print("[bold red]Error:[/] You are not logged in. Run [bold green]expense-cli login[/] first.")
        raise click.Abort()
    return token


@click.group()
def cli():
    """ExpenseWise CLI - Personal Financial administration directly from your terminal."""
    pass


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
        console.print("[bold green]Success![/] Account created. Run [bold green]expense-cli login[/] to authenticate.")
    else:
        err_msg = response.json().get('message', 'Registration failed.')
        console.print(f"[bold red]Error:[/] {err_msg}")


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
        response = client.list_expenses(page, search, category, start_date, end_date)
        if response.status_code != 200:
            console.print("[bold red]Failed to fetch expenses.[/]")
            break
            
        data = response.json()
        items = data.get('expenses', [])
        meta = data.get('pagination', {})
        default_currency = data.get('default_currency', 'USD')
        symbol = get_currency_symbol(default_currency)
        
        if not items:
            if page == 1:
                console.print("[yellow]No expenses found matching the criteria.[/]")
            else:
                console.print("[yellow]No further expenses available.[/]")
            break

        # Render rich table
        table = Table(title=f"Expenses Registry (Page {meta['current_page']} of {meta['total_pages']})")
        table.add_column("UUID", style="dim", width=12, overflow="ellipsis")
        table.add_column("Date", style="cyan")
        table.add_column("Category", style="green")
        table.add_column("Payee", style="magenta")
        table.add_column("Description", style="white")
        table.add_column("Mode", style="yellow")
        table.add_column("Amount", justify="right", style="bold")

        for exp in items:
            amount_val = float(exp['amount']) if exp.get('amount') is not None else 0.0
            table.add_row(
                exp['id'],
                exp['expense_date'],
                exp['category'],
                exp['payee'] or '-',
                exp['description'] or '-',
                exp['payment_mode'] or '-',
                f"{symbol}{amount_val:,.2f}"
            )

        console.print(table)
        
        # Paginate command loop
        if meta['has_next']:
            val = click.prompt("Press [bold green]Enter[/] for next page, or type [bold red]q[/] to quit", default='', show_default=False)
            if val.strip().lower() == 'q':
                break
            page += 1
        else:
            console.print("[blue]End of records.[/]")
            break


@cli.command()
@click.option('--amount', prompt=True, type=float, help='Money spent')
@click.option('--category', prompt=True, help='Budget category (e.g. Food, Rent, or custom)')
@click.option('--date-str', default=lambda: date.today().isoformat(), prompt='Date (YYYY-MM-DD)', help='Transaction date')
@click.option('--payee', default='', help='Merchant recipient')
@click.option('--mode', default='', help='Payment channel (e.g. Cash, Card, Phonepe, or custom)')
@click.option('--description', default='', help='Notes/Message')
def add(amount, category, date_str, payee, mode, description):
    """Adds a new expense record."""
    check_login()
    
    # Clean fields
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
        f"[bold]Total Spent (30 Days):[/] [bold green]{symbol}{metrics.get('total_spending', 0.0):,.2f}[/]\n"
        f"[bold]Daily Average Spent:[/]  [bold cyan]{symbol}{metrics.get('daily_average', 0.0):,.2f}[/]\n"
        f"[bold]Top Expense Category:[/]  [bold yellow]{metrics.get('top_category', 'None')}[/] ({symbol}{metrics.get('top_category_amount', 0.0):,.2f})"
    )
    console.print(Panel(metrics_panel, title="Spending Summary (Past 30 Days)", expand=False))
    
    # 2. Month-over-Month growth
    diff = comp.get('difference', 0.0)
    pct = comp.get('percentage_change', 0.0)
    direction = "Increase" if diff > 0 else "Decrease"
    color = "red" if diff > 0 else "green"
    
    console.print(f"\n[bold]Month-Over-Month Comparison:[/] [bold {color}]{direction} of {symbol}{abs(diff):,.2f} ({pct:.1f}%)[/]")
    console.print(f"[bold]Most Volatile Category:[/]      [bold magenta]{comp.get('most_increased_category', 'N/A')}[/] (expanded by {symbol}{comp.get('most_increased_amount', 0.0):,.2f})")
    
    # 3. Forecast
    console.print(Panel(f"Estimated next month spending: [bold green]{symbol}{forecast:,.2f}[/]\nMethod: Least-squares regression analysis over history.", title="Predictive Analytics Forecast", expand=False))
    
    # 4. Category share table
    if trends:
        table = Table(title="Category Allocation (All Time)")
        table.add_column("Category", style="green")
        table.add_column("Spent Amount", justify="right", style="bold")
        
        for cat, amt in trends.items():
            table.add_row(cat, f"{symbol}{amt:,.2f}")
        console.print("\n", table)
