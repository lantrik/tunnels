from __future__ import annotations

import socket
import subprocess
import threading
import time
from typing import Callable, Dict, Optional
from uuid import uuid4

from rich.console import Console
from rich.prompt import Prompt
from rich.style import Style
from rich.table import Table


class TunnelManager:
    def __init__(
        self,
        tunnels: Dict[str, int],
        domain: str,
        ssh_user: str,
        ssh_port: int,
        admin_auth: str,
        separate_counter: int = 4,
        scan_interval: float = 5.0,
        render_interval: float = 0.1,
        on_temp_write: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        self._tunnels = dict(tunnels)

        self._domain = domain.rstrip("/")
        self._domain_suffix = f".{self._domain}"

        self._ssh_user = ssh_user
        self._ssh_port = str(ssh_port)
        self._admin_auth = admin_auth

        self._separate_counter = separate_counter
        self._scan_interval = scan_interval
        self._render_interval = render_interval

        self._on_temp_write = on_temp_write

        self._stop_scanning = False

        self._port_statuses: Dict[int, bool] = {}
        self._tunnel_processes: Dict[str, subprocess.Popen] = {}
        self._additional_tunnels: Dict[str, int] = {}

        self._lock = threading.Lock()

    @property
    def all_tunnels(self) -> Dict[str, int]:
        with self._lock:
            merged = {**self._tunnels, **self._additional_tunnels}

        return dict(merged)

    def _is_port_open(self, port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=0.5):
                return True
        except OSError:
            return False

    def _spawn_tunnel(self, name: str, port: int) -> None:
        if name in self._tunnel_processes:
            return

        proc = subprocess.Popen(
            [
                "ssh",
                "-p",
                self._ssh_port,
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "ServerAliveInterval=30",
                "-o",
                "ServerAliveCountMax=3",
                "-N",
                "-R",
                f"{name}:80:localhost:{int(port)}",
                f"{self._ssh_user}@{self._domain}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        self._tunnel_processes[name] = proc

    def _kill_tunnel(self, name: str) -> None:
        proc = self._tunnel_processes.pop(name, None)

        if proc and proc.poll() is None:
            proc.kill()

    def _scan_ports(self) -> None:
        while not self._stop_scanning:
            for name, port in self.all_tunnels.items():
                is_open = self._is_port_open(int(port))
                self._port_statuses[int(port)] = is_open

                if is_open and name not in self._tunnel_processes:
                    self._spawn_tunnel(name, int(port))

                elif not is_open and name in self._tunnel_processes:
                    self._kill_tunnel(name)

            time.sleep(self._scan_interval)

    def _table(self) -> Table:
        table = Table(
            title="Tunnel Manager",
            expand=True,
            title_style=Style(italic=False),
        )

        table.add_column("#", style="white", no_wrap=True)
        table.add_column("Name", style="magenta", no_wrap=True)
        table.add_column("Port", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Link", style="blue")

        items = list(self.all_tunnels.items())

        for i, (name, port) in enumerate(items, start=1):
            ok = self._port_statuses.get(int(port), False)
            status = "[green]● ON[/green]" if ok else "[red]● OFF[/red]"
            link = f"https://{name}{self._domain_suffix}"

            table.add_row(str(i), name.upper(), str(port), status, link)

            if i % self._separate_counter == 0 and i != len(items):
                table.add_row("", "", "", "", "")

        return table

    def _render_info(self, console: Console, name: str, port: int) -> None:
        link = f"https://{name}{self._domain_suffix}"
        admin = f"{link}/_sish/console?x-authorization={self._admin_auth}"
        api = f"http://localhost:{int(port)}"

        ok = self._port_statuses.get(int(port), False)
        status = "Активен" if ok else "Не активен"
        symbol = "[green]●[/green]" if ok else "[red]●[/red]"

        console.print(f"\n[bold green]Название:[/bold green] {name.upper()}")
        console.print(f"[bold green]Порт:[/bold green] {int(port)}")
        console.print(f"[bold green]Статус:[/bold green] {status} {symbol}")
        console.print(f"[bold green]Локально:[/bold green] {api}")
        console.print(f"[bold green]Ссылка:[/bold green] {link}")
        console.print(f"[bold green]Админ-панель:[/bold green] {admin}")

        Prompt.ask("\n[bold]Enter — назад[/bold]")

    def _info_flow(self, console: Console) -> None:
        query = Prompt.ask("Введите номер, имя или порт").strip()

        name: str | None = None
        port: int | None = None

        for k, v in self.all_tunnels.items():
            if query == k or query == str(v):
                name, port = k, int(v)
                break

        if name is None and query.isdigit():
            idx = int(query) - 1
            items = list(self.all_tunnels.items())

            if 0 <= idx < len(items):
                k, v = items[idx]
                name, port = k, int(v)

        if name and port is not None:
            self._render_info(console, name, port)
        else:
            console.print("[red]Не найдено.[/red]")
            time.sleep(1)

    def _unique_name(self) -> str:
        while True:
            name = "".join(str(uuid4()).split("-")[1:3])

            if name not in self.all_tunnels:
                return name

    def _add_flow(self, console: Console) -> None:
        s = Prompt.ask("Порт").strip()

        if not s.isdigit():
            console.print("[red]Неверный формат порта.[/red]")
            time.sleep(1)
            return

        port = int(s)

        if port in (int(v) for v in self.all_tunnels.values()):
            console.print("[red]Порт уже добавлен.[/red]")
            time.sleep(1)
            return

        name = self._unique_name()

        with self._lock:
            self._additional_tunnels[name] = port

        if self._is_port_open(port):
            self._spawn_tunnel(name, port)

        if self._on_temp_write:
            try:
                self._on_temp_write(name, port)
            except Exception:
                pass

    def _render(self, console: Console) -> None:
        console.print("\n" * 4)
        console.print(self._table())

        console.print("\n[bold]Действия[/bold]")
        console.print("[1] Информация о туннеле")
        console.print("[2] Создать временный туннель")
        console.print("[0] Выход")

        choice = Prompt.ask("\n[bold]>>[/bold]").strip()

        if choice == "0":
            raise KeyboardInterrupt

        if choice == "1":
            self._info_flow(console)
            return

        if choice == "2":
            self._add_flow(console)
            return

    def run(self) -> None:
        console = Console()

        t = threading.Thread(target=self._scan_ports, daemon=True)
        t.start()

        time.sleep(0.1)

        try:
            while True:
                console.clear()
                self._render(console)

                time.sleep(self._render_interval)

        except KeyboardInterrupt:
            self._stop_scanning = True

            console.print("\n[bold red]Выход...[/bold red]")

            for proc in list(self._tunnel_processes.values()):
                if proc.poll() is None:
                    proc.kill()
