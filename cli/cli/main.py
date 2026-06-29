import click
import os
import re
import json
import requests
from datetime import date, datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from cli.client import APIClient

class StyledConsole(Console):
    def print(self, *args, **kwargs):
        if args and isinstance(args[0], str):
            msg = args[0]
            # Replace tags with modern themed icons
            msg = msg.replace("[bold green]Success![/]", "[bold green]✔ Success![/]")
            msg = msg.replace("[bold red]Error:[/]", "[bold red]✘ Error:[/]")
            msg = msg.replace("[bold red]Login Failed:[/]", "[bold red]✘ Login Failed:[/]")
            msg = msg.replace("[bold red]Authentication Failed:[/]", "[bold red]✘ Authentication Failed:[/]")
            msg = msg.replace("[bold red]Status Error:[/]", "[bold red]✘ Status Error:[/]")
            msg = msg.replace("[bold red]Failed to save expense:[/]", "[bold red]✘ Failed to save expense:[/]")
            msg = msg.replace("[bold red]Failed to update:[/]", "[bold red]✘ Failed to update:[/]")
            msg = msg.replace("[bold red]Failed to retrieve budget statistics:[/]", "[bold red]✘ Failed to retrieve budget statistics:[/]")
            msg = msg.replace("[bold red]Failed to update budget:[/]", "[bold red]✘ Failed to update budget:[/]")
            msg = msg.replace("[bold red]Failed to export:[/]", "[bold red]✘ Failed to export:[/]")
            msg = msg.replace("[bold red]Failed to read JSON:[/]", "[bold red]✘ Failed to read JSON:[/]")
            msg = msg.replace("[bold red]Failed to restore:[/]", "[bold red]✘ Failed to restore:[/]")
            msg = msg.replace("[bold red]Failed to retrieve spending summary metrics.[/]", "[bold red]✘ Failed to retrieve spending summary metrics.[/]")
            msg = msg.replace("[bold red]Failed to retrieve chart analytics metrics.[/]", "[bold red]✘ Failed to retrieve chart analytics metrics.[/]")
            msg = msg.replace("[bold red]Failed to retrieve categories.[/]", "[bold red]✘ Failed to retrieve categories.[/]")
            msg = msg.replace("[bold red]Failed to retrieve payment channels.[/]", "[bold red]✘ Failed to retrieve payment channels.[/]")
            msg = msg.replace("[bold red]Failed to create:[/]", "[bold red]✘ Failed to create:[/]")
            msg = msg.replace("[bold red]Failed to load profile details.[/]", "[bold red]✘ Failed to load profile details.[/]")
            msg = msg.replace("[bold red]Failed to fetch expenses.[/]", "[bold red]✘ Failed to fetch expenses.[/]")
            msg = msg.replace("[bold red]Failed to load suggestions.[/]", "[bold red]✘ Failed to load suggestions.[/]")
            msg = msg.replace("[bold red]Error clearing budget limit details.[/]", "[bold red]✘ Error clearing budget limit details.[/]")
            msg = msg.replace("[bold red]Status Error:[/]", "[bold red]✘ Status Error:[/]")
            msg = msg.replace("[bold red]Login Failed:[/]", "[bold red]✘ Login Failed:[/]")
            msg = msg.replace("[bold red]Authentication Failed:[/]", "[bold red]✘ Authentication Failed:[/]")
            msg = msg.replace("[bold red]Error:[/]", "[bold red]✘ Error:[/]")
            msg = msg.replace("[bold yellow]Warning:[/]", "[bold yellow]⚠ Warning:[/]")
            msg = msg.replace("[bold yellow]Status:[/]", "[bold yellow]ℹ Status:[/]")
            msg = msg.replace("[yellow]Note:", "[yellow]⚠ Note:")
            msg = msg.replace("[yellow]You are not", "[yellow]⚠ You are not")
            new_args = (msg,) + args[1:]
            super().print(*new_args, **kwargs)
        else:
            super().print(*args, **kwargs)

console = StyledConsole()
client = APIClient()

def print_welcome_banner(title="ExpenseWise Terminal Portal"):
    banner_text = (
        "[bold bright_cyan]"
        "  Developer: Indrajit\n"
        "  GitHub Profile: https://github.com/indrajit912\n"
        "  Project Repo:   https://github.com/indrajit912/expensewise\n"
        "  Web App URL:    https://expensewise.pythonanywhere.com"
        "[/]"
    )
    console.print(Panel(banner_text, title=f"[bold green] {title} [/]", border_style="bright_cyan", expand=False))

def show_custom_help():
    banner = r"""[bold bright_cyan]
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │ ███████╗██╗  ██╗██████╗ ███████╗███╗   ██╗███████╗███████╗██╗    ██╗██╗███████╗███████╗ │
 │ ██╔════╝╚██╗██╔╝██╔══██╗██╔════╝████╗  ██║██╔════╝██╔════╝██║    ██║██║██╔════╝██╔════╝ │
 │ █████╗   ╚███╔╝ ██████╔╝█████╗  ██╔██╗ ██║███████╗█████╗  ██║ █╗ ██║██║███████╗█████╗   │
 │ ██╔══╝   ██╔██╗ ██╔═══╝ ██╔══╝  ██║╚██╗██║╚════██║██╔══╝  ██║███╗██║██║╚════██║██╔══╝   │
 │ ███████╗██╔╝ ██╗██║     ███████╗██║ ╚████║███████║███████╗╚███╔███╔╝██║███████║███████╗ │
 │ ╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═══╝╚══════╝╚══════╝ ╚══╝╚══╝ ╚═╝╚══════╝╚══════╝ │
 │                                     EXPENSEWISE CLI                                    │
 └────────────────────────────────────────────────────────────────────────────────────────┘
[/]"""
    console.print(banner, justify="center")
    console.print("\n[bold white]Secure personal finance administration directly from your terminal.[/]")
    console.print("[dim white]All actions communicate securely with the versioned REST API.[/]\n")
    
    def print_section_table(title, commands):
        table = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
        table.add_column("Command", style="bold green", width=25)
        table.add_column("Description", style="white")
        for cmd, desc in commands:
            table.add_row(cmd, desc)
        console.print(Panel(table, title=f"[bold cyan]{title}[/]", border_style="dim blue", title_align="left"))

    print_section_table("Session & Security", [
        ("login", "Authenticate secure CLI session"),
        ("logout", "Log out and clear local session token"),
        ("register", "Create a new multi-user account"),
        ("change-password", "Securely update account password"),
        ("profile", "Display active user account details"),
        ("auth", "Manage credentials and verify active token status")
    ])

    print_section_table("Expense Management", [
        ("list", "View expenses table with pagination"),
        ("add", "Record a new expense transaction"),
        ("update", "Update fields of an existing expense by UUID"),
        ("delete", "Remove an expense record by UUID")
    ])

    print_section_table("Custom Metadata", [
        ("list-categories", "View all expense categories and badges"),
        ("add-category", "Create a new custom expense category"),
        ("update-category", "Edit category details by UUID"),
        ("delete-category", "Delete custom category by UUID"),
        ("list-payments", "View all payment channels and badges"),
        ("add-payment", "Create a new payment channel"),
        ("update-payment", "Edit payment channel details by UUID"),
        ("delete-payment", "Delete custom payment channel by UUID")
    ])

    print_section_table("Budgeting & Planning", [
        ("budget-show", "Compare monthly budget limits vs actual spending"),
        ("budget-suggest", "Recommend budget limits based on 3-month history"),
        ("budget-set", "Set/update budget limits for a category"),
        ("budget-delete", "Delete/clear budget limits for a category")
    ])

    print_section_table("Analytics & Reports", [
        ("summary", "Display range-filtered spending metrics"),
        ("analytics", "Alias for 'summary' command"),
        ("chart", "Plot distribution and trends using terminal charts")
    ])

    print_section_table("Portability & Config", [
        ("export-backup", "Download full database backup as JSON"),
        ("import-backup", "Upload and restore/merge database from JSON backup"),
        ("config", "Manage local CLI server base URL configuration"),
        ("self-update", "Update the CLI client to the latest version")
    ])

    examples = (
        "[bold yellow]Login and verify status:[/]\n"
        "  expensewise-cli login\n"
        "  expensewise-cli auth status\n\n"
        "[bold yellow]Manage expenses:[/]\n"
        "  expensewise-cli add --amount 150.0 --category Food\n"
        "  expensewise-cli list --category Food --start-date 2026-01-01\n"
        "  expensewise-cli update <uuid> --amount 145.5\n\n"
        "[bold yellow]Budget tracking:[/]\n"
        "  expensewise-cli budget-set --month 2026-06 --category Rent --amount 1500\n"
        "  expensewise-cli budget-show --month 2026-06\n\n"
        "[bold yellow]Analytics and exports:[/]\n"
        "  expensewise-cli summary --category-wise --start-date 2026-05-01\n"
        "  expensewise-cli chart --start-date 2026-05-01\n"
        "  expensewise-cli export-backup my_backup.json"
    )
    console.print(Panel(examples, title="[bold cyan]Common Usage Examples[/]", border_style="dim blue", title_align="left"))

    resources = (
        "[bold white]GitHub Profile:[/]      https://github.com/indrajit912\n"
        "[bold white]Project Repository:[/]  https://github.com/indrajit912/expensewise\n"
        "[bold white]Web Application:[/]     https://expensewise.pythonanywhere.com"
    )
    console.print(Panel(resources, title="[bold cyan]Project Resources[/]", border_style="dim blue", title_align="left"))

    console.print("\n[bold bright_cyan]Developed & Maintained by Indrajit | Postdoc Researcher, IIT Kanpur, India[/]", justify="center")

def show_config_help():
    console.print("[bold bright_cyan]ExpenseWise CLI - Local Configuration Options[/]\n")
    console.print("Manage local configuration options for the CLI client (e.g. API URL).\n")
    
    table = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
    table.add_column("Command", style="bold green", width=25)
    table.add_column("Description", style="white")
    table.add_row("show", "Displays the currently configured API server URL and active state.")
    table.add_row("set-url", "Updates the stored API server URL (e.g. http://localhost:5000/api).")
    table.add_row("reset", "Resets the configured URL to the default (http://localhost:5000/api).")
    
    console.print(Panel(table, title="[bold cyan]Configuration Commands[/]", border_style="dim blue", title_align="left"))

def show_auth_help():
    console.print("[bold bright_cyan]ExpenseWise CLI - Session Authentication Options[/]\n")
    console.print("Manage CLI client session authentication and token credentials.\n")
    
    table = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
    table.add_column("Command", style="bold green", width=25)
    table.add_column("Description", style="white")
    table.add_row("status", "Displays active session login and credential details.")
    table.add_row("token", "Securely prompts for and saves a web-generated API token.")
    
    console.print(Panel(table, title="[bold cyan]Authentication Commands[/]", border_style="dim blue", title_align="left"))

SUBCOMMAND_EXAMPLES = {
    'self-update': (
        "  expensewise-cli self-update\n"
        "  # Interactively upgrades the CLI tool from GitHub using pip or pipx."
    ),
    'login': (
        "  expensewise-cli login\n"
        "  # Prompts for authentication method (Password or API token) and connects to the active Server URL."
    ),
    'logout': (
        "  expensewise-cli logout\n"
        "  # Clears local token credentials.\n\n"
        "  expensewise-cli logout --revoke\n"
        "  # Clears local credentials and contacts the server to invalidate the token database record."
    ),
    'register': (
        "  expensewise-cli register\n"
        "  # Launches interactive registration prompt asking for Name, Email, and Password."
    ),
    'change-password': (
        "  expensewise-cli change-password\n"
        "  # Updates password for authenticated account. Securely confirms current and new values."
    ),
    'profile': (
        "  expensewise-cli profile\n"
        "  # Displays user name, email, currency choice, admin status, and date joined."
    ),
    'list': (
        "  expensewise-cli list\n"
        "  # Lists all expenses.\n\n"
        "  expensewise-cli list --category Food --start-date 2026-01-01\n"
        "  # Lists expenses filtered by category and date range."
    ),
    'add': (
        "  expensewise-cli add --amount 45.90 --category Shopping\n"
        "  # Creates a new expense entry.\n\n"
        "  expensewise-cli add --amount 12.0 --category Transport --payee 'Uber' --mode 'Credit Card'"
    ),
    'update': (
        "  expensewise-cli update <uuid> --amount 50.0\n"
        "  # Modifies amount of the target transaction.\n\n"
        "  expensewise-cli update <uuid> --description 'Updated description'"
    ),
    'delete': (
        "  expensewise-cli delete <uuid>\n"
        "  # Deletes expense with matching UUID (requires user confirmation)."
    ),
    'list-categories': (
        "  expensewise-cli list-categories\n"
        "  # Displays user-customized category definitions and active color codes."
    ),
    'add-category': (
        "  expensewise-cli add-category --name 'Groceries' --color '#22c55e'\n"
        "  # Registers a new category with color code."
    ),
    'update-category': (
        "  expensewise-cli update-category <uuid> --name 'Supermarket'\n"
        "  # Updates category details by UUID."
    ),
    'delete-category': (
        "  expensewise-cli delete-category <uuid>\n"
        "  # Deletes category with matching UUID (requires user confirmation)."
    ),
    'list-payments': (
        "  expensewise-cli list-payments\n"
        "  # Lists all custom payment channels."
    ),
    'add-payment': (
        "  expensewise-cli add-payment --name 'Debit Card' --color '#3b82f6'\n"
        "  # Registers a new payment channel."
    ),
    'update-payment': (
        "  expensewise-cli update-payment <uuid> --name 'Bank Transfer'\n"
        "  # Updates payment channel name/color by UUID."
    ),
    'delete-payment': (
        "  expensewise-cli delete-payment <uuid>\n"
        "  # Deletes payment channel with matching UUID."
    ),
    'budget-show': (
        "  expensewise-cli budget-show\n"
        "  # Shows current month's allowance tracking.\n\n"
        "  expensewise-cli budget-show --month 2026-06\n"
        "  # Shows detailed category limits vs actual spending with progress bars for June 2026."
    ),
    'budget-suggest': (
        "  expensewise-cli budget-suggest --month 2026-06\n"
        "  # Recommends budget allocations for June 2026 based on past 3-month spending patterns."
    ),
    'budget-set': (
        "  expensewise-cli budget-set --month 2026-06 --category Rent --amount 1500\n"
        "  # Configures Rent allowance limit to 1500 for June 2026."
    ),
    'budget-delete': (
        "  expensewise-cli budget-delete 2026-06 Rent\n"
        "  # Clears Rent limit configuration for June 2026."
    ),
    'summary': (
        "  expensewise-cli summary --start-date 2026-01-01 --end-date 2026-05-31\n"
        "  # Displays total spending, count, average transactions, and daily average.\n\n"
        "  expensewise-cli summary --category-wise --start-date 2026-01-01\n"
        "  # Shows spending breakdown and ASCII shares chart by category."
    ),
    'analytics': (
        "  expensewise-cli analytics --category-wise --start-date 2026-01-01\n"
        "  # Alias command for summary breakdown."
    ),
    'chart': (
        "  expensewise-cli chart --start-date 2026-01-01 --end-date 2026-03-31\n"
        "  # Visualizes spending shares distribution via a colorful Unicode block chart."
    ),
    'export-backup': (
        "  expensewise-cli export-backup backup.json\n"
        "  # Downloads all expenses, categories, and payment methods to backup.json."
    ),
    'import-backup': (
        "  expensewise-cli import-backup backup.json\n"
        "  # Restores and merges backup.json database payload to active REST server."
    ),
    'show': (
        "  expensewise-cli config show\n"
        "  # Displays resolution source, active server URL, environment variable overrides, and stored config settings."
    ),
    'set-url': (
        "  expensewise-cli config set-url https://expensewise.pythonanywhere.com/api\n"
        "  # Configures default API base URL used for server REST communications."
    ),
    'reset': (
        "  expensewise-cli config reset\n"
        "  # Removes custom API server URL from local configuration storage."
    ),
    'status': (
        "  expensewise-cli auth status\n"
        "  # Verifies active session token validity with server and prints login credential details."
    ),
    'token': (
        "  expensewise-cli auth token\n"
        "  # Securely prompts (hidden input) and stores a web-generated API token locally."
    ),
}

class CustomHelpCommand(click.Command):
    def get_help(self, ctx):
        cmd_name = self.name
        cmd_desc = self.help or ""
        
        console.print(f"[bold bright_cyan]ExpenseWise CLI - Command Help[/]")
        console.print(f"Usage: [bold green]expensewise-cli {cmd_name}[/] [options]\n")
        
        console.print(Panel(cmd_desc, title=f"[bold cyan]Description[/]", border_style="dim blue", title_align="left"))
        
        options = []
        arguments = []
        for param in self.params:
            if isinstance(param, click.Option):
                opt_names = ", ".join(param.opts)
                if param.secondary_opts:
                    opt_names += " / " + ", ".join(param.secondary_opts)
                
                if param.is_flag:
                    type_str = ""
                else:
                    type_str = f"<{param.type.name.upper()}>" if hasattr(param.type, 'name') else ""
                required_str = " [red][Required][/]" if param.required else " [dim][Optional][/]"
                default_str = f" [yellow](Default: {param.default})[/]" if param.default is not None and not isinstance(param.default, click.utils.LazyType) and not callable(param.default) else ""
                
                desc = (param.help or "") + required_str + default_str
                options.append((f"{opt_names} {type_str}", desc))
            elif isinstance(param, click.Argument):
                arg_name = param.name.upper()
                required_str = " [red][Required][/]" if param.required else " [dim][Optional][/]"
                arguments.append((arg_name, f"Target argument.{required_str}"))
                
        if arguments:
            table_args = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
            table_args.add_column("Argument", style="bold yellow", width=25)
            table_args.add_column("Description", style="white")
            for arg_name, desc in arguments:
                table_args.add_row(arg_name, desc)
            console.print(Panel(table_args, title="[bold cyan]Arguments[/]", border_style="dim blue", title_align="left"))
            
        if options:
            table_opts = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
            table_opts.add_column("Option", style="bold green", width=25)
            table_opts.add_column("Description", style="white")
            for opt_names, desc in options:
                table_opts.add_row(opt_names, desc)
            console.print(Panel(table_opts, title="[bold cyan]Options[/]", border_style="dim blue", title_align="left"))
            
        examples = SUBCOMMAND_EXAMPLES.get(cmd_name, "")
        if examples:
            console.print(Panel(examples, title="[bold cyan]Usage Examples[/]", border_style="dim blue", title_align="left"))
            
        ctx.exit()

class CustomHelpGroup(click.Group):
    def get_help(self, ctx):
        if self.name == 'config':
            show_config_help()
            ctx.exit()
        elif self.name == 'auth':
            show_auth_help()
            ctx.exit()
        else:
            show_custom_help()
            ctx.exit()



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
    import sys
    symbol = CURRENCY_SYMBOLS.get(currency_code or 'USD', currency_code or '$')
    try:
        encoding = sys.stdout.encoding or 'utf-8'
        symbol.encode(encoding)
        return symbol
    except Exception:
        # Fallback to standard ASCII
        if currency_code == 'INR':
            return 'Rs. '
        elif currency_code == 'EUR':
            return 'EUR '
        elif currency_code == 'GBP':
            return 'GBP '
        elif currency_code == 'JPY':
            return 'JPY '
        return currency_code + ' '

def check_login():
    """Helper to check if user has authenticated."""
    token = client.load_token()
    if not token:
        console.print("[bold red]Error:[/] You are not logged in. Run [bold green]expensewise-cli login[/] first.")
        raise click.Abort()
    return token


@click.group(cls=CustomHelpGroup)
def cli():
    """ExpenseWise CLI - Personal Financial administration directly from your terminal.
    
    All actions communicate securely with the versioned REST API.
    """
    pass


# ==============================================================================
# CONFIGURATION COMMANDS
# ==============================================================================

@cli.group(name='config', cls=CustomHelpGroup)
def config_group():
    """Manage local configuration options for the CLI client (e.g. API URL)."""
    pass

@config_group.command(name='show', cls=CustomHelpCommand)
def config_show():
    """Displays the currently configured API server URL and active state."""
    env_url = os.environ.get('EXPENSEWISE_API_URL')
    stored_url = None
    if os.path.exists(client.config_file_path):
        try:
            with open(client.config_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                stored_url = data.get('api_url')
        except Exception:
            pass

    console.print("[bold cyan]ExpenseWise CLI Configuration Settings[/]")
    
    # Show active URL
    active_url = client.api_url
    console.print(f"Active Server URL  : [bold green]{active_url}[/]")
    
    # Detail resolve source
    if env_url:
        console.print("Resolution Source  : [bold yellow]Environment Variable Override (EXPENSEWISE_API_URL)[/]")
    elif stored_url:
        console.print("Resolution Source  : [bold green]Stored Local Configuration[/]")
    else:
        console.print("Resolution Source  : [bold dim]Default Local Fallback[/]")

    console.print(f"Stored Config URL  : [cyan]{stored_url or 'None (Using default localhost)'}[/]")
    console.print(f"Env Variable URL   : [cyan]{env_url or 'Not Set'}[/]")

@config_group.command(name='set-url', cls=CustomHelpCommand)
@click.argument('url')
def config_set_url(url):
    """Updates the stored API server URL (e.g. https://expensewise.pythonanywhere.com/api)."""
    if not url.startswith(('http://', 'https://')):
        console.print("[bold red]Error:[/] The URL must start with http:// or https://")
        raise click.Abort()

    cleaned_url = url.rstrip('/')
    if client.save_config_url(cleaned_url):
        console.print(f"[bold green]Success![/] Configured API Server URL updated to: [bold]{cleaned_url}[/]")
    else:
        console.print("[bold red]Error:[/] Failed to write the configuration to local storage.")

@config_group.command(name='reset', cls=CustomHelpCommand)
def config_reset():
    """Resets the configured URL to the default (http://localhost:5000/api)."""
    if client.reset_config_url():
        console.print("[bold green]Success![/] Configured URL removed from local storage.")
    else:
        console.print("[yellow]Note: No custom URL was configured in local storage.[/]")
    
    console.print(f"Resolved Server URL: [bold green]{client.api_url}[/]")


# ==============================================================================
# USER MANAGEMENT COMMANDS
# ==============================================================================

@cli.command(cls=CustomHelpCommand)
def login():
    """Authenticates the terminal client session securely with the server."""
    print_welcome_banner("ExpenseWise Authentication Portal")
    console.print(Panel(
        "Select an Authentication Method:\n"
        "[bold green]1)[/] Email & Password credentials exchange\n"
        "[bold green]2)[/] API Token secure entry",
        title="ExpenseWise Authentication Portal",
        border_style="cyan"
    ))
    
    from rich.prompt import Prompt
    choice = Prompt.ask("Choose login method", choices=["1", "2"], default="1")
    
    if choice == "1":
        email = click.prompt("Email Address or Username", type=str)
        password = click.prompt("Password", hide_input=True, type=str)
        
        console.print(f"Connecting to [bold cyan]{client.api_url}[/]...")
        response = client.login(email, password)
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('token')
            client.save_token(token)
            console.print(f"[bold green]Success![/] Welcome back, [bold]{data['user']['name']}[/]. Access token saved securely.")
        else:
            err_msg = response.json().get('message', 'Check your credentials.')
            console.print(f"[bold red]Login Failed:[/] {err_msg}")
            
    elif choice == "2":
        token = Prompt.ask("Enter API Token", password=True)
        token = token.strip()
        if not token:
            console.print("[bold red]Error:[/] API Token cannot be empty.")
            return
            
        console.print("Verifying API token with server...")
        client.save_token(token)
        res = client.get_profile()
        if res.status_code == 200:
            data = res.json()
            console.print(f"[bold green]Success![/] API Token authenticated. Logged in as [bold]{data.get('name')}[/].")
        else:
            client.clear_token()
            console.print("[bold red]Authentication Failed:[/] The provided token is invalid or expired.")


@cli.group(name='auth', cls=CustomHelpGroup)
def auth():
    """Manage CLI client session authentication and token credentials."""
    pass


@auth.command(name='status', cls=CustomHelpCommand)
def auth_status():
    """Displays active session login and credential details."""
    token = client.load_token()
    if not token:
        console.print("[bold yellow]Status:[/] Unauthenticated. Run [bold green]expensewise-cli login[/] to connect.")
        return
        
    res = client.get_profile()
    if res.status_code == 200:
        data = res.json()
        masked = f"{token[:6]}...{token[-4:]}" if len(token) > 10 else "****"
        
        table = Table(title="Authentication Credentials Status", title_style="bold green", border_style="cyan")
        table.add_column("Field", style="cyan")
        table.add_column("Details", style="white")
        table.add_row("User Profile", data.get('name'))
        table.add_row("Email Address", data.get('email'))
        table.add_row("Active Token", masked)
        table.add_row("Server Host", client.api_url)
        table.add_row("Session State", "[bold green]Active & Verified[/]")
        console.print(table)
    else:
        masked = f"{token[:6]}...{token[-4:]}" if len(token) > 10 else "****"
        console.print("[bold red]Status Error:[/] Stored token is invalid, expired, or rejected by server.")
        console.print(f"Stored Token Hint: [dim]{masked}[/]")
        console.print("Run [bold yellow]expensewise-cli login[/] to authenticate again.")


@auth.command(name='token', cls=CustomHelpCommand)
def auth_token():
    """Securely prompts for and saves a web-generated API token."""
    from rich.prompt import Prompt
    token = Prompt.ask("Enter API Token", password=True)
    token = token.strip()
    if not token:
        console.print("[bold red]Error:[/] Token value cannot be empty.")
        return
        
    console.print("Verifying API token with server...")
    client.save_token(token)
    res = client.get_profile()
    if res.status_code == 200:
        data = res.json()
        console.print(f"[bold green]Success![/] API Token verified and saved securely. Logged in as [bold]{data.get('name')}[/].")
    else:
        client.clear_token()
        console.print("[bold red]Authentication Failed:[/] The provided token is invalid or expired.")


@cli.command(cls=CustomHelpCommand)
@click.option('--revoke', is_flag=True, help='Explicitly revoke/delete the active token on the server as well.')
def logout(revoke):
    """Logs out by clearing the local session token. Optionally revokes the token on the server."""
    if not client.load_token():
        console.print("[yellow]You are not currently logged in.[/]")
        return
        
    if revoke:
        console.print("Contacting server to revoke and invalidate the active token...")
        response = client.logout()
        if response.status_code == 200:
            console.print("[bold green]Success![/] Local token cleared and session revoked on the server.")
        else:
            console.print("[bold yellow]Warning:[/] Failed to revoke token on server (it may already be invalid). Local token cleared anyway.")
    else:
        client.clear_token()
        console.print("[bold green]Success![/] Local session token cleared from your machine. Stored API token remains valid on the server.")


@cli.command(cls=CustomHelpCommand)
@click.option('--name', prompt='Full Name', help='User full name')
@click.option('--email', prompt='Email Address', help='User email')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Password key')
def register(name, email, password):
    """Creates a new multi-user account on ExpenseWise."""
    print_welcome_banner("ExpenseWise User Registration")
    response = client.register(name, email, password)
    if response.status_code == 201:
        console.print("[bold green]Success![/] Account created. Run [bold green]expensewise-cli login[/] to authenticate.")
    else:
        err_msg = response.json().get('message', 'Registration failed.')
        console.print(f"[bold red]Error:[/] {err_msg}")


@cli.command(name='change-password', cls=CustomHelpCommand)
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


@cli.command(cls=CustomHelpCommand)
def profile():
    """Displays active user profile settings."""
    check_login()
    response = client.get_profile()
    if response.status_code == 200:
        data = response.json()
        table = Table(title="User Account Details", title_style="bold magenta", border_style="magenta")
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

@cli.command(name='list', cls=CustomHelpCommand)
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
        table = Table(title=f"Expenses Ledger - Page {page} of {total_pages}", border_style="cyan")
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


@cli.command(cls=CustomHelpCommand)
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


@cli.command(cls=CustomHelpCommand)
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


@cli.command(cls=CustomHelpCommand)
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

@cli.command(name='list-categories', cls=CustomHelpCommand)
def list_categories():
    """Lists all user expense categories."""
    check_login()
    res = client.list_categories()
    if res.status_code == 200:
        categories = res.json()
        table = Table(title="Expense Categories", border_style="magenta")
        table.add_column("UUID", style="dim", no_wrap=True)
        table.add_column("Category Name", style="bold cyan")
        table.add_column("Color Badge", style="white")
        
        for c in categories:
            table.add_row(c.get('id'), c.get('name'), f"[background {c.get('color')}]  [/] {c.get('color')}")
        console.print(table)
    else:
        console.print("[bold red]Failed to retrieve categories.[/]")


@cli.command(name='add-category', cls=CustomHelpCommand)
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


@cli.command(name='update-category', cls=CustomHelpCommand)
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


@cli.command(name='delete-category', cls=CustomHelpCommand)
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

@cli.command(name='list-payments', cls=CustomHelpCommand)
def list_payments():
    """Lists all user payment channels."""
    check_login()
    res = client.list_payment_methods()
    if res.status_code == 200:
        pms = res.json()
        table = Table(title="Payment Channels", border_style="blue")
        table.add_column("UUID", style="dim", no_wrap=True)
        table.add_column("Payment Mode", style="bold blue")
        table.add_column("Color Badge", style="white")
        
        for pm in pms:
            table.add_row(pm.get('id'), pm.get('name'), f"[background {pm.get('color')}]  [/] {pm.get('color')}")
        console.print(table)
    else:
        console.print("[bold red]Failed to retrieve payment channels.[/]")


@cli.command(name='add-payment', cls=CustomHelpCommand)
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


@cli.command(name='update-payment', cls=CustomHelpCommand)
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


@cli.command(name='delete-payment', cls=CustomHelpCommand)
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
# ==================@cli.command(name='budget-show', cls=CustomHelpCommand)
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
        
        table = Table(title=f"Allowance Tracker - {target_month}", border_style="cyan")
        table.add_column("Category", style="bold cyan")
        table.add_column("Budgeted Limit", style="yellow", justify="right")
        table.add_column("Actual Spent", style="magenta", justify="right")
        table.add_column("Usage Progress Bar", style="white")
        table.add_column("Status / Left", style="white")
        
        try:
            import sys
            "█░".encode(sys.stdout.encoding or 'utf-8')
            bar_char_filled = "█"
            bar_char_empty = "░"
        except Exception:
            bar_char_filled = "#"
            bar_char_empty = "-"

        for item in data.get('categories', []):
            b_val = item.get('budgeted')
            s_val = item.get('spent')
            pct = item.get('pct', 0)
            
            b_str = f"{symbol}{b_val:,.2f}" if b_val > 0 else "-"
            s_str = f"{symbol}{s_val:,.2f}"
            
            # Progress bar
            bar_len = min(15, int((pct / 100) * 15)) if b_val > 0 else 0
            bar = bar_char_filled * bar_len + bar_char_empty * (15 - bar_len)
            
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


@cli.command(name='budget-suggest', cls=CustomHelpCommand)
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

        table = Table(title=f"Intelligent Recommendations for {target_month} (Based on past {months_hist}-month history)", border_style="green")
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


@cli.command(name='budget-set', cls=CustomHelpCommand)
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


@cli.command(name='budget-delete', cls=CustomHelpCommand)
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

@cli.command(name='export-backup', cls=CustomHelpCommand)
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


@cli.command(name='import-backup', cls=CustomHelpCommand)
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


@cli.command(name='self-update', cls=CustomHelpCommand)
def self_update():
    """Allows users to update the CLI to the latest version directly from GitHub."""
    console.print(Panel(
        "[bold cyan]ExpenseWise CLI Self-Updater[/]\n\n"
        "This utility will pull the latest version of the CLI client directly from "
        "the official GitHub repository and install it on your system.",
        title="[bold green]Self-Update[/]",
        border_style="cyan"
    ))
    
    if not click.confirm("Do you want to proceed with the update?"):
        console.print("[yellow]Update canceled by user.[/]")
        return
        
    console.print(Panel(
        "Select your original installation method:\n"
        "[bold green]1)[/] pip (standard pip install)\n"
        "[bold green]2)[/] pipx (isolated application run)\n"
        "[bold green]3)[/] Show manual installation commands",
        title="Installation Method Selection",
        border_style="cyan"
    ))
    
    from rich.prompt import Prompt
    choice = Prompt.ask("Choose method", choices=["1", "2", "3"], default="1")
    
    repo_url = "git+https://github.com/indrajit912/expensewise.git#subdirectory=cli"
    
    if choice == "3":
        console.print("\n[bold cyan]Manual Installation Commands:[/]")
        console.print("[bold yellow]For pip users:[/]")
        console.print(f"  pip install --upgrade {repo_url}\n")
        console.print("[bold yellow]For pipx users:[/]")
        console.print(f"  pipx install --force {repo_url}\n")
        return

    import subprocess
    import sys
    
    if choice == "1":
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", repo_url]
        cmd_str = f"{sys.executable} -m pip install --upgrade {repo_url}"
    else:
        cmd = ["pipx", "install", "--force", repo_url]
        cmd_str = f"pipx install --force {repo_url}"
        
    console.print(f"\n[*] Active command: [bold green]{cmd_str}[/]")
    
    try:
        from rich.status import Status
        with console.status("[bold green]Upgrading package from GitHub... (this may take a few seconds)[/]"):
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
        if result.returncode == 0:
            console.print("\n[bold green]✔ Success![/] ExpenseWise CLI has been successfully updated.")
            console.print("[bold yellow]Note:[/] Please restart your active terminal session to apply the changes.")
        else:
            console.print("\n[bold red]✘ Error:[/] Update command failed with exit code [bold]{}[/]".format(result.returncode))
            console.print(Panel(result.stderr or result.stdout or "No error output returned.", title="Command Output", border_style="red"))
            console.print("\n[yellow]Alternative: Try running the command manually or check your Git installation.[/]")
    except Exception as e:
        console.print(f"\n[bold red]Error:[/] Failed to execute update subprocess: {str(e)}")
        console.print("[yellow]Please run the update command manually.[/]")


# ==============================================================================
@cli.command(name='summary', cls=CustomHelpCommand)
@click.option('--start-date', default='', help='Format: YYYY-MM-DD')
@click.option('--end-date', default='', help='Format: YYYY-MM-DD')
@click.option('--category', default='', help='Filter by category name')
@click.option('--category-wise', is_flag=True, help='Display category-wise spending breakdown table')
@click.pass_context
def display_summary(ctx, start_date, end_date, category, category_wise):
    """Displays spending summaries over a specified date range and breakdown."""
    check_login()
    
    res = client.get_analytics_summary(category=category, start_date=start_date, end_date=end_date)
    if res.status_code != 200:
        console.print("[bold red]Failed to retrieve spending summary metrics.[/]")
        return
        
    data = res.json()
    metrics = data.get('metrics', {})
    default_currency = data.get('default_currency', 'USD')
    symbol = get_currency_symbol(default_currency)
    
    is_custom = data.get('custom', False)
    
    if is_custom:
        start_str = data.get('start_date') or start_date or 'Beginning'
        end_str = data.get('end_date') or end_date or 'Present'
        title = f"Spending Summary: {start_str} to {end_str}"
        
        metrics_panel = (
            f"Total Spending       : [bold yellow]{symbol}{metrics.get('total_spending', 0.0):,.2f}[/]\n"
            f"Daily Average        : [bold magenta]{symbol}{metrics.get('daily_average', 0.0):,.2f}[/]\n"
            f"Average Transaction  : [bold green]{symbol}{metrics.get('average_transaction', 0.0):,.2f}[/]\n"
            f"Transactions Count   : [bold]{metrics.get('total_count', 0)}[/]"
        )
        console.print(Panel(metrics_panel, title=title, border_style="cyan"))
    else:
        metrics_panel = (
            f"Total Filtered Spending : [bold yellow]{symbol}{metrics.get('total_spending', 0.0):,.2f}[/]\n"
            f"Daily Averaged Spending : [bold magenta]{symbol}{metrics.get('daily_average', 0.0):,.2f}[/]\n"
            f"Transactions Count      : [bold]{metrics.get('total_count', 0)}[/]"
        )
        console.print(Panel(metrics_panel, title="Spending Metrics Overview (Last 30 Days)", border_style="cyan"))
        
        comp = data.get('comparison', {})
        diff = comp.get('difference', 0.0)
        pct = comp.get('percentage_change', 0.0)
        sign = "+" if diff > 0 else "-"
        style = "bold red" if diff > 0 else "bold green"
        comp_panel = (
            f"Budget Difference : [{style}]{sign}{symbol}{abs(diff):,.2f}[/]\n"
            f"Percentage Change : [{style}]{pct:,.1f}% change MoM[/]"
        )
        console.print(Panel(comp_panel, title="Vs. Previous Month", border_style="cyan"))
        
        fore_res = client.get_analytics_forecast()
        if fore_res.status_code == 200:
            forecast = fore_res.json().get('predicted_next_month_spending', 0.0)
            console.print(Panel(
                f"Projected Spending Next Month: [bold yellow]{symbol}{forecast:,.2f}[/]",
                title="Linear Regression Spending Forecast",
                border_style="magenta"
            ))

    if category_wise:
        categories = data.get('categories', [])
        if not categories:
            console.print("[yellow]No category data available for the breakdown.[/]")
        else:
            table = Table(title="Category-wise Spending Breakdown", border_style="cyan")
            table.add_column("Category", style="bold cyan")
            table.add_column("Total Spent", style="bold yellow", justify="right")
            table.add_column("Percentage", style="bold green", justify="right")
            table.add_column("Transactions", style="white", justify="right")
            
            for item in categories:
                table.add_row(
                    item.get('category'),
                    f"{symbol}{item.get('total', 0.0):,.2f}",
                    f"{item.get('pct', 0.0):.1f}%",
                    str(item.get('count', 0))
                )
            console.print(table)
            
            # Draw spending shares block chart
            console.print("\n[bold]Spending Share Chart:[/]")
            try:
                import sys
                "█░".encode(sys.stdout.encoding or 'utf-8')
                bar_char_filled = "█"
                bar_char_empty = "░"
            except Exception:
                bar_char_filled = "#"
                bar_char_empty = "-"
                
            max_cat_len = max(len(c.get('category', '')) for c in categories) if categories else 10
            max_amt = max(c.get('total', 0.0) for c in categories) if categories else 1.0
            
            for item in categories:
                cat = item.get('category', 'Other')
                amt = item.get('total', 0.0)
                pct = item.get('pct', 0.0)
                
                bar_len = int((amt / max_amt) * 30) if max_amt > 0 else 0
                bar = bar_char_filled * bar_len + bar_char_empty * (30 - bar_len)
                
                color_map = ["red", "green", "yellow", "blue", "magenta", "cyan"]
                idx = categories.index(item) % len(color_map)
                color = color_map[idx]
                
                console.print(
                    f"[bold {color}]{cat.ljust(max_cat_len)}[/] | "
                    f"[{color}]{bar}[/] | "
                    f"[bold]{symbol}{amt:,.2f}[/] ({pct:.1f}%)"
                )


@cli.command(name='analytics', cls=CustomHelpCommand)
@click.option('--start-date', default='', help='Format: YYYY-MM-DD')
@click.option('--end-date', default='', help='Format: YYYY-MM-DD')
@click.option('--category', default='', help='Filter by category name')
@click.option('--category-wise', is_flag=True, help='Display category-wise spending breakdown table')
@click.pass_context
def display_analytics_alias(ctx, start_date, end_date, category, category_wise):
    """Alias for 'summary' command. Displays spending summaries and breakdowns."""
    ctx.invoke(display_summary, start_date=start_date, end_date=end_date, category=category, category_wise=category_wise)


@cli.command(name='chart', cls=CustomHelpCommand)
@click.option('--category', default='', help='Filter by category name')
@click.option('--start-date', default='', help='Format: YYYY-MM-DD')
@click.option('--end-date', default='', help='Format: YYYY-MM-DD')
def display_chart(category, start_date, end_date):
    """Generates colorful terminal-based spending charts."""
    check_login()
    
    res = client.get_analytics_trends(category=category, start_date=start_date, end_date=end_date)
    if res.status_code != 200:
        console.print("[bold red]Failed to retrieve chart analytics metrics.[/]")
        return
        
    data = res.json()
    group_data = data.get('category_distribution', {})
    
    if not group_data:
        console.print("[yellow]No expense data found in the specified range.[/]")
        return
        
    total_spent = sum(group_data.values())
    
    currency = data.get('default_currency', 'USD')
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

    try:
        import sys
        "█░".encode(sys.stdout.encoding or 'utf-8')
        bar_char_filled = "█"
        bar_char_empty = "░"
    except Exception:
        bar_char_filled = "#"
        bar_char_empty = "-"

    for cat, amt in sorted_groups:
        pct = (amt / total_spent) * 100 if total_spent > 0 else 0
        # Normalize to a bar width of 30 characters
        bar_len = int((amt / max_amt) * 30) if max_amt > 0 else 0
        bar = bar_char_filled * bar_len + bar_char_empty * (30 - bar_len)
        
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
