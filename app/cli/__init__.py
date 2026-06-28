# Flask Custom CLI blueprint / commands module
# Exposes helper hooks that run directly on 'flask' command contexts.

import os
import sys
import json
import click
import shutil
import secrets
import subprocess
from decimal import Decimal
from datetime import datetime, timezone
from flask.cli import with_appcontext
from app.extensions import db
from app.models.user import User
from app.models.expense import Expense, Category, PaymentMethod
from app.services.encryption_service import EncryptionService
from app.services.audit_service import AuditService

def validate_password_strength(password: str):
    """Enforces identical password requirements to the frontend registration forms."""
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    import re
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "Password must contain at least one special character."
    return None

@click.command('bootstrap-system')
@click.option('--password', '-p', default=None, help="Password for super administrator 'ghostrix'.")
@with_appcontext
def bootstrap_system_command(password):
    """Initializes the database, creates the ghostrix super admin, and imports legacy CLI data."""
    click.echo("Starting system bootstrap process...")
    
    # 1. Check if the ghostrix account already exists
    existing_admin = User.query.filter((User.username == 'ghostrix') | (User.email == 'indrajitghosh912@gmail.com')).first()
    if existing_admin:
        click.echo("Error: System is already bootstrapped. The admin account 'ghostrix' already exists.")
        return

    # 2. Prompt for password securely if not provided via option
    if not password:
        password = click.prompt("Enter password for super administrator 'ghostrix'", hide_input=True, confirmation_prompt=True)
    pw_err = validate_password_strength(password)
    if pw_err:
        raise click.ClickException(pw_err)

    # 3. Check legacy JSON file
    json_path = r"C:\Users\indra\Documents\hello_world\ExpenseTrackerCLI\database.json"
    import_data = False
    if os.path.exists(json_path):
        click.echo(f"Legacy database file found at {json_path}.")
        import_data = True
    else:
        click.echo(f"Warning: Legacy database file not found at {json_path}.")
        if not click.confirm("Do you want to proceed with creating the admin account only?"):
            click.echo("Bootstrap cancelled.")
            return

    # 4. Generate keys and create admin user
    click.echo("Creating super admin account...")
    fernet_key = EncryptionService.generate_fernet_key()
    EncryptionService.set_override_key(fernet_key)

    admin = User(
        name="Indrajit Ghosh",
        username="ghostrix",
        email="indrajitghosh912@gmail.com",
        is_active=True,
        is_email_verified=True,
        is_admin=True,
        is_super_admin=True,
        default_currency="INR"
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.flush() # Populate admin.id
    
    admin.seed_defaults()
    
    # Cache user categories and payment methods
    user_categories = set(c.name for c in Category.query.filter_by(user_id=admin.id).all())
    user_payment_methods = set(pm.name for pm in PaymentMethod.query.filter_by(user_id=admin.id).all())

    imported_count = 0
    if import_data:
        click.echo("Parsing legacy JSON file and encrypting records...")
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                legacy_db = json.load(f)
            
            expenses_dict = legacy_db.get('expenses', {})
            for date_key, exp_list in expenses_dict.items():
                if not exp_list:
                    continue
                for exp in exp_list:
                    amount_val = exp.get('amount', 0.0)
                    category_name = exp.get('category', 'Others').strip()
                    payment_mode_name = exp.get('mode', 'Others').strip()
                    payee_name = exp.get('payee', '').strip()
                    description_val = exp.get('message', '').strip()
                    exp_date_str = exp.get('date', date_key)
                    
                    # Parse date string to Date object
                    try:
                        parsed_date = datetime.strptime(exp_date_str, "%b %d, %Y").date()
                    except Exception:
                        try:
                            parsed_date = datetime.strptime(date_key, "%b %d, %Y").date()
                        except Exception:
                            parsed_date = datetime.now(timezone.utc).date()
                            
                    # Add category/payment method to user configuration if missing
                    if category_name and category_name not in user_categories:
                        db.session.add(Category(user_id=admin.id, name=category_name))
                        user_categories.add(category_name)
                    if payment_mode_name and payment_mode_name not in user_payment_methods:
                        db.session.add(PaymentMethod(user_id=admin.id, name=payment_mode_name))
                        user_payment_methods.add(payment_mode_name)
                        
                    # Create encrypted expense record
                    new_expense = Expense(
                        user_id=admin.id,
                        amount=Decimal(str(amount_val)),
                        category=category_name,
                        payment_mode=payment_mode_name,
                        payee=payee_name,
                        description=description_val,
                        expense_date=parsed_date,
                        original_amount=Decimal(str(amount_val)),
                        original_currency='INR',
                        conversion_rate=Decimal('1.0000'),
                        converted_amount=Decimal(str(amount_val))
                    )
                    db.session.add(new_expense)
                    imported_count += 1
                    
        except Exception as e:
            db.session.rollback()
            raise click.ClickException(f"Error parsing legacy database.json: {str(e)}")

    # Commit all changes securely
    db.session.commit()
    
    # Log audit entry
    AuditService.log(
        action="System Bootstrap",
        details=f"Bootstrapped super admin ghostrix and imported {imported_count} legacy expenses.",
        user_id=admin.id
    )
    
    # Clear override key
    EncryptionService.clear_user_key()
    
    click.echo(f"System bootstrap complete! Admin account created successfully. Imported {imported_count} expenses.")


@click.command('create-admin')
@with_appcontext
def create_admin_command():
    """CLI tool to securely create the first system administrator."""
    click.echo("Creating a new administrator account...")
    
    # 1. Enforce that this is only used for the first administrator setup
    existing_admin = User.query.filter_by(is_admin=True).first()
    if existing_admin:
        click.echo("Error: An administrator already exists in the database. Additional administrators must be promoted via the Admin Dashboard or database directly.")
        return

    # 2. Gather account details
    name = click.prompt("Full Name", default="System Administrator")
    username = click.prompt("Username").strip().lower()
    email = click.prompt("Email Address").strip().lower()
    
    # Check if duplicate username or email exists
    if User.query.filter((User.username == username) | (User.email == email)).first():
        click.echo("Error: A user with this username or email already exists.")
        return
        
    default_currency = click.prompt("Default Currency (INR, USD, EUR, GBP, JPY, AUD, CAD)", default="USD").strip().upper()
    if default_currency not in ['INR', 'USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD']:
        click.echo("Invalid currency choice.")
        return

    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    pw_err = validate_password_strength(password)
    if pw_err:
        raise click.ClickException(pw_err)

    # 3. Create the administrator account
    fernet_key = EncryptionService.generate_fernet_key()
    EncryptionService.set_override_key(fernet_key)

    new_admin = User(
        name=name,
        username=username,
        email=email,
        is_active=True,
        is_email_verified=True,
        is_admin=True,
        is_super_admin=True, # The first admin created gets super admin status
        default_currency=default_currency
    )
    new_admin.set_password(password)
    db.session.add(new_admin)
    db.session.flush()
    
    new_admin.seed_defaults()
    db.session.commit()
    
    AuditService.log(
        action="CLI Admin Creation",
        details=f"Created first admin account {email} via CLI tool.",
        user_id=new_admin.id
    )
    
    EncryptionService.clear_user_key()
    
    click.echo(f"Administrator account '{username}' ({email}) created successfully.")


@click.command('create-guest')
@with_appcontext
def create_guest_command():
    """CLI tool to create the demo guest user securely."""
    click.echo("Checking guest demo user account...")
    
    existing_guest = User.query.filter((User.username == 'guest') | (User.email == 'guest@expensewise.local')).first()
    if existing_guest:
        click.echo("Guest demo user 'guest' already exists. Re-setting password to 'password'...")
        existing_guest.set_password('password')
        db.session.commit()
        click.echo("Guest user password updated.")
        return

    # Create the guest user
    fernet_key = EncryptionService.generate_fernet_key()
    EncryptionService.set_override_key(fernet_key)

    guest = User(
        name='Guest User',
        username='guest',
        email='guest@expensewise.local',
        is_active=True,
        is_email_verified=True,
        is_admin=False,
        default_currency='INR'
    )
    guest.set_password('password')
    db.session.add(guest)
    db.session.flush()
    
    guest.seed_defaults()
    db.session.commit()
    
    AuditService.log(
        action="CLI Guest Creation",
        details="Created guest demo user via CLI tool.",
        user_id=guest.id
    )
    
    EncryptionService.clear_user_key()
    
    click.echo("Guest demo user 'guest' (email: 'guest@expensewise.local', password: 'password') created successfully.")


@click.command('setup-project')
@with_appcontext
def setup_project_command():
    """Automates the complete first-time project setup from scratch."""
    from flask import current_app
    
    click.echo("======================================================================")
    click.echo("WARNING: This command will permanently delete your existing database,")
    click.echo("instance files, and migrations directory. All data will be lost!")
    click.echo("======================================================================")
    
    if not click.confirm("Are you sure you want to proceed and initialize the project?"):
        click.echo("Setup aborted by user. No changes were made.")
        return

    project_root = os.path.abspath(os.path.join(current_app.root_path, '..'))
    instance_path = os.path.join(project_root, 'instance')
    migrations_path = os.path.join(project_root, 'migrations')

    if os.path.exists(instance_path):
        click.echo(f"[*] Deleting {instance_path}...")
        try:
            shutil.rmtree(instance_path)
            click.echo("  [+] Deleted instance directory successfully.")
        except Exception as e:
            click.echo(f"  [-] Failed to delete instance directory: {str(e)}")
            raise click.ClickException("Setup aborted due to file system deletion failure.")
            
    if os.path.exists(migrations_path):
        click.echo(f"[*] Deleting {migrations_path}...")
        try:
            shutil.rmtree(migrations_path)
            click.echo("  [+] Deleted migrations directory successfully.")
        except Exception as e:
            click.echo(f"  [-] Failed to delete migrations directory: {str(e)}")
            raise click.ClickException("Setup aborted due to file system deletion failure.")

    steps = [
        ("Database Initialization (db init)", ["db", "init"]),
        ("Generate Initial Migration (db migrate)", ["db", "migrate", "-m", "Initial migration"]),
        ("Apply Database Migrations (db upgrade)", ["db", "upgrade"]),
        ("Bootstrap System Admin (bootstrap-system)", ["bootstrap-system"]),
        ("Create Demo Guest Account (create-guest)", ["create-guest"])
    ]

    for step_name, args in steps:
        click.echo(f"\n[*] Starting Step: {step_name}...")
        try:
            result = subprocess.run([sys.executable, "-m", "flask"] + args)
            if result.returncode != 0:
                click.echo(f"\n[-] Step Failed: {step_name} (Exit code {result.returncode})")
                raise click.ClickException(f"Setup failed at step: {step_name}.")
            else:
                click.echo(f"[+] Step Succeeded: {step_name}")
        except Exception as e:
            click.echo(f"\n[-] Step Failed: {step_name}")
            raise click.ClickException(f"Setup failed at step: {step_name} with error: {str(e)}")

    click.echo("\n======================================================================")
    click.echo("[+] Success: Project has been initialized and set up successfully!")
    click.echo("======================================================================")
