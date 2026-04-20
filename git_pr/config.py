import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64


class ConfigManager:
    def __init__(self, config_dir=None):
        if config_dir is None:
            config_dir = Path.home() / ".gitpr"
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "config.json"
        self.key_file = self.config_dir / "key"
        self.fernet = None
        self._init_config()

    def _init_config(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.key_file.exists():
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)
        else:
            key = self.key_file.read_bytes()
        self.fernet = Fernet(key)

        if not self.config_file.exists():
            default_config = {
                "github": {
                    "token": "",
                    "username": "",
                    "default_branch": "main"
                }
            }
            self._save_config(default_config)

    def _save_config(self, config):
        self.config_file.write_text(json.dumps(config, indent=2))

    def _load_config(self):
        if self.config_file.exists():
            return json.loads(self.config_file.read_text())
        return {}

    def encrypt_token(self, token: str) -> str:
        encrypted = self.fernet.encrypt(token.encode())
        return encrypted.decode()

    def decrypt_token(self, encrypted_token: str) -> str:
        if not encrypted_token:
            return ""
        decrypted = self.fernet.decrypt(encrypted_token.encode())
        return decrypted.decode()

    def set_github_token(self, token: str):
        config = self._load_config()
        encrypted_token = self.encrypt_token(token)
        config.setdefault("github", {})["token"] = encrypted_token
        self._save_config(config)

    def get_github_token(self) -> str:
        config = self._load_config()
        encrypted_token = config.get("github", {}).get("token", "")
        return self.decrypt_token(encrypted_token)

    def set_github_username(self, username: str):
        config = self._load_config()
        config.setdefault("github", {})["username"] = username
        self._save_config(config)

    def get_github_username(self) -> str:
        config = self._load_config()
        return config.get("github", {}).get("username", "")

    def set_default_branch(self, branch: str):
        config = self._load_config()
        config.setdefault("github", {})["default_branch"] = branch
        self._save_config(config)

    def get_default_branch(self) -> str:
        config = self._load_config()
        return config.get("github", {}).get("default_branch", "main")

    def is_configured(self) -> bool:
        token = self.get_github_token()
        username = self.get_github_username()
        return bool(token and username)
