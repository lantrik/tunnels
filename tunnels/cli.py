from __future__ import annotations

from typing import Dict

from .config import STATE_PATH, ensure_interactive, load_yaml, save_yaml
from .manager import TunnelManager


def _persist_temp(name: str, port: int) -> None:
    state = load_yaml(STATE_PATH) or {}

    temps: Dict[str, int] = state.setdefault("temporary_tunnels", {})
    temps[name] = int(port)

    save_yaml(STATE_PATH, state)


def run() -> None:
    settings, file_cfg, state = ensure_interactive()

    base = file_cfg.tunnels or {}
    temps = (state or {}).get("temporary_tunnels") or {}

    tunnels: Dict[str, int] = {
        **base,
        **{k: int(v) for k, v in temps.items()},
    }

    manager = TunnelManager(
        tunnels=tunnels,
        domain=settings.domain,
        ssh_user=settings.ssh_user,
        ssh_port=settings.ssh_port,
        admin_auth=settings.admin_auth,
        separate_counter=settings.separate_counter,
        scan_interval=settings.scan_interval,
        render_interval=settings.render_interval,
        on_temp_write=_persist_temp,
    )

    manager.run()
