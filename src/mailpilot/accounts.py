"""Accounts and built-in provider profiles."""
import json
from dataclasses import asdict, dataclass, fields
from typing import List, Optional

from .paths import config_dir, resource
from .settings import write_json_private


@dataclass
class Account:
    name: str = ""
    email: str = ""
    username: str = ""
    provider: str = "custom"
    recv_protocol: str = "imap"      # imap | pop3
    recv_host: str = ""
    recv_port: int = 993
    recv_security: str = "ssl"       # ssl | starttls | none
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_security: str = "ssl"

    @property
    def secret_key(self) -> str:
        return "account:" + self.email.lower()

    @property
    def label(self) -> str:
        return self.name or self.email


def load_providers() -> List[dict]:
    with open(resource("providers.json"), encoding="utf-8") as fh:
        return json.load(fh)["providers"]


def guess_provider(email: str, providers: Optional[List[dict]] = None) -> Optional[dict]:
    providers = providers if providers is not None else load_providers()
    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    for p in providers:
        if domain and domain in [d.lower() for d in p.get("domains", [])]:
            return p
    return None


def fill_from_profile(acct: Account, profile: dict) -> Account:
    """Copy server settings from a provider profile into an Account."""
    acct.provider = profile["id"]
    proto = acct.recv_protocol
    recv = profile.get(proto) or profile.get("imap")
    if recv is None:
        return acct
    if profile.get(proto) is None:
        acct.recv_protocol = "imap"
    acct.recv_host, acct.recv_port, acct.recv_security = recv["host"], recv["port"], recv["security"]
    smtp = profile.get("smtp")
    if smtp:
        acct.smtp_host, acct.smtp_port, acct.smtp_security = smtp["host"], smtp["port"], smtp["security"]
    return acct


def supports_password_login(profile: Optional[dict]) -> bool:
    """Mailpilot 1.0 signs in with a password or app password only (no OAuth yet)."""
    if profile is None:
        return True
    return any(a in ("password", "app-password", "bridge-password") for a in profile.get("auth", []))


class AccountStore:
    def __init__(self, path=None):
        self.path = path or (config_dir() / "accounts.json")
        self.accounts: List[Account] = []
        self.load()

    def load(self) -> None:
        names = {f.name for f in fields(Account)}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.accounts = [Account(**{k: v for k, v in a.items() if k in names}) for a in raw]
        except (OSError, ValueError, TypeError):
            self.accounts = []

    def save(self) -> None:
        write_json_private(self.path, [asdict(a) for a in self.accounts])

    def upsert(self, acct: Account) -> None:
        for i, a in enumerate(self.accounts):
            if a.email.lower() == acct.email.lower():
                self.accounts[i] = acct
                break
        else:
            self.accounts.append(acct)
        self.save()

    def remove(self, email: str) -> None:
        self.accounts = [a for a in self.accounts if a.email.lower() != email.lower()]
        self.save()

    def get(self, email: str) -> Optional[Account]:
        for a in self.accounts:
            if a.email.lower() == email.lower():
                return a
        return None
