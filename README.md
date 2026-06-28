# ExpenseWise

[![Python Version](https://img.shields.io/badge/python-3.13%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Flask Framework](https://img.shields.io/badge/framework-Flask%203.0%2B-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](./LICENSE)
[![Maintenance Status](https://img.shields.io/badge/maintenance-active-emerald.svg)](#)

**ExpenseWise** is a production-ready, highly secure personal finance management platform. It features multi-user sandboxing, transparent database-level encryption at rest, rolling analytics, linear regression forecasting, dynamic monthly budget planning, and versioned developer REST APIs with an installable command-line client.

* **Maintainer:** Indrajit Ghosh
* **Role:** Math Postdoctoral Researcher, IIT Kanpur
* **Website:** [https://indrajitghosh.onrender.com](https://indrajitghosh.onrender.com)
* **GitHub Repository:** [https://github.com/indrajit912/expensewise](https://github.com/indrajit912/expensewise)
* **Live Web Application:** [https://expensewise.pythonanywhere.com](https://expensewise.pythonanywhere.com)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Features](#2-features)
3. [Screenshots](#3-screenshots-placeholder)
4. [Technology Stack](#4-technology-stack)
5. [Installation](#5-installation)
6. [Maintainer Setup Guide](#6-maintainer-setup-guide)
7. [ExpenseWise CLI](#7-expensewise-cli)
8. [REST API Documentation](#8-rest-api-documentation)
9. [Project Structure](#9-project-structure)
10. [Configuration](#10-configuration)
11. [Deployment](#11-deployment)
12. [Contributing](#12-contributing)
13. [Roadmap](#13-roadmap)
14. [License](#14-license)

---

## 1. Project Overview

ExpenseWise is built to address the privacy concerns of storing sensitive daily transactional data online. By implementing user-level encryption keys derived from active credentials, the system ensures that expense amounts, categories, and descriptions are completely unreadable in the SQLite or PostgreSQL database unless an active session is validated.

Furthermore, it offers tools to automate budgeting decisions, project spending averages, and interface directly with local terminal scripts to keep developer workflows integrated.

---

## 2. Features

* **Secure Authentication:** Multi-factor checks utilizing password hashing and optional OTP verify routines.
* **Encrypted Storage:** Zero-knowledge data model encrypting values using symmetric AES-256 keys (Fernet) unique to each user.
* **Intelligent Budget Planning:** Calculates 3-month category averages, provides inline target recommendations, and renders allowance indicators.
* **Indian Number System Formatting:** Consistently groups digits in Indian standard format (`12,30,445.00`) across tables, summaries, and charts.
* **Dashboard & Visual Analytics:** Real-time statistics, monthly variance indicators, interactive spending trend lines, and category distribution doughnuts.
* **Custom Category/Payment Settings:** Create custom tags with unique hex colors, and access shortcuts from the Add Expense form.
* **JSON Portability:** Safe JSON backup export/import module executing multi-stage integrity and validation schema checks before execution.
* **Installable CLI Client:** Rich command-line client supporting registration, logging, list pagination, and summaries.
* **Versioned REST API:** Secure endpoints backed by JSON schemas and API access key authorizations.
* **Gravatar Profile Support:** Circular user avatars calculated from secure email hashes.
* **Responsive UI:** Clean CSS layouts with glassmorphic cards, transition animations, and dark navbar headers.

---

## 3. Screenshots (Placeholder)

*Screenshots of the application interfaces can be viewed here:*

#### Main User Dashboard
![Dashboard Mockup](./docs/screenshots/dashboard_mockup.png)
*(Placeholder: Displays the daily spend trend, category allocation doughnut, and rolling summaries)*

#### Budget Planning Center
![Budget Mockup](./docs/screenshots/budget_mockup.png)
*(Placeholder: Displays the category recommendations and real-time allowance meters)*

---

## 4. Technology Stack

* **Core Runtime:** Python (3.13+)
* **Web Framework:** Flask (3.0+) using the Application Factory Pattern
* **Database & ORM:** SQLite (dev) / PostgreSQL (prod), SQLAlchemy Core & Flask-SQLAlchemy, Alembic (Flask-Migrate)
* **Security & Auth:** Flask-Login, Flask-WTF, Flask-Talisman, Flask-Limiter, Cryptography (Fernet symmetric encryption)
* **Analytics Engine:** Pandas for aggregations, NumPy for linear regression forecasts
* **Front-End Styling:** Bootstrap 5, Custom Vanilla CSS (glassmorphism details)
* **Visualizations:** Chart.js, Bootstrap Icons
* **CLI Library:** Click, Rich (color tables and dashboard panels)
* **Testing Suite:** Pytest

---

## 5. Installation

Follow these steps to set up the development environment on your local system:

### 1. Clone the Repository
```bash
git clone https://github.com/indrajit912/expensewise.git
cd expensewise
```

### 2. Configure Virtual Environment
```bash
# Create the virtual environment
python -m venv venv

# Activate on Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Activate on Linux/macOS
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt -r requirements/dev.txt
```

### 4. Setup Environment Variables
Copy the `.env.example` file to `.env`:
```bash
# On Windows (PowerShell)
Copy-Item .env.example .env
# On Linux/macOS
cp .env.example .env
```
Open `.env` and set `FLASK_DEBUG=1`. You can also configure Hermes Email settings and customized Admin credentials if desired.

### 5. Run Database Setup and Launch
Initialize the schema and start the local development server:
```bash
# Initialize and seed database
flask setup-project

# Launch local server
flask run
```
Access the application at [http://127.0.0.1:5000/](http://127.0.0.1:5000/).

---

## 6. Maintainer Setup Guide

This guide details commands and workflows required by maintainers to develop and deploy ExpenseWise.

### The Unified Setup Tool
We have implemented a custom setup command that replaces manual migration deletions and seeding:
```bash
flask setup-project
```
**Workflow Executed:**
1. Prompts for confirmation before making changes.
2. Removes `instance/` and `migrations/` directories.
3. Initializes migrations (`flask db init`).
4. Generates initial schema maps (`flask db migrate`).
5. Performs DB upgrade (`flask db upgrade`).
6. Seeds system categories and configs (`flask bootstrap-system`).
7. Creates a default developer sandbox user (`flask create-guest`).

### Seeding Commands (Manual)
If you wish to seed values manually without resetting migrations, you can run:
```bash
# Seeding default global system categories
flask bootstrap-system

# Create the standard guest user (Username: guest, Password: password)
flask create-guest
```

### Database Schema Updates
Whenever you modify database models, generate and apply migrations:
```bash
flask db migrate -m "Description of model change"
flask db upgrade
```

### Running Tests
Execute the pytest suite to verify model math, encryption security, and API endpoints:
```bash
python -m pytest
```

---

## 7. ExpenseWise CLI

`expensewise-cli` is a standalone, terminal-based personal financial assistant that communicates exclusively with the server using the versioned REST API.

### Installation
From the root directory of the project, install the CLI in editable mode:
```bash
pip install -e cli/
```
Once installed, the CLI tool is globally available in your environment via the `expensewise-cli` executable.

### Configuration
By default, the CLI connects to the local development environment at `http://127.0.0.1:5000/api`. To point the CLI to a remote deployment (e.g. PythonAnywhere production instance), configure the `EXPENSEWISE_API_URL` environment variable:
```bash
# Windows PowerShell
$env:EXPENSEWISE_API_URL="https://expensewise.pythonanywhere.com/api"

# Linux/macOS
export EXPENSEWISE_API_URL="https://expensewise.pythonanywhere.com/api"
```

### Obtaining an API Token & Authentication
To log in without sharing your credentials over terminal streams, you can use a web-generated API token:
1. Log in to the web interface.
2. Navigate to **Settings** and scroll down to the **API Token** section.
3. Click **Generate New Token** and copy the resulting hash.
4. Run the following command to link the CLI:
   ```bash
   expensewise-cli token-login <YOUR_COPIED_TOKEN>
   ```
Alternatively, you can authenticate directly with your registration email and password:
```bash
expensewise-cli login
```
To sign out and delete local keys, run:
```bash
expensewise-cli logout
```

### Command Reference & Examples

#### User & Account Information
* **Show account details:**
  ```bash
  expensewise-cli profile
  ```
* **Change password:**
  ```bash
  expensewise-cli change-password
  ```

#### Expense Management
* **List expenses with paginated scroll:**
  ```bash
  expensewise-cli list
  ```
* **List expenses with category/date range filters:**
  ```bash
  expensewise-cli list --category=Food --start-date=2026-06-01 --end-date=2026-06-30
  ```
* **Record a transaction:**
  ```bash
  expensewise-cli add --amount=450.00 --category=Food --payee="Walmart"
  ```
* **Modify fields on a record:**
  ```bash
  expensewise-cli update <UUID> --amount=520.00 --description="Weekly shopping run"
  ```
* **Delete a record:**
  ```bash
  expensewise-cli delete <UUID>
  ```

#### Category & Payment Channels Customization
* **List categories:**
  ```bash
  expensewise-cli list-categories
  ```
* **Create a custom category:**
  ```bash
  expensewise-cli add-category --name="Subscribers" --color="#10b981"
  ```
* **List payment methods:**
  ```bash
  expensewise-cli list-payments
  ```

#### Budget Planning
* **Show budget comparisons vs actual spending:**
  ```bash
  expensewise-cli budget-show
  ```
* **Show spending budget recommendations:**
  ```bash
  expensewise-cli budget-suggest
  ```
* **Set category budget target limit:**
  ```bash
  expensewise-cli budget-set --month=2026-07 --category=Food --amount=5000.00
  ```
* **Clear category budget target:**
  ```bash
  expensewise-cli budget-delete 2026-07 Food
  ```

#### Portability Backup Files
* **Export database backup locally:**
  ```bash
  expensewise-cli export-backup backup.json
  ```
* **Import database backup from local JSON file:**
  ```bash
  expensewise-cli import-backup backup.json
  ```

#### Terminal Spending Visual Charts
Generate colorful terminal-based spending charts that map distributions across categories using Unicode bar representations:
```bash
expensewise-cli chart
```
*Supports date and category level parameters:*
```bash
expensewise-cli chart --start-date=2026-06-01 --end-date=2026-06-30
```

### Visual Chart Mockup
```text
  [ Spending Distribution Chart ]
  Total Spending: ₹12,300.00

  Food         | ██████████████████████████████  | ₹6,000.00 (48.8%)
  Rent         | ██████████████████              | ₹3,500.00 (28.5%)
  Utilities    | ██████████                      | ₹2,000.00 (16.3%)
  Other        | ████                            | ₹800.00 (6.5%)
```

### Troubleshooting
* **Error: 'expensewise-cli' is not recognized as an internal or external command:**
  Make sure you ran `pip install -e cli/` inside your active virtual environment and the environment's `Scripts/` (or `bin/`) folder is present in your system PATH.
* **Vault Decryption Errors:**
  If you recently changed your password, make sure to execute `expensewise-cli login` again to force update the local credential derivations and unlock database decryption.
```,StartLine:181,TargetContent:

---

## 8. REST API Documentation

All request and response payloads exchange JSON structures. Set `Authorization: Bearer <ACCESS_TOKEN>` on restricted routes.

### Summary Endpoints Map

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| **POST** | `/api/v1/auth/register` | Create a new user profile | No |
| **POST** | `/api/v1/auth/verify-otp`| Verify email registration OTP | No |
| **POST** | `/api/v1/auth/login` | Exchange credentials for API Access Token | No |
| **POST** | `/api/v1/auth/logout` | Revoke the active session token | Yes |
| **GET** | `/api/v1/expenses` | Query paginated list of user expenses | Yes |
| **POST** | `/api/v1/expenses` | Save a new expense record | Yes |
| **GET** | `/api/v1/expenses/<uuid>` | Fetch details of a single record | Yes |
| **PUT** | `/api/v1/expenses/<uuid>` | Edit details of a record | Yes |
| **DELETE**| `/api/v1/expenses/<uuid>` | Delete a record | Yes |
| **GET** | `/api/v1/categories` | List user custom categories | Yes |
| **POST** | `/api/v1/categories` | Add custom category | Yes |
| **GET** | `/api/v1/payment-methods` | List user payment channels | Yes |
| **GET** | `/api/v1/analytics/summary`| Fetch summary sums and averages | Yes |
| **GET** | `/api/v1/export` | Backup the user database to JSON v2.0 | Yes |
| **POST** | `/api/v1/import` | Restore the user database from JSON v2.0 | Yes |

### Example cURL Command: Save Expense
```bash
curl -X POST http://127.0.0.1:5000/api/v1/expenses \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 1250.75,
    "category": "Shopping",
    "expense_date": "2026-06-28",
    "payee": "Amazon India",
    "payment_mode": "Credit Card",
    "description": "Office supplies"
  }'
```

---

## 9. Project Structure

```text
expensewise/
├── app/
│   ├── api/                 # Versioned developer REST API endpoints & schemas
│   ├── auth/                # Sign-up, login, recovery routes and views
│   ├── dashboard/           # User metrics controllers, settings, budgets
│   ├── expenses/            # CRUD listings, filters, JSON backup/restore UI
│   ├── analytics/           # Deep analytics indicators & forecasts graphs
│   ├── cli/                 # Custom management commands (setup-project, etc.)
│   ├── services/            # Database encryption, JSON checks, analytics service
│   ├── models/              # User, Expense, APIToken, Budget database mappings
│   ├── static/              # CSS files, global JS modules
│   ├── templates/           # Jinja base layouts and modular fragments
│   └── extensions.py        # Extensions setup (db, migrate, limiter, etc.)
├── cli/                     # Setup.py and code for the expensewise-cli package
├── migrations/              # Database migration version files
├── tests/                   # Pytest automation scripts
├── config.py                # Development, Testing, Production configurations
└── manage.py                # Main application wrapper entrypoint
```

---

## 10. Configuration

Configure the application behavior using the following environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SECRET_KEY` | Symmetric token used to secure session cookies | Random hex key |
| `SECURITY_PASSWORD_SALT`| Salt key for generating recovery hashes | Random hex key |
| `DATABASE_URL` | SQLAlchemy connection URL | SQLite location |
| `FLASK_DEBUG` | Starts development server in debug mode if `1` | `0` |
| `HERMES_API_KEY` | Hermes Service access key (Email delivery) | `None` |

---

## 11. Deployment

### Production Flag
When deploying in production, ensure `FLASK_DEBUG=0` is set in the production dashboard. This automatically activates the `ProductionConfig` settings, which disable local SQLite fallbacks, enforce strict HTTPS redirects using `Flask-Talisman`, and disable debug trace logging.

### WSGI Configuration
To serve the app via Gunicorn:
```bash
gunicorn -w 4 "manage:app"
```

---

## 12. Contributing

We welcome contributions to ExpenseWise! Please follow these guidelines:
1. Fork the repository and create a feature branch (`git checkout -b feature/amazing-feature`).
2. Write clean Python code complying with PEP 8.
3. Add unit test assertions for any new service calculations or routes.
4. Run `python -m pytest` to verify that all tests pass.
5. Create a detailed Pull Request describing the changes.

---

## 13. Roadmap

* **Multi-Currency Aggregations:** Display dashboard analytics conversions dynamically across selected user standard currencies.
* **Visual Budget Alerts:** Configurable system alerts when spending threshold limits exceed 80% of category budget limits.
* **Recurring Transactions:** Automate monthly subscription records creation.
* **OIDC Integrations:** Support for signing in using OAuth 2.0 (Google, GitHub accounts).

---

## 14. License

This project is licensed under the terms of the MIT License. See the [LICENSE](./LICENSE) file for the full text. The MIT License is appropriate for this project as it permits modification, distribution, commercial use, and private hosting, allowing developers to adapt ExpenseWise for their own needs while providing the maintainer complete liability protection.
