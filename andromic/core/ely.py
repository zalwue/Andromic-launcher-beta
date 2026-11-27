"""Ely.by Yggdrasil authentication and authlib-injector management."""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from .net import download, HEADERS, post_json
from .paths import AUTHLIB_INJECTOR

AUTH_BASE = "https://authserver.ely.by"
AUTHENTICATE_URL = AUTH_BASE + "/auth/authenticate"
REFRESH_URL = AUTH_BASE + "/auth/refresh"
GITHUB_RELEASE_API = "https://api.github.com/repos/yushijinhun/authlib-injector/releases/latest"


class ElyAuthError(RuntimeError):
    """Authentication error returned by Ely.by."""

    def __init__(self, message: str, error: str = "", status: Optional[int] = None):
        self.error = error
        self.status = status
        self.needs_2fa = "two factor" in message.lower() or "two-factor" in message.lower()
        if self.needs_2fa:
            message = "Для аккаунта Ely.by включена двухфакторная защита. Введите код 2FA и повторите вход."
        super().__init__(message)


def _post(url: str, payload: dict) -> dict:
    try:
        return post_json(url, payload)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError):
            data = {}
        message = data.get("errorMessage") or data.get("error") or f"Ely.by returned HTTP {exc.code}"
        raise ElyAuthError(str(message), str(data.get("error", "")), exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ElyAuthError(f"Не удалось подключиться к Ely.by: {exc}") from None
    except (ValueError, TypeError) as exc:
        raise ElyAuthError(f"Некорректный ответ Ely.by: {exc}") from None


def authenticate(username: str, password: str, client_token: Optional[str] = None,
                 totp: str = "") -> dict:
    """Authenticate with username/e-mail and password; never persist the password."""
    username = username.strip()
    if not username or not password.strip():
        raise ElyAuthError("Введите логин и пароль Ely.by.")
    token = client_token or uuid.uuid4().hex
    if totp.strip():
        password = f"{password}:{totp.strip()}"
    data = _post(AUTHENTICATE_URL, {
        "username": username,
        "password": password,
        "clientToken": token,
        "requestUser": True,
    })
    return _normalise_account(data, token)


def refresh_account(account: dict) -> dict:
    """Refresh an existing Ely.by token and update the account in-place."""
    access_token = account.get("accessToken")
    client_token = account.get("clientToken")
    if not access_token or not client_token:
        raise ElyAuthError("Сессия Ely.by отсутствует. Войдите в аккаунт заново.")
    data = _post(REFRESH_URL, {
        "accessToken": access_token,
        "clientToken": client_token,
        "requestUser": True,
    })
    updated = _normalise_account(data, client_token)
    account.update(updated)
    return account


def _normalise_account(data: dict, client_token: str) -> dict:
    profile = data.get("selectedProfile") or {}
    profile_id = str(profile.get("id", "")).replace("-", "").lower()
    name = str(profile.get("name", "")).strip()
    access_token = data.get("accessToken")
    if len(profile_id) != 32 or not all(ch in "0123456789abcdef" for ch in profile_id):
        raise ElyAuthError("Ely.by не вернул корректный UUID игрового профиля.")
    if not name or not access_token:
        raise ElyAuthError("Ely.by вернул неполные данные игрового профиля.")
    return {
        "id": "ely-" + profile_id,
        "type": "ely",
        "nick": name,
        "uuid": profile_id,
        "accessToken": str(access_token),
        "clientToken": str(data.get("clientToken") or client_token),
        "slim": False,
    }


def ensure_authlib_injector(target: Optional[Path] = None) -> Path:
    """Download the latest official authlib-injector release and verify its digest."""
    target = Path(target or AUTHLIB_INJECTOR)
    if target.is_file() and _is_valid_jar(target):
        return target

    request = urllib.request.Request(
        GITHUB_RELEASE_API,
        headers={**HEADERS, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Не удалось получить список релизов authlib-injector: {exc}") from None

    assets = release.get("assets", [])
    asset = next((item for item in assets
                  if str(item.get("name", "")).lower().endswith(".jar")
                  and "authlib-injector" in str(item.get("name", "")).lower()), None)
    if not asset or not asset.get("browser_download_url"):
        raise RuntimeError("В официальном релизе authlib-injector не найден JAR-файл.")

    digest = asset.get("digest") or ""
    sha256 = digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None
    target.parent.mkdir(parents=True, exist_ok=True)
    # Streaming .part download + SHA-256 verify + atomic replace (never fully in RAM).
    try:
        download(asset["browser_download_url"], target, sha256=sha256, timeout=90)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"Не удалось скачать authlib-injector: {exc}") from None
    if not _is_valid_jar(target):
        target.unlink(missing_ok=True)
        raise RuntimeError("Скачанный authlib-injector.jar повреждён или не является JAR-файлом.")
    return target


def _is_valid_jar(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return "META-INF/MANIFEST.MF" in archive.namelist()
    except (OSError, zipfile.BadZipFile):
        return False
