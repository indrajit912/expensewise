# ExpenseWise

**ExpenseWise** is a production-ready, personal finance management platform built using Flask, SQLAlchemy, and Python 3.13+. It features multi-user accounts, secure credentials handling, interactive visual dashboards via Chart.js, Pandas-based analytics and linear regressions, bulk CSV sheet uploads, and a versioned REST API alongside an installable terminal CLI client.

---

## Technical Stack & Features
* **Backend:** Flask using the Application Factory Pattern.
* **Database & ORM:** SQLAlchemy supporting SQLite in development and easy migration to PostgreSQL in production, with Alembic (Flask-Migrate) versioning.
* **Security:** Enforced headers via Flask-Talisman, rate limiting via Flask-Limiter, CSRF token verification (Flask-WTF), and salted password hashing (Werkzeug).
* **Analytics Engine:** Pandas aggregation for averages, aggregates, and linear regression forecasts for next-month spending projection.
* **Import Services:**
  1. Automated import service mapping standard category names from legacy CLI JSON formats.
  2. CSV file uploading with column mapper validation and visual previews before database insert operations.
* **REST API (v1):** Token authentication endpoints backed by Marshmallow validation.
* **Terminal CLI:** Rich-enabled installable CLI client `expense-cli` that interfaces with the API.

---

## Directory Architecture

```text
expensewise/
│
├── app/
│   ├── api/                 # Versioned API routes & schemas
│   ├── auth/                # Sign-up, Sign-in, and recovery routes/forms
│   ├── dashboard/           # Visual UI metrics, settings
│   ├── expenses/            # CRUD listings, filters, CSV staging/import UI
│   ├── analytics/           # Deep analytics indicators & forecast graphs
│   ├── cli/                 # Custom Flask CLI commands
│   ├── services/            # Pandas calculations, JSON/CSV parser helpers
│   ├── models/              # User, Expense, and APIToken structures
│   ├── static/              # Stylesheets, JS scripts
│   ├── templates/           # Base layout, sub-views, error screens
│   └── extensions.py        # Centralized Flask extensions (db, mail, etc.)
│
├── cli/                     # Installable Click CLI tool package
├── migrations/              # Database migration scripts
├── tests/                   # Pytest test suites (auth, API, service math)
├── instance/                # Local database location (git-ignored)
├── requirements/            # Splitted packages dependencies
├── config.py                # Setup parameters configuration
├── manage.py                # Main entry point runner
└── README.md
```

---

## Fresh Installation and First-Time Setup

This guide details how to reset the application to a clean state and run a fresh installation.

### 1. Prerequisites & Environment Setup
* **Python Version:** Python 3.13+ (tested on Python 3.14)
* **Virtual Environment:** Set up a clean virtual environment and install packages.
  ```bash
  # Navigate to the project root
  cd .\expensewise

  # Create virtual environment
  python -m venv venv

  # Activate virtual environment
  # Windows PowerShell:
  .\venv\Scripts\Activate.ps1
  # Command Prompt (cmd):
  .\venv\Scripts\activate.bat
  # Linux/macOS:
  source venv/bin/activate

  # Install required dependencies
  pip install -r requirements.txt -r requirements/dev.txt
  ```

### 2. Environment Variables Configuration
Copy the `.env.example` template to `.env` and fill in the required parameters:
```bash
# On Windows PowerShell
Copy-Item .env.example .env
# On Linux/macOS/cmd
cp .env.example .env
```

#### Required Variables in `.env`
* `SECRET_KEY`: Keep empty or specify a random secret. Note: Leaving it blank falls back to a dynamically generated secret key (via `secrets.token_hex(32)`).
* `DATABASE_URL`: Leave blank or commented out to use the default SQLite database path (`instance/expensewise.db`). To use a custom database (e.g. PostgreSQL), specify the connection URL.
* `HERMES_BASE_URL` / `HERMES_API_KEY` / `HERMES_EMAILBOT_ID`: API details for the Hermes email service.
* `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_EMAIL`: Details for seeding the default super-admin user (e.g., `ghostrix` and `indrajitghosh912@gmail.com`).

#### Crucial Fix: SQLAlchemy Empty String Parsing Bug
When environment variables in `.env` are defined but left blank following the equals sign (e.g., `DATABASE_URL=` or `SECRET_KEY=`), standard fallback logic using `os.environ.get('DATABASE_URL') or fallback` fails because the library `python-dotenv` loads empty values as empty strings (`""`) rather than `None`.
To prevent SQLAlchemy from raising `ArgumentError: Could not parse rfc1738 URL from ""`, the system configuration evaluates `os.environ.get('DATABASE_URL')` and checks if it contains non-whitespace content using `.strip()`. If the string is empty, it correctly triggers the fallback database path:
```python
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.strip():
    SQLALCHEMY_DATABASE_URI = db_url
else:
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'instance' / 'expensewise.db'}"
```

### 3. Database Migration Sequence
If you are performing a completely clean install, delete any existing SQLite files and migration files:
```bash
# Remove old db and migrations if resetting
Remove-Item -Recurse -Force instance/expensewise.db, migrations
```
Then, execute the Alembic schema initialization and migration process:
```bash
# Initialize migration repository
flask db init

# Generate initial migration script
flask db migrate -m "Initial migration"

# Apply migration to database
flask db upgrade
```

### 4. Non-Interactive System Bootstrapping
To create the super-admin account `ghostrix` and import all legacy expenses from the old CLI project (`C:\Users\indra\...\ExpenseTrackerCLI\database.json`), execute the custom CLI command.
You can run it in a **non-interactive** environment (such as CI/CD pipelines or automated shell scripts) by specifying the password directly via the `--password` / `-p` option:
```bash
flask bootstrap-system --password "YourAdminPasswordHere123!"
```
*Note:* The password must meet security criteria: at least 8 characters, containing uppercase, lowercase, numbers, and special characters.

### 5. Running the Application
To launch the Flask development server:
```bash
python manage.py
```
The application will be available at `http://127.0.0.1:5000/`.

---

## Interactive Command Line Interface (CLI)

The CLI tool is located inside the `cli/` directory and can be installed into your active virtual environment.

### Installation
```bash
pip install -e cli
```
*This binds the command name `expense-cli` to your terminal.*

### Usage Flow
1. **Register a new account:**
   ```bash
   expense-cli register
   ```

2. **Exchange credentials for a secure local access token:**
   ```bash
   expense-cli login
   ```

3. **Query your expense ledger (includes pagination prompts):**
   ```bash
   expense-cli list
   ```
   *Supports optional query filters:* `expense-cli list --category Food --search Starbucks`

4. **Add a transaction:**
   ```bash
   expense-cli add --amount 12.50 --category Food --payee "Coffee Shop" --description "Latte and muffin"
   ```

5. **Update fields of a transaction by UUID:**
   ```bash
   expense-cli update <UUID> --amount 15.00 --description "Revised latte price"
   ```

6. **Delete a transaction:**
   ```bash
   expense-cli delete <UUID>
   ```

7. **Review terminal-based financial insights:**
   ```bash
   expense-cli analytics
   ```

---

## API Endpoints (v1)

All data-altering requests accept and return JSON and require a secure Bearer token passed in the Authorization header.

### Authentication
* `POST /api/v1/auth/register` - Create user.
* `POST /api/v1/auth/login` - Obtain token (`expires_at` returned).
* `POST /api/v1/auth/logout` - Revoke token.

### Expense Operations
* `GET /api/v1/expenses` - Paginated expense lists (filters: `search`, `category`, `start_date`, `end_date`, `sort_by`, `order`).
* `POST /api/v1/expenses` - Store an expense.
* `GET /api/v1/expenses/<uuid>` - Retrieve details.
* `PUT /api/v1/expenses/<uuid>` - Update fields.
* `DELETE /api/v1/expenses/<uuid>` - Revoke transaction.

### Backups & Import
* `GET /api/v1/export?format=csv|json` - Download database backups.
* `POST /api/v1/import` - Bulk load database JSON or multipart CSV files.

### Visual Analytics
* `GET /api/v1/analytics/summary` - Aggregates, growth totals, and daily average.
* `GET /api/v1/analytics/trends` - Category allocations and historical logs.
* `GET /api/v1/analytics/forecast` - OLS Regression next-month projection rate.

---

## Running Unit & Integration Tests

We enforce high test coverage. You can execute our pytest suite:
```bash
python -m pytest --cov=app tests/
```

---

## Owner & Maintainer

* **Author:** [Indrajit Ghosh](https://indrajitghosh.onrender.com)
* **GitHub Profile:** [@indrajit912](https://github.com/indrajit912)
* **Designation:** Postdoc Researcher, IIT Kanpur, India

