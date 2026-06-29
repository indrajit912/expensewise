import os
import json
import requests
import keyring

class APIClient:
    """Client wrapper to interact with the ExpenseWise REST API."""

    def __init__(self, api_url=None):
        self.token_file_path = os.path.expanduser('~/.expensewise/auth.json')
        if api_url:
            self._api_url = api_url.rstrip('/')
        else:
            self._api_url = None

    @property
    def config_file_path(self):
        return os.path.expanduser('~/.expensewise/config.json')

    @property
    def api_url(self):
        if hasattr(self, '_api_url') and self._api_url:
            return self._api_url
        return self.load_config_url()

    def load_config_url(self):
        """Resolves the active API URL based on priority rules."""
        # 1. Environment Override
        env_url = os.environ.get('EXPENSEWISE_API_URL')
        if env_url:
            return env_url.rstrip('/')
            
        # 2. Stored Local Config
        if os.path.exists(self.config_file_path):
            try:
                with open(self.config_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stored_url = data.get('api_url')
                    if stored_url:
                        return stored_url.rstrip('/')
            except Exception:
                pass
                
        # 3. Default Fallback
        return 'http://localhost:5000/api'

    def save_config_url(self, url):
        """Saves the API URL to local configuration storage."""
        os.makedirs(os.path.dirname(self.config_file_path), exist_ok=True)
        try:
            config_data = {}
            if os.path.exists(self.config_file_path):
                try:
                    with open(self.config_file_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                except Exception:
                    pass
                
            config_data['api_url'] = url
            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
            try:
                os.chmod(self.config_file_path, 0o600)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def reset_config_url(self):
        """Resets the configured API URL by removing it from local storage."""
        if os.path.exists(self.config_file_path):
            try:
                config_data = {}
                try:
                    with open(self.config_file_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                except Exception:
                    pass
                if 'api_url' in config_data:
                    del config_data['api_url']
                with open(self.config_file_path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2)
                return True
            except Exception:
                pass
        return False

    def save_token(self, token):
        """Saves authentication token securely using OS keyring, falling back to secure file."""
        try:
            keyring.set_password("expensewise", "api_token", token)
        except Exception:
            # Secure fallback to file
            os.makedirs(os.path.dirname(self.token_file_path), exist_ok=True)
            with open(self.token_file_path, 'w', encoding='utf-8') as f:
                json.dump({'token': token}, f)
            try:
                os.chmod(self.token_file_path, 0o600)
            except Exception:
                pass

    def load_token(self):
        """Loads authentication token from keyring or fallback file."""
        try:
            token = keyring.get_password("expensewise", "api_token")
            if token:
                return token
        except Exception:
            pass

        # Fallback file check
        if not os.path.exists(self.token_file_path):
            return None
        try:
            with open(self.token_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('token')
        except (json.JSONDecodeError, OSError):
            return None

    @property
    def session_file_path(self):
        return os.path.expanduser('~/.expensewise/session.json')

    def clear_token(self):
        """Deletes local authentication credentials from keyring and files."""
        try:
            keyring.delete_password("expensewise", "api_token")
        except Exception:
            pass

        try:
            keyring.delete_password("expensewise", "login_password")
        except Exception:
            pass

        if os.path.exists(self.token_file_path):
            try:
                os.remove(self.token_file_path)
            except OSError:
                pass

        if os.path.exists(self.session_file_path):
            try:
                os.remove(self.session_file_path)
            except OSError:
                pass

    def save_session(self, method, email=None):
        """Saves current login session metadata and timezone-aware timestamp."""
        from datetime import datetime, timezone
        os.makedirs(os.path.dirname(self.session_file_path), exist_ok=True)
        try:
            data = {
                'login_method': method,
                'email': email,
                'login_timestamp': datetime.now(timezone.utc).isoformat()
            }
            with open(self.session_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            try:
                os.chmod(self.session_file_path, 0o600)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def load_session(self):
        """Loads session metadata from local storage."""
        if not os.path.exists(self.session_file_path):
            return None
        try:
            with open(self.session_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def get_headers(self):
        """Constructs headers containing the authorization Bearer token."""
        token = self.load_token()
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f"Bearer {token}"
        return headers

    def register(self, name, email, password):
        """Triggers user registration endpoint."""
        url = f"{self.api_url}/v1/auth/register"
        payload = {'name': name, 'email': email, 'password': password}
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        return response

    def login(self, email, password):
        """Triggers user login authentication endpoint."""
        url = f"{self.api_url}/v1/auth/login"
        payload = {'email': email, 'password': password}
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        return response

    def logout(self):
        """Informs the server of token invalidation and clears local session."""
        url = f"{self.api_url}/v1/auth/logout"
        response = requests.post(url, headers=self.get_headers())
        self.clear_token()
        return response

    def list_expenses(self, page=1, search='', category='', start_date='', end_date=''):
        """Retrieves user's expense ledger list with filters."""
        url = f"{self.api_url}/v1/expenses"
        params = {
            'page': page,
            'search': search,
            'category': category,
            'start_date': start_date,
            'end_date': end_date
        }
        return requests.get(url, params=params, headers=self.get_headers())

    def get_expense(self, uuid_str):
        """Fetches details of a single expense."""
        url = f"{self.api_url}/v1/expenses/{uuid_str}"
        return requests.get(url, headers=self.get_headers())

    def add_expense(self, amount, category, date_str, payee=None, mode=None, description=None):
        """Records a new expense in the database."""
        url = f"{self.api_url}/v1/expenses"
        payload = {
            'amount': amount,
            'category': category,
            'expense_date': date_str,
            'payee': payee,
            'payment_mode': mode,
            'description': description
        }
        return requests.post(url, json=payload, headers=self.get_headers())

    def update_expense(self, uuid_str, payload):
        """Modifies parameters of an existing expense."""
        url = f"{self.api_url}/v1/expenses/{uuid_str}"
        return requests.put(url, json=payload, headers=self.get_headers())

    def delete_expense(self, uuid_str):
        """Removes an expense record."""
        url = f"{self.api_url}/v1/expenses/{uuid_str}"
        return requests.delete(url, headers=self.get_headers())

    def get_analytics_summary(self, category='', start_date='', end_date=''):
        """Retrieves rollups and comparative changes with filters."""
        url = f"{self.api_url}/v1/analytics/summary"
        params = {
            'category': category,
            'start_date': start_date,
            'end_date': end_date
        }
        return requests.get(url, params=params, headers=self.get_headers())

    def get_analytics_trends(self, category='', start_date='', end_date=''):
        """Retrieves category distributions and histories with filters."""
        url = f"{self.api_url}/v1/analytics/trends"
        params = {
            'category': category,
            'start_date': start_date,
            'end_date': end_date
        }
        return requests.get(url, params=params, headers=self.get_headers())

    def get_analytics_forecast(self):
        """Retrieves forecasts and regression predictions."""
        url = f"{self.api_url}/v1/analytics/forecast"
        return requests.get(url, headers=self.get_headers())

    def get_profile(self):
        """Retrieves profile info of currently logged in user."""
        url = f"{self.api_url}/v1/auth/me"
        return requests.get(url, headers=self.get_headers())

    def change_password(self, current_password, new_password):
        """Changes password for the currently logged in user."""
        url = f"{self.api_url}/v1/auth/change-password"
        payload = {'current_password': current_password, 'new_password': new_password}
        return requests.post(url, json=payload, headers=self.get_headers())

    def list_categories(self):
        """Retrieves all user categories."""
        url = f"{self.api_url}/v1/categories"
        return requests.get(url, headers=self.get_headers())

    def add_category(self, name, color):
        """Creates a custom category."""
        url = f"{self.api_url}/v1/categories"
        payload = {'name': name, 'color': color}
        return requests.post(url, json=payload, headers=self.get_headers())

    def update_category(self, uuid_str, name, color):
        """Updates parameters of a category."""
        url = f"{self.api_url}/v1/categories/{uuid_str}"
        payload = {}
        if name:
            payload['name'] = name
        if color:
            payload['color'] = color
        return requests.put(url, json=payload, headers=self.get_headers())

    def delete_category(self, uuid_str):
        """Deletes a custom category."""
        url = f"{self.api_url}/v1/categories/{uuid_str}"
        return requests.delete(url, headers=self.get_headers())

    def list_payment_methods(self):
        """Retrieves all user payment methods."""
        url = f"{self.api_url}/v1/payment-methods"
        return requests.get(url, headers=self.get_headers())

    def add_payment_method(self, name, color):
        """Creates a custom payment method."""
        url = f"{self.api_url}/v1/payment-methods"
        payload = {'name': name, 'color': color}
        return requests.post(url, json=payload, headers=self.get_headers())

    def update_payment_method(self, uuid_str, name, color):
        """Updates parameters of a payment method."""
        url = f"{self.api_url}/v1/payment-methods/{uuid_str}"
        payload = {}
        if name:
            payload['name'] = name
        if color:
            payload['color'] = color
        return requests.put(url, json=payload, headers=self.get_headers())

    def delete_payment_method(self, uuid_str):
        """Deletes a custom payment method."""
        url = f"{self.api_url}/v1/payment-methods/{uuid_str}"
        return requests.delete(url, headers=self.get_headers())

    def get_budget(self, month):
        """Retrieves budget details for a target month."""
        url = f"{self.api_url}/v1/budget"
        params = {'month': month}
        return requests.get(url, params=params, headers=self.get_headers())

    def update_budget(self, month, budgets):
        """Updates category budgets for a target month."""
        url = f"{self.api_url}/v1/budget"
        payload = {'month': month, 'budgets': budgets}
        return requests.post(url, json=payload, headers=self.get_headers())
