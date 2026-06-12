"""Local web frontend: stdlib HTTP server around the simulation engine.

One background thread runs the matches (idle mode chains them), the
browser polls a compact JSON state several times per second and renders
it on a canvas. No external dependency, bound to 127.0.0.1 only.
"""
from __future__ import annotations

import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from engine.ai import allocate_ai_skills
from engine.game import Game, TICKS_PER_SECOND
from engine.mapgen import generate_map
from engine.team import TeamConfig
from engine.world import ResourceType, Terrain
from meta.history import append_match, build_record, load_history
from meta.progress import (
    XP_DRAW,
    XP_LOSS,
    XP_WIN,
    add_xp,
    load_profile,
    save_profile,
    skill_budget,
    xp_needed,
)
from meta.report import generate_report
from meta.rulesdoc import generate_rules
from meta.skills import SKILLS, unlocked_skills

STATIC_DIR = Path(__file__).resolve().parent / "static"

RECAP_SECONDS = 8.0
MAX_TICKS_PER_STEP = 96
SPEED_CHOICES = (0.5, 1.0, 2.0, 4.0, 8.0)

TERRAIN_CHARS = {
    Terrain.PLAIN: ".",
    Terrain.FOREST: "f",
    Terrain.MOUNTAIN: "m",
    Terrain.WATER: "w",
}

RESOURCE_CHARS = {
    ResourceType.ORE: "^",
    ResourceType.WOOD: "T",
    ResourceType.CRYSTAL: "*",
    ResourceType.FOOD: "%",
}


def _mask_hex(width: int, height: int, cells: set[tuple[int, int]]) -> list[str]:
    """Encode a cell set as one hex string per row, 4 cells per nibble."""
    digits = "0123456789abcdef"
    rows = []
    for y in range(height):
        chars = []
        for x0 in range(0, width, 4):
            nibble = 0
            for j in range(4):
                if (x0 + j, y) in cells:
                    nibble |= 1 << j
            chars.append(digits[nibble])
        rows.append("".join(chars))
    return rows


class Session:
    """Simulation owner: one match at a time, chained in idle mode."""

    def __init__(self):
        self._lock = threading.RLock()
        self.profile = load_profile()
        self.phase = "setup"            # setup | playing | recap
        self.game: Game | None = None
        self.match_id = 0
        self.allocation: dict[str, int] = {}
        self.idle = True
        self.speed = 1.0
        self.paused = False
        self.seed: int | None = None
        self.ai_profile = ""
        self.level = self.profile.level
        self.recap: dict | None = None
        self.recap_at = 0.0
        self.session_games = 0
        threading.Thread(target=self._loop, daemon=True).start()

    # Commands from the API

    def start(self, allocation: dict, idle: bool) -> None:
        with self._lock:
            self.allocation = self._sanitize(allocation)
            self.idle = bool(idle)
            self._launch()

    def control(self, payload: dict) -> None:
        with self._lock:
            if "pause" in payload:
                self.paused = bool(payload["pause"])
            if "speed" in payload:
                try:
                    value = float(payload["speed"])
                except (TypeError, ValueError):
                    value = 1.0
                self.speed = min(SPEED_CHOICES, key=lambda s: abs(s - value))
            if payload.get("idle") is not None:
                self.idle = bool(payload["idle"])
            if payload.get("next") and self.phase == "recap":
                self._launch()
            if payload.get("stop"):
                self.phase = "setup"
                self.game = None
                self.recap = None
                self.paused = False

    def _sanitize(self, allocation: dict) -> dict[str, int]:
        budget = skill_budget(self.profile.level)
        clean: dict[str, int] = {}
        spent = 0
        for skill in unlocked_skills(self.profile.level):
            try:
                points = int(allocation.get(skill.key, 0))
            except (TypeError, ValueError):
                points = 0
            points = max(0, min(points, skill.max_points, budget - spent))
            clean[skill.key] = points
            spent += points
        return clean

    # Match lifecycle (lock held)

    def _launch(self) -> None:
        self.level = self.profile.level
        seed = random.randrange(10**9)
        gmap, bases = generate_map(seed=seed)
        ai_skills, ai_profile = allocate_ai_skills(
            self.level, skill_budget(self.level), random.Random(seed + 1)
        )
        configs = [
            TeamConfig(
                "Bleus", "blue", self.allocation, is_player=True,
                level=self.level,
            ),
            TeamConfig("Rouges", "red", ai_skills, level=self.level),
        ]
        self.game = Game(gmap, bases, configs, seed=seed)
        self.seed = seed
        self.ai_profile = ai_profile
        self.match_id += 1
        self.session_games += 1
        self.phase = "playing"
        self.paused = False
        self.recap = None

    def _finish(self) -> None:
        game = self.game
        if game.winner == 0:
            result, xp = "victoire", XP_WIN
            self.profile.wins += 1
        elif game.winner is None:
            result, xp = "egalite", XP_DRAW
        else:
            result, xp = "defaite", XP_LOSS
            self.profile.losses += 1
        gained = add_xp(self.profile, xp)
        save_profile(self.profile)
        record = build_record(
            game, 0, result, self.seed, self.level, self.ai_profile
        )
        append_match(record)
        player, enemy = game.teams[0], game.teams[1]
        self.recap = {
            "result": result,
            "reason": game.end_reason,
            "duration_min": round(game.elapsed_seconds / 60, 1),
            "xp": xp,
            "level_up": gained,
            "ai_profile": self.ai_profile,
            "seed": self.seed,
            "rows": [
                ["Score", game.score(player), game.score(enemy)],
                ["Zones explorées", len(player.explored), len(enemy.explored)],
                ["Ressources récoltées", player.stats.total_collected,
                 enemy.stats.total_collected],
                ["Unités formées", player.stats.units_trained,
                 enemy.stats.units_trained],
                ["Unités perdues", player.stats.units_lost,
                 enemy.stats.units_lost],
                ["Unités éliminées", player.stats.units_killed,
                 enemy.stats.units_killed],
                ["Bâtiments construits", player.stats.buildings_built,
                 enemy.stats.buildings_built],
                ["Bâtiments détruits", player.stats.buildings_destroyed,
                 enemy.stats.buildings_destroyed],
                ["Dégâts infligés", player.stats.damage_dealt,
                 enemy.stats.damage_dealt],
            ],
        }
        self.phase = "recap"
        self.recap_at = time.monotonic()

    # Simulation thread

    def _loop(self) -> None:
        acc = 0.0
        last = time.monotonic()
        while True:
            time.sleep(0.01)
            with self._lock:
                now = time.monotonic()
                dt, last = now - last, now
                if self.phase == "recap":
                    acc = 0.0
                    if self.idle and now - self.recap_at >= RECAP_SECONDS:
                        self._launch()
                    continue
                if self.phase != "playing" or self.paused or self.game is None:
                    acc = 0.0
                    continue
                acc += dt * TICKS_PER_SECOND * self.speed
                steps = min(int(acc), MAX_TICKS_PER_STEP)
                acc -= steps
                for _ in range(steps):
                    self.game.tick()
                    if self.game.finished:
                        self._finish()
                        break

    # JSON payloads

    def meta_json(self) -> dict:
        with self._lock:
            budget = skill_budget(self.profile.level)
            upcoming = [
                s for s in SKILLS.values()
                if s.min_level > self.profile.level
            ]
            nxt = min(upcoming, key=lambda s: s.min_level, default=None)
            return {
                "phase": self.phase,
                "profile": self._profile_json(),
                "budget": budget,
                "skills": [
                    {
                        "key": s.key,
                        "label": s.label,
                        "description": s.description,
                        "kind": s.kind,
                        "max": s.max_points,
                    }
                    for s in unlocked_skills(self.profile.level)
                ],
                "next_unlock": (
                    {"label": nxt.label, "level": nxt.min_level}
                    if nxt else None
                ),
                "allocation": self.allocation,
            }

    def _profile_json(self) -> dict:
        return {
            "level": self.profile.level,
            "xp": self.profile.xp,
            "xp_needed": xp_needed(self.profile.level),
            "wins": self.profile.wins,
            "losses": self.profile.losses,
            "session_games": self.session_games,
        }

    def map_json(self) -> dict:
        with self._lock:
            if self.game is None:
                return {"match_id": self.match_id, "rows": []}
            gmap = self.game.map
            rows = [
                "".join(TERRAIN_CHARS[t] for t in row)
                for row in gmap.terrain
            ]
            return {
                "match_id": self.match_id,
                "width": gmap.width,
                "height": gmap.height,
                "rows": rows,
            }

    def state_json(self) -> dict:
        with self._lock:
            base = {
                "phase": self.phase,
                "match_id": self.match_id,
                "profile": self._profile_json(),
                "speed": self.speed,
                "paused": self.paused,
                "idle": self.idle,
            }
            if self.phase == "recap" and self.recap is not None:
                remaining = RECAP_SECONDS - (time.monotonic() - self.recap_at)
                base["recap"] = dict(
                    self.recap,
                    next_in=round(max(0.0, remaining), 1) if self.idle else None,
                )
            game = self.game
            if game is None:
                return base
            player = game.teams[0]
            base.update(
                {
                    "tick": game.tick_count,
                    "seconds": round(game.elapsed_seconds, 1),
                    "ai_profile": self.ai_profile,
                    "teams": [
                        {
                            "name": t.name,
                            "is_player": t.is_player,
                            "alive": t.alive,
                            "score": game.score(t),
                            "stocks": {
                                RESOURCE_CHARS[r]: t.stocks.get(r, 0)
                                for r in ResourceType
                            },
                            "units": len(game.units_of(t.tid)),
                            "buildings": len(
                                game.buildings_of(t.tid, only_complete=True)
                            ),
                        }
                        for t in game.teams.values()
                    ],
                    "units": [
                        [
                            u.uid,
                            u.spec.symbol,
                            u.x,
                            u.y,
                            u.team_id,
                            round(u.hp / u.max_hp, 2),
                        ]
                        for u in game.units.values()
                        if u.team_id == 0 or u.pos in player.visible
                    ],
                    "buildings": [
                        [
                            b.bid,
                            b.spec.symbol,
                            b.x,
                            b.y,
                            b.team_id,
                            1 if b.complete else 0,
                            round(b.hp / b.max_hp, 2),
                        ]
                        for b in game.buildings.values()
                        if b.team_id == 0
                        or b.pos in player.visible
                        or b.bid in player.known_enemy_buildings
                    ],
                    "deposits": [
                        [d.x, d.y, RESOURCE_CHARS[d.rtype], d.amount, d.pile]
                        for pos, d in game.map.deposits.items()
                        if pos in player.explored
                    ],
                    "events": [
                        [round(t / TICKS_PER_SECOND), msg]
                        for t, msg in list(game.events)[-8:]
                    ],
                    "explored": _mask_hex(
                        game.map.width, game.map.height, player.explored
                    ),
                    "visible": _mask_hex(
                        game.map.width, game.map.height, player.visible
                    ),
                }
            )
            return base


SESSION: Session | None = None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silence request logging
        pass

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length < 65536:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send_file(
                STATIC_DIR / "index.html", "text/html; charset=utf-8"
            )
        elif self.path == "/static/app.css":
            self._send_file(STATIC_DIR / "app.css", "text/css; charset=utf-8")
        elif self.path == "/static/app.js":
            self._send_file(
                STATIC_DIR / "app.js",
                "application/javascript; charset=utf-8",
            )
        elif self.path == "/api/meta":
            self._send_json(SESSION.meta_json())
        elif self.path == "/api/state":
            self._send_json(SESSION.state_json())
        elif self.path == "/api/map":
            self._send_json(SESSION.map_json())
        elif self.path == "/stats":
            path = generate_report(load_history())
            self._send_file(path, "text/html; charset=utf-8")
        elif self.path == "/regles":
            path = generate_rules()
            self._send_file(path, "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self):
        payload = self._read_json()
        if self.path == "/api/start":
            SESSION.start(
                payload.get("skills") or {}, payload.get("idle", True)
            )
            self._send_json({"ok": True})
        elif self.path == "/api/control":
            SESSION.control(payload)
            self._send_json({"ok": True})
        else:
            self.send_error(404)


def serve(port: int = 8765, open_browser: bool = True) -> None:
    global SESSION
    SESSION = Session()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Doctrine est servi sur {url} (ctrl+C pour arrêter)")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
    finally:
        server.server_close()
