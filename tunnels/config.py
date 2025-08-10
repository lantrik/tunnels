from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.prompt import Prompt

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_PATH = BASE_DIR / ".env"
CFG_PATH = BASE_DIR / "config.yaml"
STATE_PATH = BASE_DIR / "state.yaml"


class Settings(BaseSettings):
    domain: str = Field(default="", min_length=1)

    ssh_user: str = "root"
    ssh_port: int = 22
    admin_auth: str = Field(default="", min_length=1)

    scan_interval: float = 5.0
    render_interval: float = 0.1
    separate_counter: int = 4

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


class FileConfig(BaseModel):
    tunnels: dict[str, int] = Field(default_factory=dict)
    options: Mapping[str, int | float | str] = Field(default_factory=dict)


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data or {}


def save_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


def _yes(console: Console, question: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"

    ans = Prompt.ask(f"{question} {hint}").strip().lower()

    if not ans:
        return default

    return ans in {"y", "yes", "д", "да"}


def _create_env_interactive(console: Console) -> Settings:
    console.print("\n[bold green]● Первичная настройка окружения (.env)[/bold green]\n")
    console.print(
        "[bold]Укажи базовые параметры подключения к туннельному серверу.[/bold]\n"
    )

    domain = Prompt.ask("[cyan]Домен[/cyan] (например, tunnels.ru)").strip().rstrip("/")

    ssh_user = (
        Prompt.ask("[cyan]SSH пользователь[/cyan]", default="root").strip() or "root"
    )
    ssh_port = Prompt.ask("[cyan]SSH порт[/cyan]", default="22").strip() or "22"
    admin_auth = Prompt.ask("[cyan]Sish Admin Token[/cyan]").strip()

    console.print(
        "\n[bold]Интервалы и вывод (оставь по умолчанию, если не уверен):[/bold]"
    )

    scan_interval = (
        Prompt.ask("[cyan]SCAN_INTERVAL[/cyan] (сек)", default="5.0").strip() or "5.0"
    )
    render_interval = (
        Prompt.ask("[cyan]RENDER_INTERVAL[/cyan] (сек)", default="0.1").strip() or "0.1"
    )
    separate_counter = (
        Prompt.ask(
            "[cyan]SEPARATE_COUNTER[/cyan] (группировка строк)", default="4"
        ).strip()
        or "4"
    )

    ENV_PATH.write_text(
        "\n".join(
            [
                f"DOMAIN={domain}",
                f"SSH_USER={ssh_user}",
                f"SSH_PORT={ssh_port}",
                f"ADMIN_AUTH={admin_auth}",
                f"SCAN_INTERVAL={scan_interval}",
                f"RENDER_INTERVAL={render_interval}",
                f"SEPARATE_COUNTER={separate_counter}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    console.print("\n[bold green]✓ .env создан[/bold green]\n")

    return Settings()


def _create_config_yaml_interactive(console: Console) -> FileConfig:
    console.print("[bold green]● Настройка config.yaml[/bold green]\n")
    console.print(
        "Можно создать [bold]дефолтный список туннелей[/bold] или стартовать с пустого.\n"
        "[dim]Дальше их легко редактировать в config.yaml[/dim]\n"
    )

    defaults: dict[str, Any] = {
        "tunnels": {
            "web1": 8000,
            "web2": 8001,
            "web3": 8002,
            "web4": 8003,
            "api1": 3000,
            "api2": 3001,
            "api3": 3002,
            "api4": 3003,
            "bot1": 3010,
            "bot2": 3011,
            "bot3": 3012,
            "bot4": 3013,
            "misc1": 3020,
            "misc2": 3021,
            "misc3": 3022,
            "misc4": 3023,
        },
        "options": {"group_size": 4},
    }

    if _yes(console, "Сгенерировать дефолтные туннели?", True):
        save_yaml(CFG_PATH, defaults)
        console.print("[bold green]✓ config.yaml создан с примерами[/bold green]\n")
        return FileConfig(**defaults)

    empty: dict[str, Any] = {"tunnels": {}, "options": {"group_size": 4}}

    save_yaml(CFG_PATH, empty)
    console.print("[bold green]✓ config.yaml создан (пустой каркас)[/bold green]\n")

    return FileConfig(**empty)


def _ensure_state_file(console: Console) -> dict:
    if not STATE_PATH.exists():
        save_yaml(STATE_PATH, {"temporary_tunnels": {}})
        console.print("[bold green]✓ state.yaml создан[/bold green]\n")

    return load_yaml(STATE_PATH)


def ensure_interactive() -> tuple[Settings, FileConfig, dict]:
    console = Console()

    try:
        settings = Settings()
    except ValidationError:
        settings = _create_env_interactive(console)

    if not CFG_PATH.exists():
        file_cfg = _create_config_yaml_interactive(console)
    else:
        file_cfg = FileConfig(**(load_yaml(CFG_PATH) or {}))

    state = _ensure_state_file(console)

    return settings, file_cfg, state
