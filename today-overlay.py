#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402


APP_DIR = Path.home() / ".config" / "super-today-overlay"
CONFIG_PATH = APP_DIR / "config.json"
BACKUP_DIR = Path.home() / ".config" / "superProductivity" / "backups"
LOCAL_API_BASE = "http://127.0.0.1:3876"
ICON_PATH = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps" / "super-today-overlay.svg"

DEFAULT_CONFIG = {
    "width": 360,
    "max_tasks": 0,
    "refresh_ms": 1000,
    "show_done": True,
    "sticky": True,
    "position_mode": "bottom_right",
    "manual_position": False,
    "bottom_gap": 26,
    "pin_from_top": 112,
    "gap_right": 0,
    "x": None,
    "y": None,
}

BG = "rgba(18, 23, 32, 0.94)"
BORDER = "rgba(88, 114, 153, 0.45)"
WORKSPACE_COLOR = "#f8c146"
SECTION_COLOR = "#66d9d1"
TEXT_COLOR = "#eef3fb"
MUTED_TEXT = "#93a1b6"
DONE_TEXT = "#697487"
CURRENT_BG = "rgba(68, 96, 142, 0.22)"


def ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_app_dir()
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text()))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    ensure_app_dir()
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")


def get_workspace_name() -> str:
    try:
        out = subprocess.check_output(
            ["wmctrl", "-d"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for line in out.splitlines():
            if " * " in line or (len(line) > 2 and line[2] == "*"):
                parts = re.split(r"  +", line.strip())
                if parts:
                    return parts[-1].strip()
    except Exception:
        pass
    return "WORKSPACE"


def get_primary_monitor_geometry() -> tuple[int, int, int, int]:
    try:
        display = Gdk.Display.get_default()
        if not display:
            raise RuntimeError("No GDK display")
        if hasattr(display, "get_primary_monitor"):
            monitor = display.get_primary_monitor()
        else:
            monitor = display.get_monitor(0)
        if not monitor:
            raise RuntimeError("No primary monitor")
        geo = monitor.get_geometry()
        return geo.x, geo.y, geo.width, geo.height
    except Exception:
        return 1920, 0, 1920, 1080


def latest_backup_file() -> Path | None:
    if not BACKUP_DIR.exists():
        return None
    files = sorted(BACKUP_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def parse_project_color(value: str | None) -> str:
    if not value:
        return SECTION_COLOR
    value = value.strip()
    if value.startswith("#"):
        return value
    match = re.match(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", value)
    if match:
        r, g, b = (max(0, min(255, int(part))) for part in match.groups())
        return f"#{r:02x}{g:02x}{b:02x}"
    return SECTION_COLOR


def apply_task_limit(rows: list[dict[str, Any]], max_tasks: int) -> list[dict[str, Any]]:
    if max_tasks <= 0:
        return rows
    return rows[:max_tasks]


def load_today_snapshot(show_done: bool, max_tasks: int) -> dict[str, Any]:
    live_snapshot = load_today_snapshot_from_api(show_done=show_done, max_tasks=max_tasks)
    if live_snapshot is not None:
        return live_snapshot

    backup = latest_backup_file()
    if not backup:
        return {
            "rows": [],
            "footer": "Enable local REST API in Super Productivity Settings > Misc",
            "source": None,
            "signature": "missing-backup-no-api",
        }

    try:
        data = json.loads(backup.read_text())
    except Exception as exc:
        return {
            "rows": [],
            "footer": f"Could not read backup: {exc}",
            "source": backup.name,
            "signature": f"bad-backup:{backup.name}",
        }

    task_state = data.get("task", {})
    task_entities = task_state.get("entities", {})
    current_task_id = task_state.get("currentTaskId")
    tag_entities = data.get("tag", {}).get("entities", {})
    project_entities = data.get("project", {}).get("entities", {})
    today_ids = tag_entities.get("TODAY", {}).get("taskIds", []) or []

    rows: list[dict[str, Any]] = []
    for task_id in today_ids:
        task = task_entities.get(task_id)
        if not task:
            continue
        is_done = bool(task.get("isDone"))
        if is_done and not show_done:
            continue

        project = project_entities.get(task.get("projectId"), {})
        rows.append(
            {
                "id": task_id,
                "title": task.get("title", "(untitled)"),
                "project": project.get("title") or "Inbox",
                "project_color": parse_project_color(project.get("theme", {}).get("primary")),
                "is_done": is_done,
                "is_current": task_id == current_task_id,
            }
        )

    visible = apply_task_limit(rows, max_tasks)
    stamp = datetime.fromtimestamp(backup.stat().st_mtime).strftime("%H:%M")
    footer = f"{len(rows)} today · backup {stamp}"

    return {
        "rows": visible,
        "footer": f"{footer} · backup fallback",
        "source": backup.name,
        "signature": json.dumps([visible, current_task_id, backup.name], sort_keys=True),
    }


def api_get(path: str, query: dict[str, str] | None = None) -> Any:
    url = f"{LOCAL_API_BASE}{path}"
    if query:
        url += "?" + urlparse.urlencode(query)
    req = urlrequest.Request(
        url,
        headers={"Host": "127.0.0.1:3876", "Accept": "application/json"},
        method="GET",
    )
    with urlrequest.urlopen(req, timeout=1.2) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_today_snapshot_from_api(show_done: bool, max_tasks: int) -> dict[str, Any] | None:
    try:
        tasks_resp = api_get(
            "/tasks",
            {
                "includeDone": "true",
                "source": "active",
            },
        )
        status_resp = api_get("/status")
        projects_resp = api_get("/projects")
        tags_resp = api_get("/tags")
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError):
        return None
    except Exception:
        return None

    if not tasks_resp.get("ok"):
        return None

    tasks = tasks_resp.get("data", []) or []
    current_task_id = (status_resp.get("data") or {}).get("currentTaskId")
    projects = projects_resp.get("data", []) or []
    project_map = {project.get("id"): project for project in projects if isinstance(project, dict)}
    tags = tags_resp.get("data", []) or []
    today_tag = next((tag for tag in tags if isinstance(tag, dict) and tag.get("id") == "TODAY"), None)
    today_ids = list((today_tag or {}).get("taskIds") or [])
    task_map = {task.get("id"): task for task in tasks if isinstance(task, dict) and task.get("id")}

    rows: list[dict[str, Any]] = []
    for task_id in today_ids:
        task = task_map.get(task_id)
        if not task:
            continue
        is_done = bool(task.get("isDone"))
        if is_done and not show_done:
            continue
        project = project_map.get(task.get("projectId"), {})
        rows.append(
            {
                "id": task.get("id"),
                "title": task.get("title", "(untitled)"),
                "project": project.get("title") or "Inbox",
                "project_color": parse_project_color((project.get("theme") or {}).get("primary")),
                "is_done": is_done,
                "is_current": task.get("id") == current_task_id,
            }
        )

    visible = apply_task_limit(rows, max_tasks)
    footer = f"{len(rows)} today · live api"
    return {
        "rows": visible,
        "footer": footer,
        "source": "local-api",
        "signature": json.dumps(["local-api", visible, current_task_id], sort_keys=True),
    }


class TaskRow(Gtk.Box):
    def __init__(self, row: dict[str, Any]):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.get_style_context().add_class("task-row")
        if row["is_current"]:
            self.get_style_context().add_class("current")

        dot = Gtk.Label()
        dot.set_use_markup(True)
        dot.set_markup(
            f"<span foreground='{html.escape(row['project_color'])}' size='large'>●</span>"
        )
        dot.set_valign(Gtk.Align.START)
        self.pack_start(dot, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        title = Gtk.Label(xalign=0)
        title.set_line_wrap(True)
        title.set_max_width_chars(28)
        title.set_selectable(False)
        title.set_use_markup(True)
        safe_title = html.escape(row["title"])
        if row["is_done"]:
            safe_title = f"<span foreground='{DONE_TEXT}' strikethrough='true'>{safe_title}</span>"
        elif row["is_current"]:
            safe_title = (
                f"<span foreground='{TEXT_COLOR}' weight='700'>"
                f"Now: {safe_title}</span>"
            )
        else:
            safe_title = f"<span foreground='{TEXT_COLOR}'>{safe_title}</span>"
        title.set_markup(safe_title)

        meta_parts = [row["project"].upper()]
        if row["is_current"]:
            meta_parts.append("ACTIVE")
        meta = Gtk.Label(xalign=0)
        meta.set_use_markup(True)
        meta.set_markup(
            f"<span foreground='{MUTED_TEXT}' size='small'>{html.escape(' · '.join(meta_parts))}</span>"
        )

        text_box.pack_start(title, False, False, 0)
        text_box.pack_start(meta, False, False, 0)
        self.pack_start(text_box, True, True, 0)


class SuperTodayOverlay(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="Super Today Overlay")
        self.config = load_config()
        self._last_signature: str | None = None
        self._last_workspace = ""
        self._is_programmatic_configure = False

        self.set_role("SuperTodayOverlay")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        if self.config["sticky"]:
            self.stick()
        if ICON_PATH.exists():
            try:
                self.set_icon_from_file(str(ICON_PATH))
            except Exception:
                pass

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)

        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self._on_key_press)
        self.connect("configure-event", self._on_configure)

        self._build_ui()
        self._place_window()
        self.show_all()
        GLib.idle_add(self._fit_to_content_and_place)

        self._refresh_workspace()
        self._refresh_today(force=True)
        GLib.timeout_add(1000, self._refresh_workspace)
        GLib.timeout_add(int(self.config["refresh_ms"]), self._refresh_today)

    def _build_ui(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_data(
            f"""
            .overlay-root {{
                background-color: {BG};
                border: 1px solid {BORDER};
                border-radius: 18px;
            }}
            .workspace-title {{
                color: {WORKSPACE_COLOR};
            }}
            .section-title {{
                color: {SECTION_COLOR};
            }}
            .task-row {{
                padding: 8px 8px;
                border-radius: 10px;
            }}
            .task-row.current {{
                background-color: {CURRENT_BG};
            }}
            .divider {{
                color: {BORDER};
            }}
            """.encode("utf-8")
        )
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        outer = Gtk.EventBox()
        outer.set_visible_window(True)
        outer.get_style_context().add_class("overlay-root")
        self.add(outer)
        self._content_widget = outer

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.set_border_width(14)
        outer.add(root)

        drag_area = Gtk.EventBox()
        drag_area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        drag_area.connect("button-press-event", self._on_drag_start)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        drag_area.add(header)

        self.workspace_label = Gtk.Label(xalign=0)
        self.workspace_label.get_style_context().add_class("workspace-title")
        self.workspace_label.set_use_markup(True)
        header.pack_start(self.workspace_label, False, False, 0)

        sub = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.section_label = Gtk.Label(xalign=0)
        self.section_label.get_style_context().add_class("section-title")
        self.section_label.set_use_markup(True)
        self.section_label.set_markup(
            f"<span weight='700' foreground='{SECTION_COLOR}' size='small'>TODAY</span>"
        )
        sub.pack_start(self.section_label, False, False, 0)

        self.summary_label = Gtk.Label(xalign=1)
        self.summary_label.set_use_markup(True)
        self.summary_label.set_markup(
            f"<span foreground='{MUTED_TEXT}' size='small'>loading</span>"
        )
        sub.pack_end(self.summary_label, False, False, 0)
        header.pack_start(sub, False, False, 0)

        divider = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        divider.get_style_context().add_class("divider")
        header.pack_start(divider, False, False, 0)

        root.pack_start(drag_area, False, False, 0)

        self.tasks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.tasks_box.set_margin_top(12)
        root.pack_start(self.tasks_box, False, False, 0)

        self.empty_label = Gtk.Label(xalign=0)
        self.empty_label.set_line_wrap(True)
        self.empty_label.set_use_markup(True)
        self.empty_label.set_markup(
            f"<span foreground='{MUTED_TEXT}'>No Today tasks right now.</span>"
        )
        self.tasks_box.pack_start(self.empty_label, False, False, 0)

        self.footer_label = Gtk.Label(xalign=0)
        self.footer_label.set_margin_top(10)
        self.footer_label.set_use_markup(True)
        self.footer_label.set_markup(
            f"<span foreground='{MUTED_TEXT}' size='small'>Esc to close · F5 to refresh</span>"
        )
        root.pack_start(self.footer_label, False, False, 0)

    def _place_window(self) -> None:
        width = int(self.config["width"])
        self.set_default_size(width, 1)
        self.resize(width, 1)
        GLib.idle_add(self._fit_to_content_and_place)

    def _should_use_manual_position(self) -> bool:
        return bool(self.config.get("manual_position")) and self.config.get("x") is not None and self.config.get("y") is not None

    def _fit_to_content_and_place(self) -> bool:
        width = int(self.config["width"])
        content_widget = getattr(self, "_content_widget", None)
        if not content_widget:
            return False

        try:
            _min_req, nat_req = content_widget.get_preferred_size()
            height = max(1, nat_req.height)
        except Exception:
            height = 1

        if self._should_use_manual_position():
            x = int(self.config["x"])
            y = int(self.config["y"])
        else:
            mon_x, mon_y, mon_w, mon_h = get_primary_monitor_geometry()
            x = mon_x + mon_w - width - int(self.config["gap_right"])
            position_mode = self.config.get("position_mode", "bottom_right")
            top_gap = 8
            max_y = mon_y + mon_h - height - top_gap

            if position_mode == "mid_right":
                anchor_y = mon_y + (mon_h // 2)
                y = min(anchor_y, max_y)
            else:
                bottom_gap = int(self.config.get("bottom_gap", 26))
                y = mon_y + mon_h - height - bottom_gap

            y = max(mon_y + top_gap, y)

        self._is_programmatic_configure = True
        self.resize(width, height)
        self.move(x, y)
        self._is_programmatic_configure = False
        return False

    def _set_workspace_markup(self, name: str) -> None:
        safe = html.escape(name.upper())
        self.workspace_label.set_markup(
            f"<span foreground='{WORKSPACE_COLOR}' weight='800' "
            f"size='x-large' letter_spacing='6000'>{safe}</span>"
        )

    def _refresh_workspace(self) -> bool:
        current = get_workspace_name()
        if current != self._last_workspace:
            self._last_workspace = current
            self._set_workspace_markup(current)
        return True

    def _refresh_today(self, force: bool = False) -> bool:
        snapshot = load_today_snapshot(
            show_done=bool(self.config["show_done"]),
            max_tasks=int(self.config["max_tasks"]),
        )
        if not force and snapshot["signature"] == self._last_signature:
            return True

        self._last_signature = snapshot["signature"]
        for child in list(self.tasks_box.get_children()):
            self.tasks_box.remove(child)

        rows = snapshot["rows"]
        if not rows:
            self.tasks_box.pack_start(self.empty_label, False, False, 0)
        else:
            for row in rows:
                self.tasks_box.pack_start(TaskRow(row), False, False, 0)

        count_text = f"{len(rows)} shown"
        self.summary_label.set_markup(
            f"<span foreground='{MUTED_TEXT}' size='small'>{html.escape(count_text)}</span>"
        )
        self.footer_label.set_markup(
            f"<span foreground='{MUTED_TEXT}' size='small'>{html.escape(snapshot['footer'])}</span>"
        )
        self.show_all()
        GLib.idle_add(self._fit_to_content_and_place)
        return True

    def _on_drag_start(self, _widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
            self.config["manual_position"] = True
            save_config(self.config)
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
            return True
        return False

    def _on_key_press(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if event.keyval == Gdk.KEY_F5:
            self._refresh_today(force=True)
            return True
        return False

    def _on_configure(self, _widget: Gtk.Widget, event: Gdk.EventConfigure) -> bool:
        if self._is_programmatic_configure:
            return False
        if not self.config.get("manual_position"):
            return False
        self.config["x"] = int(event.x)
        self.config["y"] = int(event.y)
        save_config(self.config)
        return False


def main() -> None:
    ensure_app_dir()
    try:
        GLib.set_prgname("super-today-overlay")
        Gdk.set_program_class("SuperTodayOverlay")
    except Exception:
        pass
    overlay = SuperTodayOverlay()
    overlay.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()

