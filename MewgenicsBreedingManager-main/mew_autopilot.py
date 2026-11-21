#!/usr/bin/env python3
"""
mew_autopilot.py (v10.0 - Closed-Loop Patch 1.1+ Breeding & 2D Spatial Furniture Architect)
100% Legitimate Vanilla Rules (Zero RNG/Stat/Food Cheats).

Key Capabilities:
  1. Ground-truth furniture database synced from notalim/mewgenics-house-planner + local resources.gpak.
  2. Exact 4-cell 2D grid packer (solid, shelf-bolt, pin, headroom) with horizontal flip (⇄) support,
     left-wall pinning, multi-column Attic sloped-roof clearance, and multi-move Simulated Annealing
     (Relocate + Room↔Room Swap + Storage↔Room Eviction Swap).
  3. Full Patch 1.1+ Breeding & Roster Engine (AdaptiveOptimizer):
     - Exact recursive Wright's Coefficient of Inbreeding (COI) + Patch 1.1 Stim attenuation.
     - Complementary 7-stat pair matching, CHA-drift suppression, Lovers/Rivals & Orientation rules.
     - Dynamic Progression Stage detection (Early Foundation -> Stat Consolidation -> Endgame Mut/Skills).
     - Live cat-count Comfort buffers & AutoCattery v0.5.35 breeding-room dominance alignment.
     - Patch 1.1 Mutation >10 dead-zone guard (repurposes Room 4 until >10 Mutation is achievable).
  4. Safe, non-destructive AutoCattery v0.5.35 protection sync into `Mods/AutoCattery/config/protection.json`
     preserving all manual F10 user protection records and identity_tokens.
"""

import os
import re
import sys
import csv
import io
import time
import json
import math
import struct
import random
import shutil
import inspect
import sqlite3
import tempfile
import importlib.util
import urllib.request
import ssl
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
RARE_OVERRIDE_FILE = SCRIPT_DIR / "rare_overrides.json"
MANAGED_PROTECTIONS_FILE = SCRIPT_DIR / "autopilot_managed_protections.json"
PLAN_SUMMARY_FILE = SCRIPT_DIR / "autopilot_plan_summary.json"
NOTALIM_FURN_CACHE_FILE = SCRIPT_DIR / "notalim_furniture_cache.json"
NOTALIM_HOUSE_CACHE_FILE = SCRIPT_DIR / "notalim_house_cache.json"
WHYAYALA_PARSER_CACHE_FILE = SCRIPT_DIR / "whyayala_save_parser_cache.py"

NOTALIM_FURN_URL = "https://raw.githubusercontent.com/notalim/mewgenics-house-planner/main/client/src/data/furniture.json"
NOTALIM_HOUSE_URL = "https://raw.githubusercontent.com/notalim/mewgenics-house-planner/main/client/src/data/house.json"
WHYAYALA_PARSER_URL = "https://raw.githubusercontent.com/whyayala/MewgenicsBreedingManager/main/src/save_parser.py"

sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "src"))

save_parser = None
for mod_name in ("save_parser", "src.save_parser"):
    try:
        save_parser = __import__(mod_name, fromlist=["*"])
        break
    except Exception:
        pass


# =====================================================================
# 0. UTILITIES & META KNOWLEDGE CONSTANTS (PATCH 1.1+ / SCIRESM)
# =====================================================================

COMBAT_STATS = ("STR", "DEX", "CON", "INT", "SPD", "LCK")
ALL_STATS = ("STR", "DEX", "CON", "INT", "SPD", "CHA", "LCK")

META_ABILITIES = {
    "brainstorm", "copycat", "forbidden fart", "become entropy",
    "bump", "cleanse", "summon crow", "godspeed", "godspeed+",
    "immovable", "living rocks", "pooter", "scatter shot",
    "skill share", "skill share+", "skillshare", "skillshare+",
    "super luck", "super luck+", "mini-me", "mini-me+",
    "item proxy", "item proxy+", "death boon", "tenderize",
    "split atom", "loot corpse", "repair", "bare minimum",
    "hose off", "forbidden",
}

BENEFICIAL_DISORDERS = {
    "lycanthropy", "dwarfism", "primordial dwarfism",
    "schrodinger's syndrome", "schrödinger's syndrome", "schrodingers syndrome",
    "tourette's syndrome", "tourettes syndrome", "tourette's",
    "blood frenzy", "triskaidekaphobia", "sociopathy", "tainted genes",
    "adhd", "autism", "itchies", "wheezies",
}

HIGH_VALUE_DISORDERS = {
    "schrodinger's syndrome", "schrödinger's syndrome", "schrodingers syndrome",
    "dwarfism", "primordial dwarfism", "tourette's syndrome", "tourettes syndrome",
    "blood frenzy", "triskaidekaphobia", "lycanthropy", "tainted genes",
    "adhd", "itchies", "wheezies",
}

CRIPPLING_DISORDERS = {
    "sterile", "fragile bones", "rabies", "depression", "psychosis",
    "naegleria fowleri", "malaria",
}

META_BODY_MUTATIONS = {
    "double head", "two heads", "extra head", "extra turn",
    "attack tail", "rat tail", "quills", "exposed brain",
    "cursed", "reroll", "mountain form",
}

DOMINANT_POSITIVE_TRAITS = {"strong", "agile", "tough", "smart", "quick", "lucky"}


def _to_int(val: Any, default: int = 0) -> int:
    if val is None or isinstance(val, bool):
        return default
    if isinstance(val, (int, float)):
        return int(val)
    m = re.search(r"-?\d+", str(val).strip())
    return int(m.group(0)) if m else default


def _to_float(val: Any, default: float = 0.0) -> float:
    if val is None or isinstance(val, bool):
        return default
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"-?\d+(?:\.\d+)?", str(val).strip())
    return float(m.group(0)) if m else default


def _room_name_to_id(raw_room: Any) -> Tuple[int, str]:
    if raw_room is None:
        return 0, "Storage"
    s = str(raw_room).strip()
    low = s.lower()
    if not low or low in ("0", "none", "null", "storage", "inventory", "unplaced", "stash"):
        return 0, "Storage"
    if "attic" in low or "roof" in low or low == "1":
        return 1, "Attic"
    if "floor2_large" in low or "floor2_right" in low or "top_right" in low or low == "2":
        return 2, "Floor2_Large (Mid-Right)"
    if "floor1_small" in low or "floor1_left" in low or "bot_left" in low or low == "3":
        return 3, "Floor1_Small (Bot-Left)"
    if "floor1_large" in low or "floor1_right" in low or "bot_right" in low or low == "4":
        return 4, "Floor1_Large (Bot-Right)"
    if "floor2_small" in low or "floor2_left" in low or "top_left" in low or low == "5":
        return 5, "Floor2_Small (Mid-Left)"
    return 0, s


def load_rare_overrides() -> Set[str]:
    if RARE_OVERRIDE_FILE.exists():
        try:
            data = json.loads(RARE_OVERRIDE_FILE.read_text(encoding="utf-8"))
            return set(data.get("rare_uids", []))
        except Exception:
            pass
    return set()


def save_rare_overrides(rare_uids: Set[str]) -> None:
    try:
        RARE_OVERRIDE_FILE.write_text(
            json.dumps({"rare_uids": sorted(rare_uids)}, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(str(tmp_path), str(path))


def _http_get_text(url: str, timeout: int = 10) -> Optional[str]:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


# =====================================================================
# 1. FURNITURE MODELS, GPAK (.GON + .CSV) & NOTALIM DATABASE LOADER
# =====================================================================

@dataclass
class FurnitureDef:
    item_id: str
    display_name: str
    anchor_type: str
    width: int = 2
    height: int = 2
    provides_socket: bool = False
    stim: int = 0
    comfort: int = 0
    health: int = 0
    mutation: int = 0
    appeal: int = 0
    food_storage: int = 0
    special_totem: str = ""


@dataclass
class FurniturePiece:
    uid: str
    item_id: str
    name: str
    is_rare: bool = False
    anchor_type: str = "floor_base"
    width: int = 2
    height: int = 2
    provides_socket: bool = True
    base_stim: int = 0
    base_comfort: int = 0
    base_health: int = 0
    base_mutation: int = 0
    base_appeal: int = 0
    base_food: int = 0
    special_totem: str = ""
    current_room: int = 0
    current_room_label: str = "Storage"
    cells: List[Tuple[int, int, int]] = field(default_factory=lambda: [(0, 0, 3), (0, 1, 2)])
    kind: str = "grounded"
    can_rare: bool = True
    solid_cells: List[Tuple[int, int, int]] = field(default_factory=list)
    support_cells: List[Tuple[int, int]] = field(default_factory=list)
    pin_cells: List[Tuple[int, int]] = field(default_factory=list)
    headroom_cells: List[Tuple[int, int]] = field(default_factory=list)

    @property
    def mult(self) -> int:
        return 2 if self.is_rare else 1

    @property
    def stim(self) -> int:
        return self.base_stim * self.mult

    @property
    def comfort(self) -> int:
        return self.base_comfort * self.mult

    @property
    def health(self) -> int:
        return self.base_health * self.mult

    @property
    def mutation(self) -> int:
        return self.base_mutation * self.mult

    @property
    def appeal(self) -> int:
        return self.base_appeal * self.mult

    @property
    def food_storage(self) -> int:
        return self.base_food * self.mult


def find_gpak_path() -> Optional[Path]:
    for p in [
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Mewgenics\resources.gpak"),
        Path(r"C:\Program Files\Steam\steamapps\common\Mewgenics\resources.gpak"),
        Path(r"D:\SteamLibrary\steamapps\common\Mewgenics\resources.gpak"),
        Path(r"E:\SteamLibrary\steamapps\common\Mewgenics\resources.gpak"),
    ]:
        if p.exists():
            return p
    return None


def read_files_from_gpak(gpak_path: Path, target_substrings: Tuple[str, ...]) -> Dict[str, str]:
    extracted: Dict[str, str] = {}
    try:
        with gpak_path.open("rb") as f:
            raw_count = f.read(4)
            if len(raw_count) < 4:
                return extracted
            count = struct.unpack("<I", raw_count)[0]
            if count > 500000:
                return extracted

            entries: List[Tuple[str, int, int]] = []
            running_offset = 0
            for _ in range(count):
                nlen_b = f.read(2)
                if len(nlen_b) < 2:
                    break
                nlen = struct.unpack("<H", nlen_b)[0]
                name = f.read(nlen).decode("utf-8", errors="ignore").replace("\\", "/")
                size = struct.unpack("<I", f.read(4))[0]
                entries.append((name, running_offset, size))
                running_offset += size

            data_base = f.tell()
            for name, rel_off, size in entries:
                low_name = name.lower()
                if any(sub in low_name for sub in target_substrings) and size < 25_000_000:
                    f.seek(data_base + rel_off)
                    extracted[name] = f.read(size).decode("utf-8", errors="ignore")
    except Exception:
        pass
    return extracted


def parse_gon_blocks(text: str) -> Dict[str, str]:
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    def _extract_level(s: str) -> Dict[str, str]:
        blocks: Dict[str, str] = {}
        idx = 0
        length = len(s)
        while idx < length:
            m = re.search(r"([A-Za-z0-9_.\-]+)\s*\{", s[idx:])
            if not m:
                break
            key = m.group(1).strip()
            b_start = idx + m.end() - 1
            depth = 0
            j = b_start
            while j < length:
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            blocks[key] = s[b_start + 1 : j]
            idx = j + 1
        return blocks

    top = _extract_level(text)
    results: Dict[str, str] = {}
    for k, body in top.items():
        if k.lower() in ("furniture", "items", "house_items", "objects", "furniture_items") or len(top) <= 2:
            inner = _extract_level(body)
            if len(inner) > len(top):
                results.update(inner)
            else:
                results[k] = body
        else:
            results[k] = body
    return results


def _humanize_item_id(raw_id: str, loc_map: Dict[str, str]) -> str:
    s = str(raw_id or "").strip()
    if not s:
        return "Mystery Furniture"
    if s in loc_map:
        return loc_map[s]
    if s.upper() in loc_map:
        return loc_map[s.upper()]
    for prefix in ("FURNITURE_", "ITEM_", "HOUSE_", "OBJ_", "PROP_", "FURN_"):
        if s.upper().startswith(prefix):
            s = s[len(prefix):]
    for suffix in ("_NAME", "_DESC", "_RARE", "_SHINY"):
        if s.upper().endswith(suffix):
            s = s[: -len(suffix)]
    return s.replace("_", " ").strip().title() or "Furniture Piece"


def _infer_special_totem(item_id: str, disp_name: str, st: int, co: int, he: int, mu: int, ap: int, food: int) -> str:
    combined = f"{item_id} {disp_name}".lower()
    if any(w in combined for w in ("chastity", "celibacy", "no_breed", "suppressor")):
        return "chastity"
    if "fightidol" in combined or (any(w in combined for w in ("idol", "totem", "statue_tracy")) and any(w in combined for w in ("chaos", "fight", "war", "anger", "brawl"))):
        return "chaos"
    if any(w in combined for w in ("idol", "totem", "statue_tracy")):
        if "evol" in combined or "mutat" in combined or mu >= 4:
            return "evolution"
        if "stim" in combined or st >= 4:
            return "stim"
        if "health" in combined or he >= 4:
            return "health"
        if "comfort" in combined or co >= 4:
            return "comfort"
        if "appeal" in combined or ap >= 4:
            return "appeal"
    if food > 0 or any(w in combined for w in ("food_box", "foodbox", "food_storage", "kibble", "feeder")):
        return "food"
    return ""


def _infer_anchor_and_socket(item_id: str, disp_name: str, block_text: str, w: int, h: int, totem: str) -> Tuple[str, bool]:
    combined = f"{item_id} {disp_name}".lower()
    low_blk = block_text.lower()
    if totem and totem != "food":
        return "idol", False
    if any(w in low_blk for w in ("ceiling", "hanging", "hangs")) or any(
        x in combined for x in ("chandelier", "birdcage", "hanging", "mobile", "lantern", "pendant", "ceiling")
    ):
        return "ceiling", False
    if any(w in low_blk for w in ("wall", "floating")) or any(
        x in combined for x in ("painting", "poster", "clock", "mirror", "glorg", "shelf", "wall", "banner", "plaque", "sign", "window", "tapestry")
    ):
        return "wall", ("surface" in low_blk or "shelf" in combined)

    has_surface = bool(
        re.search(r"\b(surface|table|stackable|platform|top_socket|can_stack_on)\b\s*:?\s*(true|1|[a-z0-9_]+)", low_blk)
        or any(x in combined for x in ("table", "desk", "dresser", "cabinet", "bookshelf", "crate", "barrel", "box", "tv", "television", "skull", "outhouse", "fridge", "counter", "stand", "nightstand", "chest", "trunk", "stool", "bench", "washer", "dryer", "stove", "oven"))
    )
    can_be_stacked = bool(
        "stack" in low_blk
        or any(x in combined for x in ("box", "crate", "barrel", "skull", "tv", "television", "small table", "sewer", "cube", "block", "cage"))
    )
    if can_be_stacked and has_surface:
        return "stackable", True
    if has_surface:
        return "floor_base", True
    if w <= 2 and h <= 2 and not any(x in combined for x in ("bed", "couch", "sofa", "rug", "carpet", "mat", "chair", "recliner", "throne", "toilet", "tub")):
        return "topper", False
    return "floor_base", False


def load_master_furniture_catalog() -> Tuple[Dict[str, FurnitureDef], Dict[str, str]]:
    catalog: Dict[str, FurnitureDef] = {}
    loc_map: Dict[str, str] = {}

    gpak = find_gpak_path()
    if gpak:
        files = read_files_from_gpak(gpak, ("furniture", "house", "items.gon", "text/", "local", ".csv"))
        for fname, content in files.items():
            if fname.lower().endswith(".csv"):
                try:
                    reader = csv.reader(io.StringIO(content))
                    for row in reader:
                        if len(row) >= 2 and row[0].strip() and row[1].strip():
                            loc_map[row[0].strip()] = row[1].strip()
                            loc_map[row[0].strip().upper()] = row[1].strip()
                except Exception:
                    pass

        for fname, content in files.items():
            if not fname.lower().endswith(".gon"):
                continue
            if not any(w in fname.lower() for w in ("furn", "house", "item")):
                continue
            blocks = parse_gon_blocks(content)
            for item_id, blk in blocks.items():
                def _num(keys: Tuple[str, ...]) -> int:
                    for k in keys:
                        m = re.search(rf"\b{k}\b\s*[:=]?\s*(-?\d+)", blk, re.IGNORECASE)
                        if m:
                            return int(m.group(1))
                    return 0

                st = _num(("stimulation", "stim", "intelligence"))
                co = _num(("comfort", "comf"))
                he = _num(("health", "heal", "hp"))
                mu = _num(("mutation", "evolution", "mut", "evo"))
                ap = _num(("appeal", "app", "beauty"))
                fd = _num(("food_storage", "food", "storage", "capacity"))

                if st == 0 and co == 0 and he == 0 and mu == 0 and ap == 0 and fd == 0:
                    if not re.search(r"\b(size|type|comfort|stimulation|appeal|health|mutation|surface)\b", blk, re.I):
                        continue

                name_m = re.search(r'\bname\b\s*[:=]?\s*"([^"]+)"', blk, re.IGNORECASE)
                raw_name_token = name_m.group(1) if name_m else item_id
                pretty_name = _humanize_item_id(raw_name_token, loc_map)
                if pretty_name.upper().startswith("FURNITURE_"):
                    pretty_name = _humanize_item_id(item_id, loc_map)

                sz_m = re.search(r"\bsize\b\s*[:=]?\s*\[\s*(\d+)\s*[, ]+\s*(\d+)\s*\]", blk, re.IGNORECASE)
                w = int(sz_m.group(1)) if sz_m else 2
                h = int(sz_m.group(2)) if sz_m else 2

                totem = _infer_special_totem(item_id, pretty_name, st, co, he, mu, ap, fd)
                anchor, sock = _infer_anchor_and_socket(item_id, pretty_name, blk, w, h, totem)

                catalog[item_id.lower()] = FurnitureDef(
                    item_id=item_id, display_name=pretty_name, anchor_type=anchor,
                    width=w, height=h, provides_socket=sock,
                    stim=st, comfort=co, health=he, mutation=mu, appeal=ap,
                    food_storage=fd, special_totem=totem,
                )

    if save_parser is not None:
        for attr_name, val in vars(save_parser).items():
            if "furn" in attr_name.lower() and isinstance(val, dict):
                for k, v in val.items():
                    low_k = str(k).lower()
                    if low_k not in catalog and isinstance(v, dict):
                        dname = str(v.get("name", _humanize_item_id(str(k), loc_map)))
                        st = _to_int(v.get("stimulation", v.get("stim", 0)))
                        co = _to_int(v.get("comfort", v.get("comf", 0)))
                        he = _to_int(v.get("health", v.get("hp", 0)))
                        mu = _to_int(v.get("mutation", v.get("evolution", 0)))
                        ap = _to_int(v.get("appeal", 0))
                        fd = _to_int(v.get("food", v.get("food_storage", 0)))
                        tot = _infer_special_totem(low_k, dname, st, co, he, mu, ap, fd)
                        anc, sock = _infer_anchor_and_socket(low_k, dname, str(v), 2, 2, tot)
                        catalog[low_k] = FurnitureDef(str(k), dname, anc, 2, 2, sock, st, co, he, mu, ap, fd, tot)

    core_fallbacks = [
        ("idol_of_chastity",    "Idol of Chastity",    "idol",       1, 2, False,  0,  5,  0,  0,  0,   0, "chastity"),
        ("idol_of_chaos",       "Idol of Chaos",       "idol",       1, 2, False,  0, -5,  0,  0,  0,   0, "chaos"),
        ("idol_of_evolution",   "Idol of Evolution",   "idol",       1, 2, False,  0,  0,  0,  5,  0,   0, "evolution"),
        ("idol_of_stimulation", "Idol of Stimulation", "idol",       1, 2, False,  5,  0,  0,  0,  0,   0, "stim"),
        ("idol_of_health",      "Idol of Health",      "idol",       1, 2, False,  0,  0,  5,  0,  0,   0, "health"),
        ("idol_of_comfort",     "Idol of Comfort",     "idol",       1, 2, False,  0,  5,  0,  0,  0,   0, "comfort"),
        ("idol_of_appeal",      "Idol of Appeal",      "idol",       1, 2, False,  0,  0,  0,  0,  5,   0, "appeal"),
        ("sewer_small_table",   "Sewer Small Table",   "floor_base", 2, 2, True,   3, -1,  0,  0,  0,   0, ""),
        ("sewer_table",         "Sewer Table",         "floor_base", 3, 2, True,   4, -1,  0,  0,  0,   0, ""),
        ("food_storage_box",    "Food Storage Box",    "stackable",  2, 2, True,   0,  0,  0,  0,  0,  40, "food"),
        ("ethereal_skull",      "Ethereal Skull",      "stackable",  1, 1, True,   2, -1,  0,  3, -4,   0, ""),
        ("brain_of_glorg",      "Brain of Glorg",      "wall",       2, 2, False,  1, -1,  0,  4, -4,   0, ""),
        ("toxic_barrel",        "Toxic Barrel",        "stackable",  2, 2, True,   4, -2, -1,  2,  0,   0, ""),
        ("bleach_jug",          "Bleach Jug",          "topper",     1, 1, False,  3, -1,  1,  0,  0,   0, ""),
        ("robo_part",           "Robo Part",           "topper",     1, 1, False,  3, -1,  0,  0,  0,   0, ""),
        ("book_stack",          "Book Stack",          "topper",     1, 1, False,  2,  0,  0,  0, -1,   0, ""),
        ("medical_jar",         "Medical Jar",         "topper",     1, 1, False,  2,  0,  1,  1,  0,   0, ""),
        ("fairy_in_a_jar",      "Fairy in a Jar",      "topper",     1, 1, False,  1,  2,  3,  0,  2,   0, ""),
        ("bookshelf",           "Bookshelf",           "floor_base", 2, 4, True,   4,  1,  0,  0,  1,   0, ""),
        ("arcade_machine",      "Arcade Machine",      "floor_base", 2, 4, True,   5,  1,  0,  0,  2,   0, ""),
        ("television",          "Television",          "stackable",  2, 2, True,   3,  1,  0,  0,  0,   0, ""),
        ("outhouse",            "Outhouse",            "floor_base", 2, 4, True,   0,  3,  2,  0, -1,   0, ""),
        ("cat_bed",             "Cat Bed",             "floor_base", 3, 1, False,  0,  4,  2,  0,  0,   0, ""),
        ("plush_couch",         "Plush Couch",         "floor_base", 4, 2, False,  0,  4,  1,  0,  1,   0, ""),
        ("medkit",              "Medkit",              "topper",     1, 1, False,  0,  0,  4,  0,  0,   0, ""),
        ("iv_drip",             "IV Drip",             "floor_base", 1, 3, False,  0, -1,  5,  0,  0,   0, ""),
        ("angel_statue",        "Angel Statue",        "wall",       3, 3, False,  0,  2,  4,  0,  4,   0, ""),
        ("painting",            "Framed Painting",     "wall",       2, 2, False,  1,  1,  0,  0,  4,   0, ""),
    ]
    for fid, dname, anc, w, h, sock, st, co, he, mu, ap, fd, tot in core_fallbacks:
        if fid not in catalog:
            catalog[fid] = FurnitureDef(fid, dname, anc, w, h, sock, st, co, he, mu, ap, fd, tot)

    return catalog, loc_map


DEFAULT_HOUSE_JSON: Dict[str, Any] = {
    "rooms": {
        "Floor1_Large": {
            "id": "Floor1_Large", "label": "Ground floor, right", "w": 18, "h": 9, "free": 112,
            "grid": [
                "122222222222222221",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "122222222222222221",
            ],
        },
        "Floor1_Small": {
            "id": "Floor1_Small", "label": "Ground floor, left", "w": 18, "h": 9, "free": 112,
            "grid": [
                "122222222222222221",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "122222222222222221",
            ],
        },
        "SmallAttic": {
            "id": "SmallAttic", "label": "Attic (small house)", "w": 20, "h": 7, "free": 32,
            "grid": [
                "11222222222222222211",
                "11100000000000000111",
                "11122000000000022111",
                "11111220000002211111",
                "11111112200221111111",
                "11111111122111111111",
                "11111111111111111111",
            ],
        },
        "LargeAttic": {
            "id": "LargeAttic", "label": "Attic", "w": 37, "h": 11, "free": 136,
            "grid": [
                "1122222222222222222222222222222222211",
                "1110000000000000000000000000000000111",
                "1112200000000000000000000000000022111",
                "1111122000000000000000000000002211111",
                "1111111220000000000000000000221111111",
                "1111111112200000000000000022111111111",
                "1111111111122000000000002211111111111",
                "1111111111111220000000221111111111111",
                "1111111111111112200022111111111111111",
                "1111111111111111122211111111111111111",
                "1111111111111111111111111111111111111",
            ],
        },
        "Floor2_Large": {
            "id": "Floor2_Large", "label": "Upstairs, right", "w": 18, "h": 9, "free": 112,
            "grid": [
                "122222222222222221",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "122222222222222221",
            ],
        },
        "Floor2_Small": {
            "id": "Floor2_Small", "label": "Upstairs, left", "w": 18, "h": 9, "free": 112,
            "grid": [
                "122222222222222221",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "100000000000000001",
                "122222222222222221",
            ],
        },
    }
}


def load_notalim_databases(force_network: bool = False) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    house_data = dict(DEFAULT_HOUSE_JSON)
    if force_network or not NOTALIM_HOUSE_CACHE_FILE.exists():
        raw_h = _http_get_text(NOTALIM_HOUSE_URL, timeout=8)
        if raw_h:
            try:
                parsed_h = json.loads(raw_h)
                if isinstance(parsed_h, dict) and "rooms" in parsed_h:
                    house_data = parsed_h
                    NOTALIM_HOUSE_CACHE_FILE.write_text(raw_h, encoding="utf-8")
            except Exception:
                pass
    elif NOTALIM_HOUSE_CACHE_FILE.exists():
        try:
            parsed_h = json.loads(NOTALIM_HOUSE_CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(parsed_h, dict) and "rooms" in parsed_h:
                house_data = parsed_h
        except Exception:
            pass

    raw_furn_list: List[Dict[str, Any]] = []
    if force_network or not NOTALIM_FURN_CACHE_FILE.exists():
        raw_f = _http_get_text(NOTALIM_FURN_URL, timeout=10)
        if raw_f:
            try:
                parsed_f = json.loads(raw_f)
                if isinstance(parsed_f, list) and len(parsed_f) > 50:
                    raw_furn_list = parsed_f
                    NOTALIM_FURN_CACHE_FILE.write_text(raw_f, encoding="utf-8")
            except Exception:
                pass
    if not raw_furn_list and NOTALIM_FURN_CACHE_FILE.exists():
        try:
            parsed_f = json.loads(NOTALIM_FURN_CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(parsed_f, list):
                raw_furn_list = parsed_f
        except Exception:
            pass

    if force_network or not WHYAYALA_PARSER_CACHE_FILE.exists():
        raw_wp = _http_get_text(WHYAYALA_PARSER_URL, timeout=8)
        if raw_wp and "def " in raw_wp and "furniture" in raw_wp:
            try:
                WHYAYALA_PARSER_CACHE_FILE.write_text(raw_wp, encoding="utf-8")
            except Exception:
                pass

    catalog: Dict[str, Dict[str, Any]] = {}
    for entry in raw_furn_list:
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        fid = str(entry["id"]).strip()
        name = str(entry.get("name") or fid).strip()
        stats = entry.get("stats") or {}
        extra = entry.get("extra") or {}
        st = _to_int(stats.get("s", 0))
        co = _to_int(stats.get("c", 0))
        he = _to_int(stats.get("h", 0))
        mu = _to_int(stats.get("m", 0))
        ap = _to_int(stats.get("a", 0))
        fd = _to_int(extra.get("food", extra.get("food_storage", 40 if "foodbox" in fid.lower() else 0)))
        cells = [(int(c[0]), int(c[1]), int(c[2])) for c in (entry.get("cells") or []) if len(c) >= 3]
        if not cells:
            cells = [(0, 0, 3), (0, 1, 1)]
        w = max(int(entry.get("w") or 1), max((c[0] for c in cells), default=0) + 1)
        h = max(int(entry.get("h") or 2), max((c[1] for c in cells), default=0) + 1)
        kind = str(entry.get("kind") or "grounded")
        special = bool(entry.get("special", False))
        can_rare = bool(entry.get("canRare", not special))
        totem = _infer_special_totem(fid, name, st, co, he, mu, ap, fd)
        if "suppressor" in fid.lower():
            totem = "chastity"
        elif "fightidol" in fid.lower():
            totem = "chaos"
        if totem and totem != "food":
            can_rare = False

        catalog[fid.lower()] = {
            "id": fid, "name": name, "stim": st, "comfort": co, "health": he,
            "mutation": mu, "appeal": ap, "food": fd, "totem": totem,
            "cells": cells, "w": w, "h": h, "kind": kind, "can_rare": can_rare,
        }

    return catalog, house_data


MASTER_CATALOG, LOCALIZATION_MAP = load_master_furniture_catalog()
NOTALIM_CATALOG, NOTALIM_HOUSE = load_notalim_databases(force_network=False)


def _attach_notalim_meta(piece: FurniturePiece) -> FurniturePiece:
    clean = re.sub(r"^(furn_\d+_|db_\d+_|sp_\d+_|house_\d+_|canon_)", "", piece.item_id.lower().strip())
    for tag in ("_rare", "rare_", "(rare)", "★", "_shiny", "shiny_"):
        clean = clean.replace(tag, "").strip()

    rec = NOTALIM_CATALOG.get(clean)
    if rec is None:
        for k, v in NOTALIM_CATALOG.items():
            if v["name"].lower() == piece.name.lower() or k.endswith("_" + clean):
                rec = v
                break

    if rec is not None:
        piece.item_id = rec["id"]
        piece.name = rec["name"]
        piece.base_stim = rec["stim"]
        piece.base_comfort = rec["comfort"]
        piece.base_health = rec["health"]
        piece.base_mutation = rec["mutation"]
        piece.base_appeal = rec["appeal"]
        piece.base_food = rec["food"]
        piece.special_totem = rec["totem"]
        piece.width = rec["w"]
        piece.height = rec["h"]
        piece.cells = list(rec["cells"])
        piece.kind = rec["kind"]
        piece.can_rare = rec["can_rare"]
        if not piece.can_rare:
            piece.is_rare = False
    else:
        if not piece.cells:
            piece.cells = [(0, 0, 3), (0, 1, 2)]
            piece.kind = "grounded"
            piece.can_rare = True

    piece.solid_cells = [(dx, dy, t) for dx, dy, t in piece.cells if t in (1, 2)]
    piece.support_cells = [(dx, dy) for dx, dy, t in piece.cells if t == 2]
    piece.pin_cells = [(dx, dy) for dx, dy, t in piece.cells if t == 3]
    piece.headroom_cells = [(dx, dy) for dx, dy, t in piece.cells if t == 4]
    piece.provides_socket = len(piece.support_cells) > 0
    return piece


def lookup_furniture_piece(
    uid: str, raw_key: str, is_rare: bool = False,
    current_room: int = 0, current_room_label: str = "Storage",
    explicit_stats: Optional[Dict[str, int]] = None,
    rare_overrides: Optional[Set[str]] = None,
) -> FurniturePiece:
    clean_key = str(raw_key or "").strip()
    low_key = clean_key.lower()

    if any(r_tag in low_key for r_tag in ("_rare", "rare_", "(rare)", "★", "shiny", "golden", "_gold")):
        is_rare = True
        for r_tag in ("_rare", "rare_", "(rare)", "★", "shiny_", "_shiny", "_gold"):
            low_key = low_key.replace(r_tag, "").strip()

    if rare_overrides and uid in rare_overrides:
        is_rare = True

    norm_key = low_key.replace(" ", "_").replace("-", "_")
    matched_def: Optional[FurnitureDef] = MASTER_CATALOG.get(norm_key)

    if matched_def is None:
        for k, fdef in MASTER_CATALOG.items():
            if k == norm_key or (len(norm_key) >= 4 and (k in norm_key or norm_key in k or fdef.display_name.lower() in low_key)):
                matched_def = fdef
                break

    if matched_def is not None:
        if explicit_stats:
            for sk, base_v in (
                ("stim", matched_def.stim), ("comfort", matched_def.comfort),
                ("health", matched_def.health), ("mutation", matched_def.mutation),
                ("appeal", matched_def.appeal),
            ):
                if base_v != 0 and explicit_stats.get(sk) == base_v * 2:
                    is_rare = True

        piece = FurniturePiece(
            uid=uid, item_id=matched_def.item_id, name=matched_def.display_name,
            is_rare=is_rare, anchor_type=matched_def.anchor_type,
            width=matched_def.width, height=matched_def.height,
            provides_socket=matched_def.provides_socket,
            base_stim=matched_def.stim, base_comfort=matched_def.comfort,
            base_health=matched_def.health, base_mutation=matched_def.mutation,
            base_appeal=matched_def.appeal, base_food=matched_def.food_storage,
            special_totem=matched_def.special_totem,
            current_room=current_room, current_room_label=current_room_label,
        )
        return _attach_notalim_meta(piece)

    pretty = _humanize_item_id(clean_key, LOCALIZATION_MAP)
    st = (explicit_stats or {}).get("stim", 2)
    co = (explicit_stats or {}).get("comfort", 1)
    he = (explicit_stats or {}).get("health", 1)
    mu = (explicit_stats or {}).get("mutation", 0)
    ap = (explicit_stats or {}).get("appeal", 1)
    tot = _infer_special_totem(norm_key, pretty, st, co, he, mu, ap, 0)
    anc, sock = _infer_anchor_and_socket(norm_key, pretty, "", 2, 2, tot)

    piece = FurniturePiece(
        uid=uid, item_id=norm_key or uid, name=pretty,
        is_rare=is_rare, anchor_type=anc, width=2, height=2, provides_socket=sock,
        base_stim=st, base_comfort=co, base_health=he, base_mutation=mu, base_appeal=ap,
        base_food=0, special_totem=tot,
        current_room=current_room, current_room_label=current_room_label,
    )
    return _attach_notalim_meta(piece)


# =====================================================================
# 2. CAT DATA MODEL, PEDIGREE COI & PATCH 1.1+ BREEDING OPTIMIZER
# =====================================================================

@dataclass
class CatData:
    id: int
    name: str
    age: int
    is_kitten: bool
    status: str
    is_retired: bool = False
    sex: str = "Unknown"            # "Male", "Female", "Fluid", "Unknown"
    orientation: str = "Straight"   # "Straight", "Gay", "Bi"
    libido: str = "Average"         # "Low", "Average", "High"
    aggression: str = "Average"     # "Low", "Average", "High"
    room_id: int = 1
    room_label: str = "Attic"
    parents: Tuple[Optional[int], Optional[int]] = (None, None)
    lovers: Set[int] = field(default_factory=set)
    haters: Set[int] = field(default_factory=set)
    saved_inbredness: float = 0.0
    collar: str = ""
    stats: Dict[str, int] = field(default_factory=lambda: {
        "STR": 4, "DEX": 4, "CON": 4, "INT": 4, "SPD": 4, "CHA": 4, "LCK": 4
    })
    abilities: List[str] = field(default_factory=list)
    mutations: List[str] = field(default_factory=list)
    disorders: List[str] = field(default_factory=list)
    defects: List[str] = field(default_factory=list)
    injuries: List[str] = field(default_factory=list)

    @property
    def combat_sum(self) -> int:
        return sum(self.stats.get(k, 4) for k in COMBAT_STATS)

    @property
    def weighted_breed_stat_sum(self) -> float:
        """Applies CHA = 0.20 anti-Charisma-Drift weight across all 7 base stats."""
        return float(self.combat_sum) + (self.stats.get("CHA", 4) * 0.20)

    @property
    def sevens_count(self) -> int:
        return sum(1 for k in COMBAT_STATS if self.stats.get(k, 4) >= 7)

    @property
    def six_plus_count(self) -> int:
        return sum(1 for k in COMBAT_STATS if self.stats.get(k, 4) >= 6)

    @property
    def bad_disorder_count(self) -> int:
        return sum(1 for d in self.disorders if d.lower() not in BENEFICIAL_DISORDERS)

    @property
    def crippling_disorder_count(self) -> int:
        return sum(1 for d in self.disorders if d.lower() in CRIPPLING_DISORDERS)

    @property
    def good_disorder_count(self) -> int:
        return sum(1 for d in self.disorders if d.lower() in HIGH_VALUE_DISORDERS)

    @property
    def is_sterile(self) -> bool:
        return any("sterile" in d.lower() for d in self.disorders)

    @property
    def is_injured(self) -> bool:
        return len(self.injuries) > 0

    @property
    def body_mutation_bonus(self) -> float:
        score = float(len(self.mutations)) * 3.0
        for m in self.mutations:
            low_m = m.lower()
            if any(meta in low_m for meta in META_BODY_MUTATIONS):
                score += 13.0
        return score

    @property
    def meta_skill_bonus(self) -> float:
        all_skills = [a.lower() for a in (self.abilities + self.mutations)]
        bonus = sum(12.0 for a in all_skills if any(ma in a for ma in META_ABILITIES))
        if any("skill share+" in a or "skillshare+" in a for a in all_skills):
            bonus += 28.0
        elif any("skill share" in a or "skillshare" in a for a in all_skills):
            bonus += 18.0
        bonus += sum(8.0 for a in all_skills if a in DOMINANT_POSITIVE_TRAITS)
        return bonus

    @property
    def defender_score(self) -> float:
        """Patch 1.1+ combat/defender score (Retired House-Boss Defenders & Adventure Squad)."""
        con_spd_bonus = (self.stats.get("CON", 4) + self.stats.get("SPD", 4)) * 0.65
        eight_plus_cnt = sum(1 for k in COMBAT_STATS if self.stats.get(k, 4) >= 8)
        good_dis_bonus = self.good_disorder_count * 16.0
        crippling_pen = self.crippling_disorder_count * 48.0
        injury_pen = len(self.injuries) * 6.0
        return (
            (self.combat_sum * 3.2)
            + con_spd_bonus
            + (self.sevens_count * 13.0)
            + (eight_plus_cnt * 8.5)
            + (len(self.abilities) * 5.0)
            + self.meta_skill_bonus
            + good_dis_bonus
            + self.body_mutation_bonus
            - (self.bad_disorder_count * 25.0)
            - crippling_pen
            - (len(self.defects) * 18.0)
            - injury_pen
            - (22.0 if self.age >= 14 else 0.0)
        )

    @property
    def breeder_score(self) -> float:
        """Individual genetic quality for Chapel breeding (anti-CHA-drift, defect-averse)."""
        if self.is_sterile:
            return -9999.0
        libido_bonus = 6.0 if self.libido == "High" else (-8.0 if self.libido == "Low" else 0.0)
        agg_pen = 10.0 if self.aggression == "High" else 0.0
        fluid_risk_pen = 5.0 if self.sex == "Fluid" else 0.0
        age_pen = 14.0 if self.age >= 12 else (6.0 if self.age >= 9 else 0.0)
        return (
            (self.weighted_breed_stat_sum * 3.6)
            + (self.sevens_count * 16.0)
            + (self.six_plus_count * 5.0)
            + (self.meta_skill_bonus * 0.85)
            + (self.body_mutation_bonus * 0.90)
            + (self.good_disorder_count * 10.0)
            + libido_bonus
            - (self.bad_disorder_count * 32.0)
            - (self.crippling_disorder_count * 65.0)
            - (len(self.defects) * 24.0)
            - agg_pen
            - fluid_risk_pen
            - age_pen
        )


class PedigreeAnalyzer:
    """Exact recursive Wright's Coefficient of Inbreeding (COI) via tabular kinship."""

    def __init__(self, cats: List[CatData]):
        self.cat_map: Dict[int, CatData] = {c.id: c for c in cats if c.id > 0}
        self._gen_cache: Dict[int, int] = {}
        self._kin_cache: Dict[Tuple[int, int], float] = {}

    def generation(self, cid: Optional[int], visiting: Optional[Set[int]] = None) -> int:
        if cid is None or cid not in self.cat_map:
            return 0
        if cid in self._gen_cache:
            return self._gen_cache[cid]
        if visiting is None:
            visiting = set()
        if cid in visiting:
            return 0
        visiting.add(cid)
        p1, p2 = self.cat_map[cid].parents
        g = 1 + max(self.generation(p1, visiting), self.generation(p2, visiting))
        visiting.remove(cid)
        self._gen_cache[cid] = g
        return g

    def kinship(self, a: Optional[int], b: Optional[int], depth: int = 0) -> float:
        if a is None or b is None or depth > 14:
            return 0.0
        if a not in self.cat_map or b not in self.cat_map:
            return 0.0
        key = (a, b) if a <= b else (b, a)
        if key in self._kin_cache:
            return self._kin_cache[key]

        if a == b:
            p1, p2 = self.cat_map[a].parents
            if p1 is not None and p2 is not None and p1 in self.cat_map and p2 in self.cat_map:
                f_self = self.kinship(p1, p2, depth + 1)
            else:
                f_self = max(0.0, min(1.0, self.cat_map[a].saved_inbredness))
            val = 0.5 * (1.0 + f_self)
            self._kin_cache[key] = val
            return val

        ga = self.generation(a)
        gb = self.generation(b)
        if ga < gb:
            a, b = b, a
        p1, p2 = self.cat_map[a].parents
        if p1 is None and p2 is None:
            self._kin_cache[key] = 0.0
            return 0.0
        val = 0.5 * (self.kinship(p1, b, depth + 1) + self.kinship(p2, b, depth + 1))
        self._kin_cache[key] = val
        return val

    def pair_coi(self, cat_a: CatData, cat_b: CatData) -> float:
        """Returns expected Wright's COI [0.0..1.0] of a kitten produced by (cat_a, cat_b)."""
        if cat_a.id == cat_b.id:
            return 1.0
        return self.kinship(cat_a.id, cat_b.id)


@dataclass
class BreedingPairRec:
    cat_a: CatData
    cat_b: CatData
    coi: float
    expected_combat_sum: float
    expected_sevens: float
    pair_score: float
    room_target: str
    notes: str = ""


@dataclass
class HouseDemandProfile:
    """Closed-loop contract linking live breeding/roster state -> 2D furniture solver."""
    stage: str = "STAT_CONSOLIDATION"  # EARLY_FOUNDATION | STAT_CONSOLIDATION | ENDGAME_MUTATION_SKILLS
    unlocked_rooms: int = 4
    room_roles: List[str] = field(default_factory=lambda: ["breeding", "barracks", "fight_club", "mutation"])
    room_cat_counts: Dict[str, int] = field(default_factory=lambda: {
        "breeding": 4, "barracks": 10, "fight_club": 4, "mutation": 3, "secondary_breed": 2
    })
    has_chastity_idol: bool = False
    has_chaos_idol: bool = False
    has_evo_idol: bool = False
    max_achievable_mut: int = 0
    enable_mutation_lab: bool = False
    has_beneficial_disorder_breeder: bool = False
    has_bad_disorder_patient: bool = False
    target_stim: int = 95
    target_appeal: int = 100
    prefer_attic_size: str = "LargeAttic"


@dataclass
class BreedingPlan:
    stage: str
    demand: HouseDemandProfile
    primary_pairs: List[BreedingPairRec] = field(default_factory=list)
    secondary_pairs: List[BreedingPairRec] = field(default_factory=list)
    retired_defenders: List[CatData] = field(default_factory=list)
    adventure_squad: List[CatData] = field(default_factory=list)
    mutation_candidates: List[CatData] = field(default_factory=list)
    fight_pit_cats: List[CatData] = field(default_factory=list)
    barracks_cats: List[CatData] = field(default_factory=list)
    cull_queue: List[Tuple[CatData, str]] = field(default_factory=list)
    vip_protect_ids: List[int] = field(default_factory=list)
    room_stim_used: int = 32
    notes: List[str] = field(default_factory=list)


def _are_cats_biologically_compatible(a: CatData, b: CatData) -> Tuple[bool, str]:
    """Checks vanilla Mewgenics sex, orientation, sterile, lover & hater rules."""
    if a.id == b.id or a.is_sterile or b.is_sterile:
        return False, "Sterile/Self"
    if b.id in a.haters or a.id in b.haters:
        return False, "Rivals (Hates)"

    sa, sb = a.sex, b.sex
    # Male+Female or anything with Fluid can produce kittens; Unknown assumes compatible
    if sa in ("Male", "Female") and sb in ("Male", "Female") and sa == sb:
        return False, f"Same-Sex ({sa})"

    # Orientation check
    oa, ob = a.orientation, b.orientation
    if oa == "Gay" and sa in ("Male", "Female") and sb in ("Male", "Female") and sa != sb:
        return False, "Gay Orientation"
    if ob == "Gay" and sa in ("Male", "Female") and sb in ("Male", "Female") and sa != sb:
        return False, "Gay Orientation"

    # Monogamy protection: don't break up existing Loves pairs
    if a.lovers and b.id not in a.lovers:
        return False, "Bonded to Other Lover"
    if b.lovers and a.id not in b.lovers:
        return False, "Bonded to Other Lover"

    note = "Loves ❤️" if (b.id in a.lovers or a.id in b.lovers) else ""
    if sa == "Fluid" or sb == "Fluid":
        note = (note + " Fluid(?)").strip()
    return True, note


def evaluate_breeding_pair(
    a: CatData, b: CatData, coi: float, room_stim: int
) -> Optional[BreedingPairRec]:
    """
    Exact SciresM + Patch 1.1 expected-offspring scorer:
      - Patch 1.1 reduces effective Stimulation when COI > 0 and spikes birth-defect inheritance.
      - Computes expected combat stat sum, expected 7-count, complementarity gain, and skill/mutation transfer.
    """
    ok, rel_note = _are_cats_biologically_compatible(a, b)
    if not ok:
        return None
    if coi > 0.125:
        return None

    # Patch 1.1: inbreeding attenuates effective Stimulation
    eff_stim = max(0.0, float(room_stim) * max(0.25, 1.0 - (coi * 3.5)))
    p_high = (1.0 + 0.01 * eff_stim) / (2.0 + 0.01 * eff_stim)

    exp_sum = 0.0
    exp_sevens = 0.0
    complement_bonus = 0.0
    for k in COMBAT_STATS:
        va = a.stats.get(k, 4)
        vb = b.stats.get(k, 4)
        hi, lo = (va, vb) if va >= vb else (vb, va)
        exp_k = (p_high * hi) + ((1.0 - p_high) * lo)
        exp_sum += exp_k
        if hi >= 7 and lo >= 7:
            exp_sevens += 1.0
        elif hi >= 7:
            exp_sevens += p_high
            complement_bonus += 3.5  # Consolidating a 7 across bloodlines!

    # Skill & Mutation inheritance at current room_stim
    p_sp1 = min(1.0, 0.20 + 0.025 * eff_stim)
    p_pas = min(1.0, 0.05 + 0.01 * eff_stim)
    skill_val = (a.meta_skill_bonus + b.meta_skill_bonus) * 0.5 * (0.65 * p_sp1 + 0.35 * p_pas)
    mut_val = (a.body_mutation_bonus + b.body_mutation_bonus) * 0.5 * (0.5 + 0.5 * p_high)
    good_dis_val = (a.good_disorder_count + b.good_disorder_count) * 4.5

    # Patch 1.1 defect & COI penalties: COI >= 0.05 adds 1.5*COI new birth-defect chance!
    defect_pen = (len(a.defects) + len(b.defects)) * (16.0 + coi * 140.0)
    bad_dis_pen = (a.bad_disorder_count + b.bad_disorder_count) * 18.0
    crip_pen = (a.crippling_disorder_count + b.crippling_disorder_count) * 55.0
    coi_pen = (coi * 180.0) + (35.0 if coi >= 0.05 else 0.0)

    # Anti-Charisma Drift & Libido/Love adjustments
    cha_avg = (a.stats.get("CHA", 4) + b.stats.get("CHA", 4)) * 0.5
    love_bonus = 22.0 if (b.id in a.lovers or a.id in b.lovers) else 0.0
    agg_pen = (12.0 if a.aggression == "High" else 0.0) + (12.0 if b.aggression == "High" else 0.0)
    lib_bonus = (6.0 if a.libido == "High" else (-6.0 if a.libido == "Low" else 0.0)) + (
        6.0 if b.libido == "High" else (-6.0 if b.libido == "Low" else 0.0)
    )

    score = (
        (exp_sum * 4.2)
        + (exp_sevens * 22.0)
        + complement_bonus
        + skill_val
        + mut_val
        + good_dis_val
        + love_bonus
        + lib_bonus
        + (cha_avg * 0.4)
        - defect_pen
        - bad_dis_pen
        - crip_pen
        - coi_pen
        - agg_pen
    )

    notes_parts = []
    if rel_note:
        notes_parts.append(rel_note)
    if coi == 0.0:
        notes_parts.append("0% COI Outcross")
    else:
        notes_parts.append(f"COI {coi*100:.1f}%")
    if complement_bonus >= 7.0:
        notes_parts.append("High 7-Synergy")
    return BreedingPairRec(
        cat_a=a, cat_b=b, coi=coi,
        expected_combat_sum=exp_sum, expected_sevens=exp_sevens,
        pair_score=score, room_target="Room 1: Chapel",
        notes=" | ".join(notes_parts),
    )


class AdaptiveOptimizer:
    """
    Closed-loop Breeding, Progression & Roster Strategy Engine.
    Computes optimal breeding pairs, room assignments, protection IDs, and the HouseDemandProfile
    that dynamically steers the 2D spatial furniture solver.
    """

    def __init__(
        self,
        cats: List[CatData],
        room_count: int = 4,
        furniture: Optional[List[FurniturePiece]] = None,
        solved_stim: Optional[int] = None,
        prefer_attic_size: str = "LargeAttic",
    ):
        self.cats = cats
        self.room_count = max(1, min(5, room_count))
        self.furniture = furniture or []
        self.solved_stim = solved_stim
        self.prefer_attic_size = prefer_attic_size
        self.pedigree = PedigreeAnalyzer(cats)

    def _detect_demand_and_stage(self, living_house: List[CatData]) -> HouseDemandProfile:
        totems = {p.special_totem for p in self.furniture if p.special_totem}
        has_chastity = "chastity" in totems
        has_chaos = "chaos" in totems
        has_evo = "evolution" in totems

        pos_mut_total = sum(max(0, p.mutation) for p in self.furniture)
        pos_stim_total = sum(max(0, p.stim) for p in self.furniture)
        enable_mut_lab = (self.room_count >= 4) and (has_evo or pos_mut_total > 10)

        adults = [c for c in living_house if not c.is_kitten]
        top_sums = sorted((c.combat_sum for c in adults), reverse=True)[:4]
        avg_top_sum = (sum(top_sums) / len(top_sums)) if top_sums else 24.0
        multi_seven_cnt = sum(1 for c in adults if c.sevens_count >= 3)

        if self.room_count <= 2 or len(self.furniture) < 14 or avg_top_sum < 32.0:
            stage = "EARLY_FOUNDATION"
            target_stim = 32
            target_appeal = 50
        elif multi_seven_cnt >= 4 and (enable_mut_lab or pos_stim_total >= 95):
            stage = "ENDGAME_MUTATION_SKILLS"
            target_stim = 196 if pos_stim_total >= 130 else 100
            target_appeal = 200
        else:
            stage = "STAT_CONSOLIDATION"
            target_stim = 95 if pos_stim_total >= 55 else 32
            target_appeal = 100

        # Dynamic room roles adapting to progression and Patch 1.1 >10 Mutation threshold
        roles = ["breeding"]
        if self.room_count >= 2:
            roles.append("barracks")
        if self.room_count >= 3:
            roles.append("fight_club")
        if self.room_count >= 4:
            roles.append("mutation" if enable_mut_lab else "secondary_breed")
        if self.room_count >= 5:
            roles.append("secondary_breed" if enable_mut_lab else "appeal_overflow")

        attic_id = self.prefer_attic_size
        if self.room_count <= 2:
            attic_id = "SmallAttic"

        return HouseDemandProfile(
            stage=stage,
            unlocked_rooms=self.room_count,
            room_roles=roles,
            has_chastity_idol=has_chastity,
            has_chaos_idol=has_chaos,
            has_evo_idol=has_evo,
            max_achievable_mut=pos_mut_total,
            enable_mutation_lab=enable_mut_lab,
            target_stim=target_stim,
            target_appeal=target_appeal,
            prefer_attic_size=attic_id,
        )

    def _select_best_non_overlapping_pairs(
        self, pool: List[CatData], room_stim: int, max_pairs: int, room_label: str
    ) -> List[BreedingPairRec]:
        cands: List[BreedingPairRec] = []
        n = len(pool)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = pool[i], pool[j]
                coi = self.pedigree.pair_coi(a, b)
                rec = evaluate_breeding_pair(a, b, coi, room_stim)
                if rec is not None:
                    rec.room_target = room_label
                    cands.append(rec)

        cands.sort(key=lambda r: r.pair_score, reverse=True)
        chosen: List[BreedingPairRec] = []
        used: Set[int] = set()
        for rec in cands:
            if rec.cat_a.id in used or rec.cat_b.id in used:
                continue
            chosen.append(rec)
            used.add(rec.cat_a.id)
            used.add(rec.cat_b.id)
            if len(chosen) >= max_pairs:
                break
        return chosen

    def solve(self) -> Dict[str, Any]:
        living_house = [c for c in self.cats if c.status == "In House"]
        demand = self._detect_demand_and_stage(living_house)
        est_stim = self.solved_stim if self.solved_stim is not None else min(
            demand.target_stim, max(0, sum(max(0, p.stim) for p in self.furniture))
        )

        # 1. Top 4 Retired House-Boss Defenders (Guillotina / House Bosses)
        retired_pool = [c for c in living_house if c.is_retired and not c.is_kitten and c.age < 15]
        retired_pool.sort(key=lambda c: c.defender_score, reverse=True)
        retired_defenders = retired_pool[:4]
        retired_ids = {c.id for c in retired_defenders}

        # 2. Active Adventure Squad (Top 4 non-retired non-kitten combatants)
        active_adults = [c for c in living_house if not c.is_retired and not c.is_kitten]
        adventure_cands = [c for c in active_adults if c.crippling_disorder_count == 0]
        adventure_cands.sort(key=lambda c: c.defender_score, reverse=True)
        adventure_squad = adventure_cands[:4]

        # 3. Breeding Pool (non-kitten, fertile; retired cats CAN still breed in Mewgenics if healthy!)
        breed_eligible = [
            c for c in living_house
            if not c.is_kitten and not c.is_sterile and c.age < 15 and c.crippling_disorder_count == 0
        ]
        breed_eligible.sort(key=lambda c: c.breeder_score, reverse=True)
        top_breed_pool = breed_eligible[:18]

        # Primary Chapel: 2 monogamous/non-overlapping top pairs (4 cats keeps Comfort high & prevents jealousy)
        primary_pairs = self._select_best_non_overlapping_pairs(
            top_breed_pool, est_stim, max_pairs=2, room_label="Room 1: Chapel"
        )
        primary_ids = {c.id for pr in primary_pairs for c in (pr.cat_a, pr.cat_b)}

        # Secondary Breeding / Outcross Suite (if Room 4 repurposed or Room 5 unlocked)
        secondary_pairs: List[BreedingPairRec] = []
        if "secondary_breed" in demand.room_roles:
            rem_pool = [c for c in top_breed_pool if c.id not in primary_ids]
            sec_idx = demand.room_roles.index("secondary_breed") + 1
            secondary_pairs = self._select_best_non_overlapping_pairs(
                rem_pool, max(15, est_stim // 2), max_pairs=2, room_label=f"Room {sec_idx}: Outcross"
            )
        secondary_ids = {c.id for pr in secondary_pairs for c in (pr.cat_a, pr.cat_b)}

        # Check if any active primary breeder holds a beneficial S-tier disorder (avoid Health >10 curing it!)
        demand.has_beneficial_disorder_breeder = any(
            c.good_disorder_count > 0
            for pr in primary_pairs for c in (pr.cat_a, pr.cat_b)
        )

        # 4. Mutation Lab Candidates (only if Patch 1.1 >10 Mutation Lab is active!)
        mutation_candidates: List[CatData] = []
        if "mutation" in demand.room_roles:
            mut_pool = [
                c for c in active_adults
                if c.id not in primary_ids and c.id not in secondary_ids
                and len(c.mutations) < 10 and c.crippling_disorder_count == 0
                and (c.sevens_count >= 2 or c.combat_sum >= 33)
            ]
            mut_pool.sort(key=lambda c: (c.sevens_count, c.combat_sum, -len(c.mutations)), reverse=True)
            mutation_candidates = mut_pool[:4]
        mut_ids = {c.id for c in mutation_candidates}

        # 5. Barracks / Nursery Safe-Haven: Kittens + Retired Defenders + Adventure Squad + Bad-Disorder Patients
        barracks_ids: Set[int] = set()
        barracks_cats: List[CatData] = []
        for c in living_house:
            if c.id in primary_ids or c.id in secondary_ids or c.id in mut_ids:
                continue
            needs_ward = (
                c.is_kitten
                or c.id in retired_ids
                or any(a.id == c.id for a in adventure_squad)
                or (c.bad_disorder_count > 0 and c.breeder_score > 110.0)
            )
            if needs_ward:
                barracks_cats.append(c)
                barracks_ids.add(c.id)

        demand.has_bad_disorder_patient = any(c.bad_disorder_count > 0 for c in barracks_cats)

        # 6. Fight Pit & Baby Jack Rare-Furniture Farm (surplus adults when Room 3 unlocked)
        fight_pit_cats: List[CatData] = []
        fight_ids: Set[int] = set()
        if "fight_club" in demand.room_roles:
            surplus = [
                c for c in living_house
                if not c.is_kitten
                and c.id not in primary_ids
                and c.id not in secondary_ids
                and c.id not in mut_ids
                and c.id not in barracks_ids
            ]
            surplus.sort(key=lambda c: (c.is_injured, c.breeder_score))
            fight_pit_cats = surplus[:6]
            fight_ids = {c.id for c in fight_pit_cats}

        # 7. Smart NPC Donation / Culling Queue (when roster approaches 25-cat cap)
        cull_queue: List[Tuple[CatData, str]] = []
        protected_set = retired_ids | primary_ids | {c.id for c in adventure_squad}
        for c in living_house:
            if c.id in protected_set:
                continue
            if c.is_retired and c.id not in retired_ids:
                cull_queue.append((c, "Frank (5th+ Retired Surplus)"))
            elif c.is_injured and c.breeder_score < 130.0:
                cull_queue.append((c, "Baby Jack (Injured -> +Rare% Shop)"))
            elif c.is_kitten and c.combat_sum <= 26 and c.sevens_count == 0:
                cull_queue.append((c, "Tink (Low-Stat Kitten)"))
            elif c.age >= 14 or c.crippling_disorder_count > 0 or len(c.defects) >= 2:
                cull_queue.append((c, "Tracy / Beanies (Elderly or Defective)"))
        cull_queue.sort(key=lambda pair: pair[0].defender_score)

        # Update dynamic room cat counts for closed-loop furniture Comfort buffers
        demand.room_cat_counts = {
            "breeding": max(2, len(primary_ids)),
            "barracks": max(4, len(barracks_cats)),
            "fight_club": max(2, len(fight_pit_cats)),
            "mutation": max(2, len(mutation_candidates)),
            "secondary_breed": max(2, len(secondary_ids)),
            "appeal_overflow": 0,
        }

        # Auto-protected VIPs: Top 4 Retired Defenders + Top 2 Primary Stud/Dam Breeders
        vip_ids = [c.id for c in retired_defenders]
        if primary_pairs:
            for c in (primary_pairs[0].cat_a, primary_pairs[0].cat_b):
                if c.id > 0 and c.id not in vip_ids:
                    vip_ids.append(c.id)

        notes: List[str] = []
        if not demand.has_chastity_idol and self.room_count >= 2:
            notes.append("No Idol of Chastity yet -> Solver caps Barracks C+S+H+M below Attic so AutoCattery breeds in Attic.")
        if self.room_count >= 4 and not demand.enable_mutation_lab:
            notes.append(f"Max Mutation is {demand.max_achievable_mut} (<=10 Patch 1.1 dead zone) -> Room 4 repurposed as Outcross Suite.")
        if demand.has_beneficial_disorder_breeder:
            notes.append("Primary breeder has S-tier disorder -> Chapel Health soft-capped <=10 to prevent overnight cure.")

        plan_obj = BreedingPlan(
            stage=demand.stage,
            demand=demand,
            primary_pairs=primary_pairs,
            secondary_pairs=secondary_pairs,
            retired_defenders=retired_defenders,
            adventure_squad=adventure_squad,
            mutation_candidates=mutation_candidates,
            fight_pit_cats=fight_pit_cats,
            barracks_cats=barracks_cats,
            cull_queue=cull_queue[:10],
            vip_protect_ids=vip_ids,
            room_stim_used=est_stim,
            notes=notes,
        )

        return {
            "cats": self.cats,
            "adventure_squad": adventure_squad,
            "retired_defenders": retired_defenders,
            "primary_pairs": primary_pairs,
            "room_count": self.room_count,
            "demand": demand,
            "plan": plan_obj,
        }


# =====================================================================
# 3. UNIVERSAL SAVE READER (CATS + PEDIGREE + FURNITURE + ROOMS)
# =====================================================================

def _get_val(obj: Any, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if isinstance(obj, dict) and k in obj and obj[k] is not None:
            return obj[k]
        if hasattr(obj, k):
            val = getattr(obj, k)
            if val is not None:
                return val
    return default


def _normalize_sex(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in ("m", "male", "0", "boy"):
        return "Male"
    if s in ("f", "female", "1", "girl"):
        return "Female"
    if any(w in s for w in ("fluid", "ditto", "intersex", "both", "?", "2", "non")):
        return "Fluid"
    return "Unknown"


def _normalize_orientation(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if any(w in s for w in ("gay", "homo", "lesbian")):
        return "Gay"
    if any(w in s for w in ("bi", "pan")):
        return "Bi"
    return "Straight"


def _normalize_tier(raw: Any) -> str:
    if isinstance(raw, (int, float)):
        if raw >= 0.67 or raw >= 2:
            return "High"
        if raw <= 0.33 or raw == 0:
            return "Low"
        return "Average"
    s = str(raw or "").strip().lower()
    if "high" in s:
        return "High"
    if "low" in s:
        return "Low"
    return "Average"


def _extract_id(val: Any) -> Optional[int]:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val if val > 0 else None
    if isinstance(val, str) and val.strip().isdigit():
        iv = int(val.strip())
        return iv if iv > 0 else None
    for attr in ("db_key", "key", "id", "cat_id"):
        if hasattr(val, attr):
            iv = _to_int(getattr(val, attr), 0)
            if iv > 0:
                return iv
        if isinstance(val, dict) and attr in val:
            iv = _to_int(val[attr], 0)
            if iv > 0:
                return iv
    return None


def _extract_id_set(raw: Any) -> Set[int]:
    out: Set[int] = set()
    if raw is None:
        return out
    if isinstance(raw, (list, tuple, set)):
        for x in raw:
            iv = _extract_id(x)
            if iv:
                out.add(iv)
    else:
        iv = _extract_id(raw)
        if iv:
            out.add(iv)
    return out


def _extract_parents(rc: Any) -> Tuple[Optional[int], Optional[int]]:
    raw_parents = _get_val(rc, "parents", "parent_ids", default=None)
    if isinstance(raw_parents, (list, tuple)) and len(raw_parents) >= 2:
        return _extract_id(raw_parents[0]), _extract_id(raw_parents[1])
    p1 = _extract_id(_get_val(rc, "parent_a", "parent1", "father_id", "father", "sire", "dad", default=None))
    p2 = _extract_id(_get_val(rc, "parent_b", "parent2", "mother_id", "mother", "dam", "mom", default=None))
    return p1, p2


def _normalize_status(rc: Any) -> str:
    raw_status = str(_get_val(rc, "status", "location", "state", default="In House")).strip().lower()
    is_dead = bool(_get_val(rc, "is_dead", "dead", "gone", "is_gone", default=False))
    if is_dead or any(w in raw_status for w in ("gone", "dead", "sold", "donated", "missing")):
        return "Gone"
    if any(w in raw_status for w in ("adventure", "away", "run", "party", "expedition")):
        return "Adventure"
    return "In House"


def _extract_furniture_object_fields(rf: Any, idx: int) -> Tuple[str, bool, Any, Dict[str, int]]:
    pairs: List[Tuple[str, Any]] = []
    if isinstance(rf, dict):
        pairs = list(rf.items())
    elif hasattr(rf, "_asdict"):
        pairs = list(rf._asdict().items())
    elif hasattr(rf, "__dict__"):
        pairs = list(vars(rf).items())
    elif isinstance(rf, (list, tuple)):
        pairs = [(f"col_{i}", v) for i, v in enumerate(rf)]

    if not isinstance(rf, (dict, list, tuple)):
        seen_k = {k for k, _ in pairs}
        for k in dir(rf):
            if not k.startswith("_") and k not in seen_k:
                try:
                    val = getattr(rf, k)
                    if not callable(val):
                        pairs.append((k, val))
                except Exception:
                    pass

    raw_room: Any = "Storage"
    fname: Optional[str] = None
    is_rare: bool = False
    exp_stats: Dict[str, int] = {}
    room_keywords = {"attic", "largeattic", "smallattic", "floor1_small", "floor1_large", "floor2_small", "floor2_large", "storage", "stash"}

    for k, v in pairs:
        low_k = k.lower()
        if any(w in low_k for w in ("room", "location", "zone", "area")) and isinstance(v, (str, int)):
            raw_room = v
            break
        if isinstance(v, str) and v.strip().lower() in room_keywords:
            raw_room = v

    priority_name_keys = (
        "display_name", "item_name", "furniture_name", "name", "key", "item_key",
        "furniture_key", "def_key", "def_name", "template", "template_name",
        "gon_key", "asset", "asset_name", "sprite", "kind", "label", "title",
        "item_id", "furniture_id", "type", "id", "code", "model", "slug",
    )
    pair_dict = {k.lower(): v for k, v in pairs}
    for pk in priority_name_keys:
        if pk in pair_dict and isinstance(pair_dict[pk], str):
            cand = pair_dict[pk].strip()
            if cand and cand.lower() not in room_keywords and not cand.isdigit():
                fname = cand
                break

    if not fname:
        for _, v in pairs:
            if isinstance(v, str):
                cand = v.strip()
                if len(cand) >= 2 and cand.lower() not in room_keywords and not cand.isdigit():
                    fname = cand
                    break

    for k, v in pairs:
        low_k = k.lower()
        if any(w in low_k for w in ("rare", "shiny", "qual", "variant", "tier", "gold", "special", "upgrad", "flag", "mult")):
            if isinstance(v, bool) and v:
                is_rare = True
            elif isinstance(v, (int, float)) and v >= 1 and ("rare" in low_k or "shiny" in low_k or "variant" in low_k or "qual" in low_k or v == 2):
                is_rare = True
            elif isinstance(v, str) and any(w in v.lower() for w in ("rare", "shiny", "gold", "true", "2x", "★")):
                is_rare = True
        if isinstance(v, str) and any(w in v.lower() for w in ("_rare", "rare_", "shiny", "★", "(rare)")):
            is_rare = True

    for skey, names in (
        ("stim", ("stimulation", "stim")),
        ("comfort", ("comfort", "comf")),
        ("health", ("health", "hp", "heal")),
        ("mutation", ("mutation", "evolution", "mut", "evo")),
        ("appeal", ("appeal", "app", "beauty")),
    ):
        for nm in names:
            if nm in pair_dict and isinstance(pair_dict[nm], (int, float)):
                exp_stats[skey] = int(pair_dict[nm])
                break

    return fname or f"Mystery Piece #{idx+1}", is_rare, raw_room, exp_stats


def _parse_binary_furniture_blob(db_key: int, raw_b: bytes) -> Optional[Tuple[str, str, bool]]:
    if not raw_b or len(raw_b) < 10:
        return None
    try:
        import lz4.block
        if len(raw_b) > 12:
            uncomp_sz = struct.unpack_from("<I", raw_b, 0)[0]
            if 16 <= uncomp_sz <= 500_000:
                for hdr in (4, 8):
                    try:
                        dec = lz4.block.decompress(raw_b[hdr:], uncompressed_size=uncomp_sz)
                        if len(dec) >= 12:
                            raw_b = dec
                            break
                    except Exception:
                        pass
    except Exception:
        pass

    item_id: Optional[str] = None
    pos_after_id = 0
    for start_off in (4, 0, 8):
        for len_fmt, len_sz in (("<Q", 8), ("<I", 4)):
            if start_off + len_sz <= len(raw_b):
                slen = struct.unpack_from(len_fmt, raw_b, start_off)[0]
                s_end = start_off + len_sz + slen
                if 2 <= slen <= 64 and s_end <= len(raw_b):
                    chunk = raw_b[start_off + len_sz : s_end]
                    if all(32 <= b < 127 for b in chunk):
                        cand = chunk.decode("ascii", errors="ignore").strip()
                        if cand.lower() in NOTALIM_CATALOG or any(
                            cand.lower().startswith(p)
                            for p in ("object_", "wallmounted_", "ceiling_", "special_", "small_", "set_", "fightidol", "suppressor")
                        ):
                            item_id = cand
                            pos_after_id = s_end
                            break
        if item_id:
            break

    if not item_id:
        for m in re.finditer(rb"[A-Za-z][A-Za-z0-9_]{2,48}", raw_b):
            tok = m.group(0).decode("ascii", errors="ignore")
            if tok.lower().replace("_rare", "") in NOTALIM_CATALOG:
                item_id = tok
                pos_after_id = m.end()
                break
    if not item_id:
        return None

    room_name = "Storage"
    pos_before_room = len(raw_b)
    pos_after_room = pos_after_id
    for rm in ("LargeAttic", "SmallAttic", "Attic", "Floor1_Large", "Floor1_Small", "Floor2_Large", "Floor2_Small"):
        idx = raw_b.find(rm.encode("ascii"), pos_after_id)
        if idx != -1:
            room_name = rm
            pos_before_room = max(pos_after_id, idx - 8 if idx >= pos_after_id + 8 else idx - 4)
            pos_after_room = idx + len(rm)
            break

    is_rare = "_rare" in item_id.lower() or "rare_" in item_id.lower()
    rec = NOTALIM_CATALOG.get(item_id.lower().replace("_rare", ""))
    if rec and not rec["can_rare"]:
        is_rare = False
    elif not is_rare:
        tail = raw_b[pos_after_room:]
        gap = raw_b[pos_after_id:pos_before_room]
        meta = tail if len(tail) >= 4 else gap
        if room_name == "Storage" and len(meta) >= 8 and meta[:8] == b"\x00" * 8:
            meta = meta[8:]
        if len(meta) >= 8:
            cx, cy = struct.unpack_from("<ii", meta, 0)
            if -1 <= cx <= 40 and -1 <= cy <= 15:
                rem = meta[8:]
                if rem and (rem[0] == 1 or (len(rem) >= 4 and struct.unpack_from("<I", rem, 0)[0] == 1) or (len(rem) >= 5 and rem[4] == 1)):
                    is_rare = True
        elif len(meta) >= 1 and (meta[0] == 1 or (len(meta) >= 4 and struct.unpack_from("<I", meta, 0)[0] == 1)):
            is_rare = True
        if not is_rare and len(gap) in (1, 2, 4) and gap[0] == 1:
            is_rare = True

    return item_id, room_name, is_rare


def find_latest_save() -> Optional[Path]:
    appdata = os.environ.get("APPDATA", "")
    base_dir = Path(appdata) / "Glaiel Games" / "Mewgenics"
    if not base_dir.exists():
        return None
    sav_files = [
        p for p in base_dir.rglob("steamcampaign*.sav")
        if "backups" not in str(p).lower() and not str(p).endswith("_bak")
    ]
    return max(sav_files, key=lambda p: p.stat().st_mtime) if sav_files else None


def load_save_cats_and_furniture(sav_path: Path) -> Tuple[List[CatData], List[FurniturePiece], int]:
    """Safely snapshots SQLite + WAL/SHM sidecars and parses cats (with pedigree), furniture & unlocked rooms."""
    rare_overrides = load_rare_overrides()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_sav = Path(tmpdir) / sav_path.name
        shutil.copy2(sav_path, tmp_sav)
        for ext in ("-wal", "-shm", "-journal"):
            sidecar = sav_path.with_name(sav_path.name + ext)
            if sidecar.exists():
                shutil.copy2(sidecar, Path(tmpdir) / sidecar.name)

        cats: List[CatData] = []
        furniture: List[FurniturePiece] = []
        rooms_seen: Set[int] = {1}  # Never hardcode 4; accurately detect 1..5 unlocked rooms!

        parser_mods = []
        if WHYAYALA_PARSER_CACHE_FILE.exists():
            try:
                spec = importlib.util.spec_from_file_location("whyayala_save_parser", str(WHYAYALA_PARSER_CACHE_FILE))
                if spec and spec.loader:
                    wmod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(wmod)
                    parser_mods.append(wmod)
            except Exception:
                pass
        if save_parser is not None:
            parser_mods.append(save_parser)

        parsed = None
        for pmod in parser_mods:
            for fn_name in ("parse_save", "load_save", "read_save"):
                fn = getattr(pmod, fn_name, None)
                if callable(fn) and not isinstance(fn, type):
                    try:
                        parsed = fn(str(tmp_sav))
                        if parsed is not None:
                            break
                    except Exception:
                        continue
            if parsed is not None:
                break

        if parsed is not None:
            raw_cats = parsed[0] if isinstance(parsed, tuple) else getattr(parsed, "cats", None)
            if raw_cats is None and isinstance(parsed, dict):
                raw_cats = parsed.get("cats", [])
            if isinstance(raw_cats, dict):
                raw_cats = list(raw_cats.values())

            for rc in (raw_cats or []):
                status = _normalize_status(rc)
                r_id, r_lbl = _room_name_to_id(_get_val(rc, "room_id", "room", default="Attic"))
                if status == "In House" and r_id > 0:
                    rooms_seen.add(r_id)

                raw_stats = _get_val(rc, "base_stats", "stats", default=None)
                if isinstance(raw_stats, dict):
                    stats_dict = {k: _to_int(raw_stats.get(k, raw_stats.get(k.lower(), 4)), 4) for k in ALL_STATS}
                elif isinstance(raw_stats, (list, tuple)) and len(raw_stats) >= 7:
                    stats_dict = {k: _to_int(raw_stats[i], 4) for i, k in enumerate(ALL_STATS)}
                else:
                    stats_dict = {k: _to_int(_get_val(rc, k.lower(), k, default=4), 4) for k in ALL_STATS}

                age_val = _to_int(_get_val(rc, "age", default=3), 3)
                collar_val = str(_get_val(rc, "collar", "cat_class", default="") or "")
                is_retired = bool(
                    _get_val(rc, "is_retired", "retired", "has_adventured", "veteran", default=False)
                    or bool(collar_val)
                )

                cats.append(CatData(
                    id=_to_int(_get_val(rc, "db_key", "key", "id", default=0), 0),
                    name=str(_get_val(rc, "name", default="Cat")),
                    age=age_val,
                    is_kitten=bool(_get_val(rc, "is_kitten", default=(age_val < 2))),
                    status=status,
                    is_retired=is_retired,
                    sex=_normalize_sex(_get_val(rc, "sex", "gender", default="Unknown")),
                    orientation=_normalize_orientation(_get_val(rc, "orientation", "sexuality", "sexual_orientation", default="Straight")),
                    libido=_normalize_tier(_get_val(rc, "libido", default="Average")),
                    aggression=_normalize_tier(_get_val(rc, "aggression", default="Average")),
                    room_id=r_id if r_id > 0 else 1,
                    room_label=r_lbl,
                    parents=_extract_parents(rc),
                    lovers=_extract_id_set(_get_val(rc, "lovers", "loves", "lover_ids", "partner", default=None)),
                    haters=_extract_id_set(_get_val(rc, "haters", "hates", "hater_ids", "rivals", default=None)),
                    saved_inbredness=_to_float(_get_val(rc, "inbredness", "coi", "inbreeding", default=0.0), 0.0),
                    collar=collar_val,
                    stats=stats_dict,
                    abilities=[str(x) for x in (_get_val(rc, "abilities", "spells", default=[]) or [])],
                    mutations=[str(x) for x in (_get_val(rc, "mutations", default=[]) or [])],
                    disorders=[str(x) for x in (_get_val(rc, "disorders", default=[]) or [])],
                    defects=[str(x) for x in (_get_val(rc, "defects", "birth_defects", default=[]) or [])],
                    injuries=[str(x) for x in (_get_val(rc, "injuries", "wounds", default=[]) or [])],
                ))

            raw_furn = None
            for f_attr in ("furniture", "house_furniture", "placed_furniture", "house_items", "room_furniture"):
                cand = getattr(parsed, f_attr, None) if not isinstance(parsed, dict) else parsed.get(f_attr)
                if cand and not callable(cand):
                    raw_furn = cand
                    break

            flat_furn = []
            if isinstance(raw_furn, dict):
                for k_room, v_list in raw_furn.items():
                    if isinstance(v_list, (list, tuple)):
                        for it in v_list:
                            flat_furn.append((k_room, it))
                    else:
                        flat_furn.append((None, v_list))
            elif isinstance(raw_furn, (list, tuple)):
                for it in raw_furn:
                    if not (hasattr(it, "base_stats") or hasattr(it, "is_kitten")):
                        flat_furn.append((None, it))

            for idx, (parent_room, rf) in enumerate(flat_furn):
                fname, is_rare, raw_room, exp_stats = _extract_furniture_object_fields(rf, idx)
                if parent_room and str(raw_room) == "Storage":
                    raw_room = parent_room
                r_id, r_label = _room_name_to_id(raw_room)
                if r_id > 0:
                    rooms_seen.add(r_id)
                uid = f"furn_{idx+1}_{fname.lower().replace(' ', '_')}"
                p = lookup_furniture_piece(uid, fname, is_rare, r_id, r_label, exp_stats or None, rare_overrides)
                furniture.append(_attach_notalim_meta(p))

        # Direct SQLite binary scan for furniture & exact unlocked-room discovery
        try:
            conn = sqlite3.connect(str(tmp_sav))
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            db_pieces: List[FurniturePiece] = []
            rare_by_idx: Set[int] = set()

            for tname in tables:
                if tname.lower() == "cats":
                    continue
                cur.execute(f"SELECT * FROM [{tname}]")
                for row_idx, row in enumerate(cur.fetchall()):
                    row_key = row[0] if isinstance(row[0], int) else (row_idx + 1)
                    for col in row:
                        if isinstance(col, bytes):
                            for rm_tok in (b"Floor2_Small", b"Floor2_Large", b"Floor1_Small", b"Floor1_Large", b"LargeAttic"):
                                if rm_tok in col:
                                    r_id, _ = _room_name_to_id(rm_tok.decode("ascii"))
                                    if r_id > 0:
                                        rooms_seen.add(r_id)
                            res = _parse_binary_furniture_blob(row_key, col)
                            if res is not None:
                                item_id, rm_name, blob_rare = res
                                r_id, r_label = _room_name_to_id(rm_name)
                                if r_id > 0:
                                    rooms_seen.add(r_id)
                                uid = f"furn_{len(db_pieces)+1}_{item_id.lower()}"
                                if uid in rare_overrides:
                                    blob_rare = True
                                p = lookup_furniture_piece(uid, item_id, blob_rare, r_id, r_label, None, rare_overrides)
                                p = _attach_notalim_meta(p)
                                if p.is_rare:
                                    rare_by_idx.add(len(db_pieces))
                                db_pieces.append(p)
            conn.close()

            if not furniture and db_pieces:
                furniture = db_pieces
            elif furniture and len(db_pieces) == len(furniture):
                for idx, p in enumerate(furniture):
                    if idx in rare_by_idx and getattr(p, "can_rare", True):
                        p.is_rare = True
        except Exception:
            pass

        for p in furniture:
            _attach_notalim_meta(p)

        unlocked_rooms = max(1, min(5, max(rooms_seen) if rooms_seen else 1))
        return cats, furniture, unlocked_rooms


# =====================================================================
# 4. NON-DESTRUCTIVE AUTOCATTERY v0.5.35 PROTECTION SYNC
# =====================================================================

def _find_autocattery_dirs() -> List[Path]:
    found: List[Path] = []
    seen: Set[str] = set()
    for d in [
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Mewgenics\Mods\AutoCattery"),
        Path(r"C:\Program Files\Steam\steamapps\common\Mewgenics\Mods\AutoCattery"),
        Path(r"D:\SteamLibrary\steamapps\common\Mewgenics\Mods\AutoCattery"),
    ]:
        if d.exists():
            key = str(d.resolve()).lower()
            if key not in seen:
                seen.add(key)
                found.append(d)

    downloads = Path.home() / "Downloads"
    if downloads.exists():
        for mewtator_ac in downloads.rglob("Mewtator/mods/AutoCattery"):
            if mewtator_ac.is_dir():
                key = str(mewtator_ac.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    found.append(mewtator_ac)
    return found


def _load_managed_protection_ids() -> Set[int]:
    if MANAGED_PROTECTIONS_FILE.exists():
        try:
            data = json.loads(MANAGED_PROTECTIONS_FILE.read_text(encoding="utf-8"))
            return {int(x) for x in data.get("managed_cat_ids", []) if int(x) > 0}
        except Exception:
            pass
    return set()


def _save_managed_protection_ids(ids: Set[int]) -> None:
    try:
        _atomic_write_json(MANAGED_PROTECTIONS_FILE, {"managed_cat_ids": sorted(ids)})
    except Exception:
        pass


def update_retired_protection(
    cats: List[CatData], extra_protect_ids: Optional[List[int]] = None
) -> Tuple[List[CatData], int]:
    """
    Syncs Top-4 Retired House-Boss Defenders (+ optional VIP primary breeders) as `NoCull`
    into AutoCattery v0.5.35's `config/protection.json` WITHOUT disturbing any manual F10
    protection entries or identity_tokens.
    """
    retired = [c for c in cats if c.status == "In House" and c.is_retired and not c.is_kitten and c.age < 15]
    retired.sort(key=lambda c: c.defender_score, reverse=True)
    top_4 = retired[:4]

    desired_ids: List[int] = [c.id for c in top_4 if c.id > 0]
    for cid in (extra_protect_ids or []):
        if cid > 0 and cid not in desired_ids:
            desired_ids.append(cid)
    desired_set = set(desired_ids)

    prev_managed = _load_managed_protection_ids()
    ac_dirs = _find_autocattery_dirs()
    synced_count = 0

    for ac_dir in ac_dirs:
        # 1. Official AutoCattery v0.5.35 protection schema: Mods/AutoCattery/config/protection.json
        prot_path = ac_dir / "config" / "protection.json"
        existing: Dict[str, Any] = {"schema_version": 1, "records": []}
        if prot_path.exists():
            try:
                loaded = json.loads(prot_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("records"), list):
                    existing = loaded
            except Exception:
                existing = {"schema_version": 1, "records": []}

        new_records: List[Dict[str, Any]] = []
        already_present_ids: Set[int] = set()

        for rec in existing.get("records", []):
            if not isinstance(rec, dict):
                continue
            cid = _to_int(rec.get("cat_id"), 0)
            if cid <= 0:
                new_records.append(rec)
                continue
            # If this record was previously added by autopilot AND has no user identity_token, drop if no longer desired
            is_autopilot_only = (cid in prev_managed) and not rec.get("identity_token")
            if is_autopilot_only and cid not in desired_set:
                continue
            # Preserve ALL user records (and their stronger levels / identity_tokens) intact!
            new_records.append(rec)
            already_present_ids.add(cid)

        for cid in desired_ids:
            if cid not in already_present_ids:
                new_records.append({"cat_id": cid, "level": "NoCull"})

        existing["schema_version"] = int(existing.get("schema_version", 1))
        existing["records"] = new_records
        try:
            _atomic_write_json(prot_path, existing)
            synced_count += 1
        except Exception:
            pass

    _save_managed_protection_ids(desired_set)
    return top_4, synced_count


def load_cats_safely(sav_path: Path) -> Tuple[List[CatData], int]:
    """Bridge function used by `ingame_button.py`."""
    cats, _, room_count = load_save_cats_and_furniture(sav_path)
    return cats, room_count


def sync_autocattery_config(plan: Dict[str, Any]) -> Tuple[List[CatData], int]:
    """Bridge function used by `ingame_button.py` & UI."""
    plan_obj: Optional[BreedingPlan] = plan.get("plan")
    vip_ids = plan_obj.vip_protect_ids if plan_obj else []
    top_4, synced = update_retired_protection(plan.get("cats", []), extra_protect_ids=vip_ids)
    try:
        if plan_obj is not None:
            summary = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "stage": plan_obj.stage,
                "room_stim_used": plan_obj.room_stim_used,
                "retired_defenders": [
                    {"id": c.id, "name": c.name, "combat_sum": c.combat_sum, "score": round(c.defender_score, 1)}
                    for c in plan_obj.retired_defenders
                ],
                "adventure_squad": [
                    {"id": c.id, "name": c.name, "combat_sum": c.combat_sum, "score": round(c.defender_score, 1)}
                    for c in plan_obj.adventure_squad
                ],
                "primary_pairs": [
                    {
                        "cat_a": pr.cat_a.name, "cat_b": pr.cat_b.name,
                        "coi": round(pr.coi, 4),
                        "expected_sum": round(pr.expected_combat_sum, 1),
                        "expected_7s": round(pr.expected_sevens, 2),
                    }
                    for pr in plan_obj.primary_pairs
                ],
                "notes": plan_obj.notes,
            }
            _atomic_write_json(PLAN_SUMMARY_FILE, summary)
    except Exception:
        pass
    return top_4, synced


# =====================================================================
# 5. 2D SPATIAL ROOM PACKER & CLOSED-LOOP HOUSE SCORING ENGINE
# =====================================================================

@dataclass
class RoomSpec:
    room_id: int
    internal_room_name: str
    name: str
    short_tab: str
    role: str
    floor_sockets: int
    wall_sockets: int
    ceiling_sockets: int
    max_stack_height: int
    placed: List[FurniturePiece] = field(default_factory=list)
    packer: Any = None
    placements: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def totals(self) -> Dict[str, int]:
        return {
            "Stimulation": sum(p.stim for p in self.placed),
            "Comfort": sum(p.comfort for p in self.placed),
            "Health": sum(p.health for p in self.placed),
            "Mutation": sum(p.mutation for p in self.placed),
            "Appeal": sum(p.appeal for p in self.placed),
            "FoodStorage": sum(p.food_storage for p in self.placed),
        }

    @property
    def autocattery_breed_sum(self) -> int:
        """Exact AutoCattery v0.5.35 room ranking metric: Comfort + Stimulation + Health + Mutation."""
        t = self.totals
        return t["Comfort"] + t["Stimulation"] + t["Health"] + t["Mutation"]

    @property
    def has_chastity(self) -> bool:
        return any(p.special_totem == "chastity" for p in self.placed)


def _piece_role_density(piece: FurniturePiece, role: str) -> float:
    """Role-aware stat value per occupied tile so high-value pieces get packed first inside each wave."""
    area = max(1.0, float(len(piece.solid_cells) or len(piece.headroom_cells) or 1))
    if role == "breeding":
        if piece.mutation > 0 or piece.special_totem in ("chastity", "chaos"):
            return -999.0
        val = (piece.stim * 6.5) + (piece.comfort * 2.2) + (piece.health * 1.8) + (piece.appeal * 1.2)
    elif role == "barracks":
        if piece.special_totem == "chaos":
            return -999.0
        val = (piece.comfort * 4.5) + (piece.health * 5.2) + (piece.appeal * 2.4) + (40.0 if piece.special_totem == "chastity" else 0.0)
    elif role == "fight_club":
        if piece.comfort > 0 or piece.special_totem == "chastity":
            return -999.0
        val = (-piece.comfort * 6.0) + (piece.appeal * 3.8) + (piece.stim * 1.0) + (40.0 if piece.special_totem == "chaos" else 0.0)
    elif role == "mutation":
        val = (piece.mutation * 8.0) + (piece.health * 2.8) + (piece.comfort * 1.6) + (piece.appeal * 1.4) + (40.0 if piece.special_totem == "evolution" else 0.0)
    elif role == "secondary_breed":
        if piece.mutation > 0 or piece.special_totem in ("chastity", "chaos"):
            return -999.0
        val = (piece.stim * 5.0) + (piece.comfort * 3.0) + (piece.health * 2.0) + (piece.appeal * 2.2)
    else:  # appeal_overflow
        val = (piece.appeal * 6.0) + (piece.food_storage * 0.5) + (piece.comfort * 1.2)
    if piece.special_totem == "food":
        val += 14.0
    return val / area


def score_room_state(room: RoomSpec, demand: HouseDemandProfile) -> float:
    """
    Closed-loop SciresM + Patch 1.1+ Room Scorer driven by live `HouseDemandProfile`:
      - Dynamic Comfort buffers scale directly with actual routed cat counts in each room.
      - Respects Patch 1.1 >10 Mutation threshold and >10 Health disorder-cure mechanics.
      - Pushes Fight Pit to Comfort <= -10 so AutoCattery v0.5.35 strictly excludes it from breeding.
    """
    t = room.totals
    stim, comf, heal, mut, app = t["Stimulation"], t["Comfort"], t["Health"], t["Mutation"], t["Appeal"]
    totems = {p.special_totem for p in room.placed if p.special_totem}
    food_boxes = sum(1 for p in room.placed if p.special_totem == "food")
    cat_cnt = demand.room_cat_counts.get(room.role, 4)
    # Every cat past 4 adds -1 Comfort overcrowding; plus 2-poop morning buffer + safety margin
    dynamic_comf_floor = max(8, cat_cnt + 6)
    global_bonus = (app * (2.6 if demand.stage == "EARLY_FOUNDATION" else 1.9)) + (food_boxes * 26.0) + (len(room.placed) * 0.35)

    if room.role == "breeding":
        if "chastity" in totems:
            return -999999.0
        if "chaos" in totems:
            return -60000.0

        eff_s = max(0, stim)
        p_better = (1.0 + 0.01 * eff_s) / (2.0 + 0.01 * eff_s)
        p_spell1 = min(1.0, 0.20 + 0.025 * eff_s)
        p_passive = min(1.0, 0.05 + 0.01 * eff_s)
        p_class_favor = min(1.0, 0.01 * eff_s)
        p_spell2 = min(1.0, 0.02 + 0.005 * eff_s)

        breakpoints = (
            (60.0 if stim >= 32 else p_spell1 * 45.0)
            + (85.0 if stim >= 95 else p_passive * 65.0)
            + (30.0 if stim >= 100 else p_class_favor * 22.0)
            + (55.0 if stim >= 196 else p_spell2 * 35.0)
        )
        breed_comf_target = max(12, cat_cnt + 8)
        comf_pen = max(0, breed_comf_target - comf) * 52.0
        comf_pad = min(comf, breed_comf_target + 10) * 2.0

        # Health >= 8 protects stud longevity; cap <= 10 if a primary breeder holds an S-tier disorder!
        heal_pen = max(0, 8 - heal) * 38.0
        disorder_cure_pen = (max(0, heal - 10) * 26.0) if demand.has_beneficial_disorder_breeder else 0.0

        # Patch 1.1: 1..10 Mutation rolls junk +2/-1 stat shifts; keep pure breeding Chapel at Mut <= 0
        mut_pen = max(0, mut) * 95.0
        totem_bonus = (
            (70.0 if "stim" in totems else 0.0)
            + (38.0 if "comfort" in totems else 0.0)
            + (28.0 if "health" in totems else 0.0)
        )
        stim_wt = 9.0 if demand.stage != "EARLY_FOUNDATION" else 7.8
        return (
            (stim * stim_wt) + (p_better * 250.0) + breakpoints + comf_pad + totem_bonus + global_bonus
            - (comf_pen + heal_pen + disorder_cure_pen + mut_pen)
        )

    elif room.role == "barracks":
        if "chaos" in totems:
            return -99999.0
        totem_bonus = 600.0 if "chastity" in totems else 0.0
        barracks_comf_target = max(14, cat_cnt + 6)
        comf_pen = max(0, barracks_comf_target - comf) * 34.0
        # Health >= 11 cures bad run disorders at +1%/pt above 10 per night!
        heal_target = 13 if demand.has_bad_disorder_patient else 10
        heal_pen = max(0, heal_target - heal) * 34.0
        disorder_cure_bonus = max(0, heal - 10) * (11.0 if demand.has_bad_disorder_patient else 5.5)
        return (
            totem_bonus + (comf * 5.0) + (heal * 7.2) + disorder_cure_bonus + (app * 4.2) + global_bonus
            - (comf_pen + heal_pen)
        )

    elif room.role == "fight_club":
        if "chastity" in totems:
            return -60000.0
        totem_bonus = 600.0 if "chaos" in totems else 0.0
        # AutoCattery excludes rooms with Comfort <= -10 from breeding! Reward reaching <= -10 strongly.
        if comf <= -10:
            comf_score = 120.0 + (abs(comf) * 6.5)
        elif comf <= -5:
            comf_score = 45.0 + (abs(comf) * 7.5)
        elif comf <= 0:
            comf_score = -comf * 6.0
        else:
            comf_score = -comf * 36.0
        # Health [0..5] farms injured losers for Baby Jack's +1%/cat Rare furniture shop scaling
        heal_band = 32.0 if (0 <= heal <= 5) else -abs(heal - 2) * 9.5
        return totem_bonus + comf_score + heal_band + (app * 6.0) + (stim * 1.2) + global_bonus

    elif room.role == "mutation":
        if "chastity" in totems:
            return -25000.0
        totem_bonus = 600.0 if "evolution" in totems else 0.0
        # Patch 1.1: <= 10 Mutation only rolls basic +2/-1 stat shifts; >10 rolls effect mutations (+2.5%/pt)
        if mut > 10:
            mut_score = 210.0 + ((mut - 10) * 18.0)
        elif mut > 0:
            mut_score = (mut * 4.0) - 55.0
        else:
            mut_score = 0.0
        floor_pen = (max(0, 8 - heal) * 35.0) + (max(0, dynamic_comf_floor - 4 - comf) * 26.0)
        return totem_bonus + mut_score + (heal * 5.0) + (comf * 2.4) + (stim * 2.0) + global_bonus - floor_pen

    elif room.role == "secondary_breed":
        if "chastity" in totems or "chaos" in totems:
            return -50000.0
        eff_s = max(0, stim)
        spell1_bonus = 60.0 if eff_s >= 32 else (eff_s * 1.6)
        floor_pen = (max(0, 10 - comf) * 32.0) + (max(0, 6 - heal) * 22.0) + (max(0, mut) * 55.0)
        return spell1_bonus + (stim * 5.8) + (comf * 4.0) + (heal * 3.5) + (app * 4.8) + global_bonus - floor_pen

    else:  # appeal_overflow
        return (app * 7.5) + (comf * 2.0) + (heal * 2.0) + global_bonus


def score_house_state(rooms: List[RoomSpec], demand: HouseDemandProfile) -> float:
    """
    Whole-house objective:
      1. Sums per-room strategic scores.
      2. Rewards House-Wide Appeal Stray milestones (50 / 100 / 200).
      3. Enforces AutoCattery v0.5.35 Breeding-Room Dominance:
         Ensures Room 1 (`breeding`) strictly beats every other breeding-eligible room
         (non-Chastity, Comfort > -10) on `Comfort + Stimulation + Health + Mutation`!
    """
    room_sum = sum(score_room_state(r, demand) for r in rooms)
    total_appeal = sum(r.totals["Appeal"] for r in rooms)
    appeal_milestone = (
        (115.0 if total_appeal >= 200 else 0.0)
        + (75.0 if total_appeal >= 100 else 0.0)
        + (30.0 if total_appeal >= 50 else 0.0)
    )

    # AutoCattery v0.5.35 Breeding-Room Lock Guard
    ac_penalty = 0.0
    breed_room = next((r for r in rooms if r.role == "breeding"), None)
    if breed_room is not None:
        breed_ac = breed_room.autocattery_breed_sum
        if breed_room.totals["Comfort"] <= -10 or breed_room.has_chastity:
            ac_penalty += 5000.0
        for other in rooms:
            if other.room_id == breed_room.room_id:
                continue
            # AutoCattery considers a room breeding-eligible if it has no Chastity Idol and Comfort > -10
            if not other.has_chastity and other.totals["Comfort"] > -10:
                other_ac = other.autocattery_breed_sum
                if other_ac >= breed_ac - 4:
                    ac_penalty += (other_ac - breed_ac + 5) * 48.0

    return room_sum + appeal_milestone - ac_penalty


class RoomGridPacker:
    """
    Exact 2D grid packer using notalim/mewgenics-house-planner's 4 cell types (1, 2, 3, 4):
      1 = Solid
      2 = Solid + Support Shelf (●)
      3 = Pin / Anchor (+)
      4 = Background / Headroom (□)
    Upgraded in v10.0 with:
      - Left-wall scanning from x0 = 0 (fixes wall-mounted left-edge anchors).
      - Multi-column Attic sloped-roof clearance across ALL solid/support columns.
      - Support-bolt preservation (prevents 1-wide toppers from fragmenting wide shelves).
      - Role-aware value sorting inside waves + multi-heuristic best-packing selection.
    """

    def __init__(self, room_json_id: str, house_data: Dict[str, Any]):
        r_info = house_data.get("rooms", {}).get(room_json_id) or DEFAULT_HOUSE_JSON["rooms"]["Floor1_Large"]
        self.room_json_id = room_json_id
        self.w = int(r_info["w"])
        self.h = int(r_info["h"])
        self.free_tiles = int(r_info.get("free", 112))
        self.is_attic = "attic" in room_json_id.lower()

        grid_strs: List[str] = r_info["grid"]
        self.base_grid = [[1] * self.w for _ in range(self.h)]
        for y in range(self.h):
            for x in range(min(self.w, len(grid_strs[y]))):
                val = int(grid_strs[y][x])
                if self.is_attic and y >= 1 and val == 2:
                    val = 1  # Sloped Attic roof cannot hang anything
                self.base_grid[y][x] = val

        # Precompute vertical clearance above every tile (x, y)
        self.col_clearance = [[0] * self.w for _ in range(self.h)]
        for x in range(self.w):
            for y in range(self.h):
                if self.base_grid[y][x] in (0, 2):
                    c_cnt = 0
                    for yy in range(y + 1, self.h):
                        if self.base_grid[yy][x] == 0:
                            c_cnt += 1
                        else:
                            break
                    self.col_clearance[y][x] = c_cnt

        self.reset()

    def reset(self) -> None:
        self.occupied = [[False] * self.w for _ in range(self.h)]
        self.wall_occupied = [[False] * self.w for _ in range(self.h)]
        self.floor_support = [[False] * self.w for _ in range(self.h)]
        self.ceil_support = [[False] * self.w for _ in range(self.h)]
        self.used_support = [[False] * self.w for _ in range(self.h)]
        self.support_owner: List[List[Optional[FurniturePiece]]] = [[None] * self.w for _ in range(self.h)]

        for x in range(self.w):
            if self.base_grid[0][x] == 2:
                self.floor_support[0][x] = True
            if not self.is_attic and self.base_grid[self.h - 1][x] == 2:
                self.ceil_support[self.h - 1][x] = True
        self.placements: List[Dict[str, Any]] = []

    @staticmethod
    def _orientations(piece: FurniturePiece) -> List[Tuple[List[Tuple[int, int, int]], bool]]:
        norm = piece.cells
        w = piece.width
        flipped = [(w - 1 - dx, dy, t) for dx, dy, t in norm]
        if set(flipped) == set(norm):
            return [(norm, False)]
        return [(norm, False), (flipped, True)]

    def can_place_cells(self, piece: FurniturePiece, cells: List[Tuple[int, int, int]], x0: int, y0: int) -> bool:
        if x0 < 0 or y0 < 0 or x0 + piece.width > self.w or y0 + piece.height > self.h:
            return False
        is_hanging = getattr(piece, "kind", "grounded") == "hanging"
        is_mixed = getattr(piece, "kind", "") == "mixed"
        is_pure_wall = not piece.solid_cells and not piece.pin_cells

        for dx, dy, t in cells:
            rx, ry = x0 + dx, y0 + dy
            if rx < 0 or rx >= self.w or ry < 0 or ry >= self.h:
                return False
            if t == 3:
                if self.used_support[ry][rx]:
                    return False
                if is_hanging:
                    if not self.ceil_support[ry][rx]:
                        return False
                elif is_mixed and dy > 0:
                    if not (self.floor_support[ry][rx] or self.base_grid[ry][rx] in (1, 2)):
                        return False
                else:
                    if not self.floor_support[ry][rx]:
                        return False
            elif t in (1, 2):
                if self.base_grid[ry][rx] != 0 or self.occupied[ry][rx]:
                    return False
            elif t == 4:
                if self.base_grid[ry][rx] != 0:
                    return False
                if is_pure_wall and self.wall_occupied[ry][rx]:
                    return False
        return True

    def place(self, piece: FurniturePiece, x0: int, y0: int, cells: List[Tuple[int, int, int]], is_flipped: bool) -> None:
        is_pure_wall = not piece.solid_cells and not piece.pin_cells
        deps: Set[str] = set()
        sources: List[str] = []

        for dx, dy, t in cells:
            rx, ry = x0 + dx, y0 + dy
            if t == 3:
                self.used_support[ry][rx] = True
                owner = self.support_owner[ry][rx]
                if owner is not None:
                    deps.add(owner.uid)
                    if owner.name not in sources:
                        sources.append(owner.name)
                elif ry == 0 and "Floor" not in sources:
                    sources.append("Floor")
                elif ry == self.h - 1 and "Ceiling" not in sources:
                    sources.append("Ceiling")
            elif t in (1, 2):
                self.occupied[ry][rx] = True
                if t == 2:
                    self.floor_support[ry][rx] = True
                    self.support_owner[ry][rx] = piece
            elif t == 4 and is_pure_wall:
                self.wall_occupied[ry][rx] = True

        flip_tag = " ⇄Flip" if is_flipped else ""
        if not piece.pin_cells:
            lbl = f"Wall/Floating (Col {x0}, R{y0}){flip_tag}"
        elif "Ceiling" in sources:
            lbl = f"Ceiling (Col {x0}){flip_tag}"
        elif sources and sources != ["Floor"]:
            non_flr = [s for s in sources if s != "Floor"]
            lbl = f"On {non_flr[0]} (Col {x0}, R{y0}){flip_tag}"
        else:
            lbl = f"Floor (Col {x0}){flip_tag}"

        self.placements.append({
            "piece": piece, "x0": x0, "y0": y0, "cells": cells, "is_flipped": is_flipped,
            "order_num": len(self.placements) + 1, "rests_on_label": lbl, "deps": deps,
        })

    def _headroom_for_cells(self, cells: List[Tuple[int, int, int]], x0: int, y0: int) -> int:
        """Exact minimum vertical clearance above a piece's top-most solid/support cells."""
        top_by_col: Dict[int, int] = {}
        for dx, dy, t in cells:
            if t in (1, 2):
                rx, ry = x0 + dx, y0 + dy
                if rx not in top_by_col or ry > top_by_col[rx]:
                    top_by_col[rx] = ry
        if not top_by_col:
            return self.col_clearance[y0][x0]
        return min(self.col_clearance[ry][rx] for rx, ry in top_by_col.items())

    def _adjacency_score(self, cells: List[Tuple[int, int, int]], x0: int, y0: int) -> float:
        """Counts solid-cell edge contacts with walls or already-placed neighbors (prevents 1-tile gaps)."""
        occ_local = {(x0 + dx, y0 + dy) for dx, dy, t in cells if t in (1, 2)}
        if not occ_local:
            return 0.0
        contacts = 0
        for rx, ry in occ_local:
            for nx in (rx - 1, rx + 1):
                if (nx, ry) in occ_local:
                    continue
                if nx < 0 or nx >= self.w or self.base_grid[ry][nx] != 0 or self.occupied[ry][nx]:
                    contacts += 1
        return min(4.0, float(contacts))

    def _pin_fragmentation_penalty(self, cells: List[Tuple[int, int, int]], x0: int, y0: int) -> float:
        """Penalizes placing a 1-pin topper in the middle of a contiguous open shelf, fragmenting it."""
        pins = [(x0 + dx, y0 + dy) for dx, dy, t in cells if t == 3]
        if len(pins) != 1:
            return 0.0
        px, py = pins[0]
        left_free = (px - 1 >= 0) and self.floor_support[py][px - 1] and not self.used_support[py][px - 1]
        right_free = (px + 1 < self.w) and self.floor_support[py][px + 1] and not self.used_support[py][px + 1]
        return 8.0 if (left_free and right_free) else 0.0

    def find_spot(
        self, piece: FurniturePiece, prefer_high: bool = False
    ) -> Optional[Tuple[int, int, List[Tuple[int, int, int]], bool]]:
        max_x, max_y = self.w - piece.width, self.h - piece.height
        if max_x < 0 or max_y < 0:
            return None
        orients = self._orientations(piece)

        if getattr(piece, "kind", "grounded") == "hanging":
            for y0 in range(max_y, -1, -1):
                for x0 in range(0, max_x + 1):
                    for cells, is_fl in orients:
                        if self.can_place_cells(piece, cells, x0, y0):
                            return (x0, y0, cells, is_fl)
            return None

        if not piece.pin_cells:
            y_ord = [y for y in (2, 3, 4, 1, 5, 6) if y <= max_y] if piece.support_cells else list(range(max_y, 0, -1))
            for y0 in y_ord:
                for x0 in range(0, max_x + 1):
                    for cells, is_fl in orients:
                        if self.can_place_cells(piece, cells, x0, y0):
                            return (x0, y0, cells, is_fl)
            return None

        best_cand = None
        best_score = -1e9
        has_shelves = len(piece.support_cells) > 0

        for y0 in range(0, max_y + 1):
            for x0 in range(0, max_x + 1):
                for cells, is_fl in orients:
                    if not self.can_place_cells(piece, cells, x0, y0):
                        continue
                    headroom_above = self._headroom_for_cells(cells, x0, y0)
                    adj_bonus = self._adjacency_score(cells, x0, y0) * 3.0
                    frag_pen = self._pin_fragmentation_penalty(cells, x0, y0) if not has_shelves else 0.0

                    if has_shelves and not prefer_high:
                        # Shelf providers want low y0 AND open headroom above their newly created shelves
                        sc = (-y0 * 18.0) + (min(headroom_above, 5) * 10.5) + adj_bonus - (x0 * 0.12) - (0.25 if is_fl else 0.0)
                    else:
                        # Pure toppers want elevated shelves (y0 >= 1) OR snug low-ceiling Attic eaves
                        elev_bonus = (y0 * 24.0) if y0 >= 1 else -30.0
                        snug_eave_bonus = (6.0 - min(headroom_above, 6)) * 5.0
                        sc = elev_bonus + snug_eave_bonus + adj_bonus - frag_pen + (x0 * 0.08) - (0.25 if is_fl else 0.0)

                    if sc > best_score:
                        best_score = sc
                        best_cand = (x0, y0, cells, is_fl)

        return best_cand

    def _pack_single_strategy(
        self, items: List[FurniturePiece], role: str, mode: str = "value"
    ) -> Tuple[List[FurniturePiece], List[FurniturePiece]]:
        self.reset()
        w1 = [p for p in items if p.pin_cells and p.support_cells and getattr(p, "kind", "") != "hanging" and len(p.support_cells) >= len(p.pin_cells)]
        w2 = [p for p in items if p.pin_cells and p.support_cells and getattr(p, "kind", "") != "hanging" and len(p.support_cells) < len(p.pin_cells)]
        w3 = [p for p in items if not p.pin_cells and p.support_cells]
        w4 = [p for p in items if getattr(p, "kind", "") == "hanging"]
        w5 = [p for p in items if p.pin_cells and not p.support_cells and getattr(p, "kind", "") != "hanging" and len(p.pin_cells) >= 2]
        w6 = [p for p in items if p.pin_cells and not p.support_cells and getattr(p, "kind", "") != "hanging" and len(p.pin_cells) == 1]
        w7 = [p for p in items if not p.pin_cells and not p.support_cells]

        if mode == "footprint":
            w1.sort(key=lambda p: (-len(p.pin_cells), -len(p.support_cells), p.height, p.uid))
            w2.sort(key=lambda p: (-len(p.support_cells), -len(p.pin_cells), p.height, p.uid))
            w3.sort(key=lambda p: (-len(p.support_cells), -p.width, p.uid))
            w4.sort(key=lambda p: (-len(p.support_cells), -p.width, -p.height, p.uid))
            w5.sort(key=lambda p: (-(1 if p.special_totem else 0), -len(p.pin_cells), -p.height, p.uid))
            w6.sort(key=lambda p: (-(1 if p.special_totem else 0), -p.height, p.uid))
            w7.sort(key=lambda p: (-len(p.headroom_cells), -p.width, p.uid))
        else:
            # Value-first sorting ensures ★Rare / high-stat items win prime floor & shelf slots!
            w1.sort(key=lambda p: (-len(p.support_cells), -_piece_role_density(p, role), p.height, p.uid))
            w2.sort(key=lambda p: (-_piece_role_density(p, role), -len(p.support_cells), p.height, p.uid))
            w3.sort(key=lambda p: (-len(p.support_cells), -_piece_role_density(p, role), p.uid))
            w4.sort(key=lambda p: (-_piece_role_density(p, role), -p.width, p.uid))
            w5.sort(key=lambda p: (-(1 if p.special_totem else 0), -_piece_role_density(p, role), -len(p.pin_cells), p.uid))
            w6.sort(key=lambda p: (-(1 if p.special_totem else 0), -_piece_role_density(p, role), -p.height, p.uid))
            w7.sort(key=lambda p: (-_piece_role_density(p, role), -len(p.headroom_cells), p.uid))

        placed, leftover = [], []
        for wave, pref_hi in ((w1, False), (w2, False), (w3, False), (w4, False), (w5, True), (w6, True), (w7, True)):
            for p in wave:
                sp = self.find_spot(p, prefer_high=pref_hi)
                if sp is not None:
                    self.place(p, sp[0], sp[1], sp[2], sp[3])
                    placed.append(p)
                else:
                    leftover.append(p)
        return placed, leftover

    def _toposort_placements(self) -> None:
        uid_map = {inf["piece"].uid: inf for inf in self.placements}
        ordered, visited = [], set()

        def _visit(inf: Dict[str, Any]):
            uid = inf["piece"].uid
            if uid in visited:
                return
            for dep in sorted(inf["deps"]):
                if dep in uid_map and dep not in visited:
                    _visit(uid_map[dep])
            visited.add(uid)
            ordered.append(inf)

        for inf in sorted(self.placements, key=lambda i: (1 if not i["piece"].pin_cells else 0, i["y0"], i["x0"])):
            _visit(inf)

        for idx, inf in enumerate(ordered, 1):
            inf["order_num"] = idx
        for inf in ordered:
            if inf["deps"]:
                p_uid = next(iter(inf["deps"]))
                if p_uid in uid_map:
                    p_inf = uid_map[p_uid]
                    fl_s = " ⇄Flip" if inf.get("is_flipped") else ""
                    inf["rests_on_label"] = f"On #{p_inf['order_num']:02d} {p_inf['piece'].name}{fl_s}"
        self.placements = ordered

    def pack_items(
        self, items: List[FurniturePiece], role: str = "breeding", try_alt_if_leftover: bool = True
    ) -> Tuple[List[FurniturePiece], List[FurniturePiece]]:
        for p in items:
            if not p.solid_cells and not p.headroom_cells:
                _attach_notalim_meta(p)

        placed, leftover = self._pack_single_strategy(items, role=role, mode="value")
        if leftover and try_alt_if_leftover:
            val_placements = list(self.placements)
            val_placed, val_leftover = list(placed), list(leftover)
            fp_placed, fp_leftover = self._pack_single_strategy(items, role=role, mode="footprint")
            if len(fp_placed) > len(val_placed):
                placed, leftover = fp_placed, fp_leftover
            else:
                # Re-run value strategy cleanly so internal occupancy grids match placements
                placed, leftover = self._pack_single_strategy(items, role=role, mode="value")
                if len(placed) < len(val_placed):
                    self.placements = val_placements
                    placed, leftover = val_placed, val_leftover

        self._toposort_placements()
        return placed, leftover


def _build_room_specs(demand: HouseDemandProfile) -> List[RoomSpec]:
    """Builds progression-adaptive RoomSpecs for 1..5 unlocked rooms."""
    n = max(1, min(5, demand.unlocked_rooms))
    attic_id = demand.prefer_attic_size
    if attic_id not in NOTALIM_HOUSE.get("rooms", {}):
        attic_id = "SmallAttic" if n <= 2 else "LargeAttic"
    attic_t = int(NOTALIM_HOUSE["rooms"][attic_id].get("free", 136))

    role_meta = {
        "breeding": ("Breeding Chapel", "🏠", "Breed"),
        "barracks": ("Chastity Barracks & Ward", "🛡️", "Barracks"),
        "fight_club": ("Chaos Fight Pit & Jack Farm", "⚔️", "Fight Pit"),
        "mutation": ("Patch 1.1 >10 Mut Lab", "🧬", "Mut Lab"),
        "secondary_breed": ("Secondary Outcross Suite", "✨", "Outcross"),
        "appeal_overflow": ("Appeal & Food Vault", "🏆", "Appeal"),
    }
    room_geoms = [
        (1, attic_id, attic_t, 31, 28, 0, 8),
        (2, "Floor2_Large", 112, 16, 22, 16, 7),
        (3, "Floor1_Small", 112, 16, 22, 16, 7),
        (4, "Floor1_Large", 112, 16, 22, 16, 7),
        (5, "Floor2_Small", 112, 16, 22, 16, 7),
    ]

    rooms: List[RoomSpec] = []
    for idx in range(n):
        rid, r_internal, tiles, fs, ws, cs, sh = room_geoms[idx]
        role = demand.room_roles[idx] if idx < len(demand.room_roles) else "appeal_overflow"
        title, icon, short_role = role_meta.get(role, ("Utility Room", "📦", "Room"))
        spec = RoomSpec(
            room_id=rid,
            internal_room_name=r_internal,
            name=f"Room {rid}: {r_internal} ({tiles} Tiles — {title})",
            short_tab=f"{icon} R{rid}: {short_role}",
            role=role,
            floor_sockets=fs,
            wall_sockets=ws,
            ceiling_sockets=cs,
            max_stack_height=sh,
        )
        spec.packer = RoomGridPacker(r_internal, NOTALIM_HOUSE)
        rooms.append(spec)
    return rooms


def _item_allowed_in_room(item: FurniturePiece, room: RoomSpec) -> bool:
    if room.room_id == 1 and getattr(item, "kind", "") == "hanging":
        return False
    if room.role == "breeding" and (item.mutation > 0 or item.special_totem in ("chastity", "chaos")):
        return False
    if room.role == "barracks" and item.special_totem == "chaos":
        return False
    if room.role == "fight_club" and (item.comfort > 0 or item.special_totem == "chastity"):
        return False
    if room.role == "mutation" and item.special_totem == "chastity":
        return False
    if room.role == "secondary_breed" and (item.mutation > 0 or item.special_totem in ("chastity", "chaos")):
        return False
    return True


def solve_house_closed_loop(
    inventory: List[FurniturePiece],
    demand: HouseDemandProfile,
    sa_iterations: int = 560,
) -> Tuple[List[RoomSpec], List[FurniturePiece], str]:
    """
    Deterministic Multi-Move 2D Spatial House Solver:
      Phase 1: Role-aware greedy construction (totems & shelf-providers first).
      Phase 2: Multi-move Simulated Annealing (Relocate + Room↔Room Swap + Storage↔Room Swap).
      Phase 3: Storage rescue pass + final multi-heuristic packing tightening.
    """
    for p in inventory:
        _attach_notalim_meta(p)

    rooms = _build_room_specs(demand)

    def _repack(r: RoomSpec, cand: List[FurniturePiece], fast: bool = True) -> Tuple[List[FurniturePiece], List[FurniturePiece]]:
        pl, left = r.packer.pack_items(cand, role=r.role, try_alt_if_leftover=not fast)
        r.placed = pl
        r.placements = list(r.packer.placements)
        return pl, left

    # 100% deterministic initial ordering (independent of current_room or SQLite row order!)
    sorted_inv = sorted(
        inventory,
        key=lambda p: (
            -(1 if p.special_totem and p.special_totem != "food" else 0),
            -(1 if p.support_cells else 0),
            -len(p.support_cells),
            -(1 if p.is_rare else 0),
            -(abs(p.stim) * 2 + abs(p.comfort) + abs(p.health) + abs(p.mutation) * 2 + abs(p.appeal)),
            p.item_id.lower(),
            p.uid,
        ),
    )

    # Phase 1: Greedy constructive placement
    storage: List[FurniturePiece] = []
    for item in sorted_inv:
        best_r: Optional[RoomSpec] = None
        best_gain = -0.1
        base_house_sc = score_house_state(rooms, demand)
        for r in rooms:
            if not _item_allowed_in_room(item, r):
                continue
            old_pl = list(r.placed)
            pl_after, left_after = _repack(r, old_pl + [item], fast=True)
            if item in pl_after and not left_after:
                gain = (score_house_state(rooms, demand) - base_house_sc) + (len(item.support_cells) * 1.4)
                if gain > best_gain:
                    best_gain = gain
                    best_r = r
            _repack(r, old_pl, fast=True)

        if best_r is not None:
            _repack(best_r, best_r.placed + [item], fast=True)
        else:
            storage.append(item)

    # Phase 2: Deterministic Multi-Move Simulated Annealing (Relocate + Room↔Room Swap + Storage↔Room Swap)
    rng = random.Random(1337)
    locked_totems = {"chastity", "chaos", "evolution", "stim"}
    temp = 32.0

    for _ in range(sa_iterations):
        temp *= 0.994
        move_roll = rng.random()

        # Move A: Storage ↔ Room Swap or Insert (when storage has items)
        if storage and move_roll < 0.22:
            st_item = rng.choice(storage)
            r_t = rng.choice(rooms)
            if not _item_allowed_in_room(st_item, r_t):
                continue
            old_t = list(r_t.placed)
            old_tot = score_house_state(rooms, demand)

            # Try pure insert first
            pl_ins, left_ins = _repack(r_t, old_t + [st_item], fast=True)
            if st_item in pl_ins and not left_ins:
                delta = score_house_state(rooms, demand) - old_tot
                if delta > 0 or rng.random() < math.exp(max(-20.0, delta / max(0.1, temp))):
                    storage.remove(st_item)
                    continue
                _repack(r_t, old_t, fast=True)

            # Otherwise try evicting one non-locked piece from r_t in exchange for st_item
            evict_cands = [p for p in old_t if p.special_totem not in locked_totems]
            if not evict_cands:
                continue
            ev_item = rng.choice(evict_cands)
            pl_sw, left_sw = _repack(r_t, [p for p in old_t if p.uid != ev_item.uid] + [st_item], fast=True)
            if st_item in pl_sw and not left_sw:
                delta = score_house_state(rooms, demand) - old_tot
                if delta > 0 or rng.random() < math.exp(max(-20.0, delta / max(0.1, temp))):
                    storage.remove(st_item)
                    storage.append(ev_item)
                    continue
            _repack(r_t, old_t, fast=True)
            continue

        if len(rooms) < 2:
            continue

        # Move B: Room ↔ Room Swap (breaks local optima when rooms are full!)
        if move_roll < 0.60:
            r_a, r_b = rng.sample(rooms, 2)
            cands_a = [p for p in r_a.placed if p.special_totem not in locked_totems]
            cands_b = [p for p in r_b.placed if p.special_totem not in locked_totems]
            if not cands_a or not cands_b:
                continue
            it_a = rng.choice(cands_a)
            it_b = rng.choice(cands_b)
            if not _item_allowed_in_room(it_a, r_b) or not _item_allowed_in_room(it_b, r_a):
                continue

            old_a, old_b = list(r_a.placed), list(r_b.placed)
            old_tot = score_house_state(rooms, demand)
            pl_a, left_a = _repack(r_a, [p for p in old_a if p.uid != it_a.uid] + [it_b], fast=True)
            pl_b, left_b = _repack(r_b, [p for p in old_b if p.uid != it_b.uid] + [it_a], fast=True)
            if it_b in pl_a and it_a in pl_b and not left_a and not left_b:
                delta = score_house_state(rooms, demand) - old_tot
                if delta > 0 or rng.random() < math.exp(max(-20.0, delta / max(0.1, temp))):
                    continue
            _repack(r_a, old_a, fast=True)
            _repack(r_b, old_b, fast=True)
            continue

        # Move C: Single-Item Relocate (Room A -> Room B)
        r_a, r_b = rng.sample(rooms, 2)
        cands_a = [p for p in r_a.placed if p.special_totem not in locked_totems]
        if not cands_a:
            continue
        it_a = rng.choice(cands_a)
        if not _item_allowed_in_room(it_a, r_b):
            continue

        old_a, old_b = list(r_a.placed), list(r_b.placed)
        old_tot = score_house_state(rooms, demand)
        _, left_a = _repack(r_a, [p for p in old_a if p.uid != it_a.uid], fast=True)
        pl_b, left_b = _repack(r_b, old_b + [it_a], fast=True)
        if it_a in pl_b and not left_a and not left_b:
            delta = score_house_state(rooms, demand) - old_tot
            if delta > 0 or rng.random() < math.exp(max(-20.0, delta / max(0.1, temp))):
                continue
        _repack(r_a, old_a, fast=True)
        _repack(r_b, old_b, fast=True)

    # Phase 3: Final rescue pass (with full dual-strategy packing) for any remaining storage pieces
    rem_storage: List[FurniturePiece] = []
    for item in storage:
        best_r = None
        best_gain = -1.0
        old_sc = score_house_state(rooms, demand)
        for r in rooms:
            if not _item_allowed_in_room(item, r):
                continue
            old_pl = list(r.placed)
            pl_after, left_after = _repack(r, old_pl + [item], fast=False)
            if item in pl_after and not left_after:
                gain = score_house_state(rooms, demand) - old_sc
                if gain > best_gain:
                    best_gain = gain
                    best_r = r
            _repack(r, old_pl, fast=False)
        if best_r is not None:
            _repack(best_r, best_r.placed + [item], fast=False)
        else:
            rem_storage.append(item)

    # Final clean topological repack on each room
    for r in rooms:
        _repack(r, list(r.placed), fast=False)

    rare_cnt = sum(1 for p in inventory if p.is_rare)
    placed_cnt = sum(len(r.placed) for r in rooms)
    tot_app = sum(r.totals["Appeal"] for r in rooms)
    breed_r = rooms[0]
    ac_ok = all(
        (r.has_chastity or r.totals["Comfort"] <= -10 or r.autocattery_breed_sum < breed_r.autocattery_breed_sum)
        for r in rooms[1:]
    )
    ac_tag = "AutoCattery Lock: ✔" if ac_ok else "AutoCattery Lock: ⚠ Check R1"
    app_tag = "2nd Spell + Passive Strays!" if tot_app >= 200 else ("2nd Spell Strays!" if tot_app >= 100 else "Next Milestone: 100")

    strat = (
        f"🔒 [{demand.stage}] {placed_cnt}/{len(inventory)} Packed ({rare_cnt} ★Rare) | "
        f"R1 Stim: {breed_r.totals['Stimulation']} | House Appeal: {tot_app} ({app_tag}) | {ac_tag}"
    )
    return rooms, rem_storage, strat


# =====================================================================
# 6. STUDIO ARCHITECT UI (v10.0 - BLUEPRINT + BREEDING PLAN TABS)
# =====================================================================

class FurnitureArchitectUI:
    PIECE_PALETTE = [
        ("#d98a6c", "#4a2518", "#f0b8a2"),
        ("#7aa689", "#1e3b28", "#b2d4be"),
        ("#7395b8", "#1d3247", "#adc7e0"),
        ("#c99e5a", "#45300e", "#e8ca95"),
        ("#a682a8", "#3b213d", "#d4b8d6"),
        ("#63a3a6", "#163c3e", "#9fd0d2"),
        ("#c77b8b", "#471c26", "#e6b3be"),
        ("#8fa868", "#2d3d14", "#bfd49e"),
        ("#7e88b8", "#222847", "#b5bce0"),
        ("#ba8765", "#422714", "#deb99f"),
        ("#6bab92", "#173d2e", "#a5d6c3"),
        ("#b8849e", "#401f30", "#dbb4c8"),
        ("#769eb0", "#1b3642", "#accad6"),
        ("#b59c6b", "#3d3117", "#dbcaa4"),
        ("#cf8c72", "#4a2415", "#edbcae"),
        ("#87997d", "#293622", "#b9c7b1"),
    ]

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mewgenics Closed-Loop Breeding & Furniture Architect (v10.0)")
        self.root.geometry("1380x880")
        self.root.configure(bg="#2b303c")

        self.last_mtime = 0.0
        self.only_show_moves = False
        self.room_override_var = tk.StringVar(value="Auto")
        self.selected_tab_idx = 0   # 0..len(rooms)-1 = room blueprint, len(rooms) = Breeding & Roster Plan
        self.selected_info: Optional[Dict[str, Any]] = None
        self.hovered_info: Optional[Dict[str, Any]] = None
        self.rare_overrides: Set[str] = load_rare_overrides()

        self.locked_collection_sig: Optional[Tuple[Any, ...]] = None
        self.locked_item_multiset: Optional[Tuple[str, ...]] = None

        self.current_rooms: List[RoomSpec] = []
        self.current_storage: List[FurniturePiece] = []
        self.current_inventory: List[FurniturePiece] = []
        self.current_cats: List[CatData] = []
        self.current_room_count: int = 4
        self.current_sav: Optional[Path] = None
        self.current_plan: Optional[BreedingPlan] = None
        self.top_4: List[CatData] = []
        self.synced_cnt: int = 0
        self.strat_name: str = ""
        self.cell_hit_map: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self.last_grid_params: Tuple[int, int, int, int, int] = (0, 0, 32, 0, 0)

        self._build_ui()
        self._poll_save()

    @staticmethod
    def _canonicalize_inventory(furniture: List[FurniturePiece], rare_overrides: Set[str]) -> List[FurniturePiece]:
        for p in furniture:
            _attach_notalim_meta(p)

        grouped: Dict[str, List[FurniturePiece]] = {}
        for p in furniture:
            grouped.setdefault(p.item_id.lower(), []).append(p)

        canonical_list: List[FurniturePiece] = []
        for fid in sorted(grouped.keys()):
            copies = grouped[fid]
            copies.sort(key=lambda x: (not x.is_rare, x.current_room, x.uid))
            for copy_idx, p in enumerate(copies, 1):
                canon_uid = f"canon_{fid}_{copy_idx}"
                if canon_uid in rare_overrides or p.uid in rare_overrides:
                    if getattr(p, "can_rare", True):
                        p.is_rare = True
                p.uid = canon_uid
                canonical_list.append(p)
        return canonical_list

    @staticmethod
    def _compute_collection_sig(room_count: int, furniture: List[FurniturePiece], demand: HouseDemandProfile) -> Tuple[Any, ...]:
        items_sig = tuple(sorted((p.item_id.lower(), bool(p.is_rare)) for p in furniture))
        return (room_count, demand.stage, tuple(demand.room_roles), demand.has_beneficial_disorder_breeder, items_sig)

    def _sync_live_room_locations_without_resolving(self, fresh_furniture: List[FurniturePiece]) -> None:
        pool_by_key: Dict[Tuple[str, bool], List[Tuple[int, str]]] = {}
        for fp in fresh_furniture:
            key = (fp.item_id.lower(), bool(fp.is_rare))
            pool_by_key.setdefault(key, []).append((fp.current_room, fp.current_room_label))

        for r in self.current_rooms:
            for p in r.placed:
                key = (p.item_id.lower(), bool(p.is_rare))
                locs = pool_by_key.get(key, [])
                if (r.room_id, r.internal_room_name) in locs:
                    locs.remove((r.room_id, r.internal_room_name))
                    p.current_room = r.room_id
                    p.current_room_label = r.internal_room_name
                else:
                    match = next((loc for loc in locs if loc[0] == r.room_id), None)
                    if match:
                        locs.remove(match)
                        p.current_room, p.current_room_label = match

        for r in self.current_rooms:
            for p in r.placed:
                key = (p.item_id.lower(), bool(p.is_rare))
                locs = pool_by_key.get(key, [])
                if locs and p.current_room != r.room_id:
                    p.current_room, p.current_room_label = locs.pop(0)

        for p in self.current_storage:
            key = (p.item_id.lower(), bool(p.is_rare))
            locs = pool_by_key.get(key, [])
            if locs:
                p.current_room, p.current_room_label = locs.pop(0)

    def _effective_room_count(self, detected: int) -> int:
        val = self.room_override_var.get()
        if val.isdigit():
            return max(1, min(5, int(val)))
        return max(1, min(5, detected))

    def _run_closed_loop_solve(self, room_count: int, furniture: List[FurniturePiece]) -> None:
        """
        True 2-pass Closed-Loop Synergy:
          Pass 1: Breeding optimizer analyzes live cats + furniture -> HouseDemandProfile.
          Pass 2: 2D spatial furniture solver solves rooms using live DemandProfile.
          Pass 3: Re-scores breeding pairs with actual solved Room 1 Stimulation & syncs protection.json.
        """
        opt1 = AdaptiveOptimizer(self.current_cats, room_count, furniture)
        res1 = opt1.solve()
        demand: HouseDemandProfile = res1["demand"]

        rooms, storage, strat = solve_house_closed_loop(furniture, demand)
        solved_stim = rooms[0].totals["Stimulation"] if rooms else 0

        opt2 = AdaptiveOptimizer(self.current_cats, room_count, furniture, solved_stim=solved_stim)
        res2 = opt2.solve()
        self.current_plan = res2["plan"]
        self.top_4, self.synced_cnt = sync_autocattery_config(res2)

        self.current_rooms = rooms
        self.current_storage = storage
        self.strat_name = strat
        self.locked_collection_sig = self._compute_collection_sig(room_count, furniture, demand)

    def _build_ui(self):
        top_bar = tk.Frame(self.root, bg="#232731", pady=7)
        top_bar.pack(fill="x", padx=10)

        sign_frame = tk.Frame(top_bar, bg="#d99b52", bd=2, relief="flat", padx=2, pady=2)
        sign_frame.pack(side="left", padx=4)
        inner_paper = tk.Frame(sign_frame, bg="#1b1e26", padx=12, pady=3)
        inner_paper.pack()
        tk.Label(
            inner_paper,
            text="🐾 MEWGENICS CLOSED-LOOP ARCHITECT (v10.0 — BREEDING × FURNITURE)",
            bg="#1b1e26", fg="#f5e6c8", font=("Segoe UI", 11, "bold"),
        ).pack()

        btn_style = {"font": ("Segoe UI", 9, "bold"), "bd": 0, "relief": "flat", "cursor": "hand2", "padx": 10, "pady": 5}

        tk.Button(
            top_bar, text="🌐 Sync Notalim DB", command=self.sync_notalim_action,
            bg="#4d908e", fg="#ffffff", activebackground="#5aa6a4", **btn_style,
        ).pack(side="right", padx=3)

        tk.Button(
            top_bar, text="★ Rare (2x)...", command=self.open_rare_manager_dialog,
            bg="#d99b52", fg="#1a1819", activebackground="#ebb06b", **btn_style,
        ).pack(side="right", padx=3)

        self.filter_btn = tk.Button(
            top_bar, text="🎯 Moves Only: OFF", command=self.toggle_move_filter,
            bg="#3b4252", fg="#eceff4", activebackground="#4c566a", **btn_style,
        )
        self.filter_btn.pack(side="right", padx=3)

        tk.Button(
            top_bar, text="🔄 Force Re-Solve", command=self.force_reoptimize,
            bg="#689d6a", fg="#ffffff", activebackground="#7ec180", **btn_style,
        ).pack(side="right", padx=3)

        # Rooms Override Selector (Auto / 1..5)
        rm_frame = tk.Frame(top_bar, bg="#232731")
        rm_frame.pack(side="right", padx=6)
        tk.Label(rm_frame, text="Rooms:", bg="#232731", fg="#d8dee9", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 3))
        rm_box = ttk.Combobox(rm_frame, textvariable=self.room_override_var, values=("Auto", "1", "2", "3", "4", "5"), width=5, state="readonly")
        rm_box.pack(side="left")
        rm_box.bind("<<ComboboxSelected>>", lambda _e: self.force_reoptimize())

        status_card = tk.Frame(self.root, bg="#232731", highlightbackground="#3b4252", highlightthickness=1)
        status_card.pack(fill="x", padx=10, pady=3)

        self.retired_lbl = tk.Label(
            status_card, text="🛡️ AutoCattery v0.5.35 Protection Sync (`config/protection.json`): Scanning save...",
            bg="#232731", fg="#a3be8c", font=("Segoe UI", 9, "bold"), anchor="w",
        )
        self.retired_lbl.pack(fill="x", padx=10, pady=(3, 1))

        self.strat_lbl = tk.Label(
            status_card, text="🗿 Loading Notalim furniture.json & Patch 1.1+ breeding engine...",
            bg="#232731", fg="#d8dee9", font=("Segoe UI", 9), anchor="w",
        )
        self.strat_lbl.pack(fill="x", padx=10, pady=(1, 3))

        self.tab_bar = tk.Frame(self.root, bg="#2b303c", pady=4)
        self.tab_bar.pack(fill="x", padx=10)
        self.tab_buttons: List[tk.Button] = []

        self.main_pane = tk.Frame(self.root, bg="#2b303c")
        self.main_pane.pack(fill="both", expand=True, padx=10, pady=2)

        # Blueprint View (Rooms 1..N)
        self.blueprint_frame = tk.Frame(self.main_pane, bg="#2b303c")
        canvas_border = tk.Frame(self.blueprint_frame, bg="#3b4252", bd=2, relief="flat")
        canvas_border.pack(fill="both", expand=True, pady=(0, 6))

        self.canvas = tk.Canvas(canvas_border, bg="#1e222a", height=465, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._draw_blueprint_room())
        self.canvas.bind("<Motion>", self._on_canvas_hover)
        self.canvas.bind("<Leave>", self._on_canvas_leave)
        self.canvas.bind("<Button-1>", self._on_canvas_left_click)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)

        bottom_frame = tk.Frame(self.blueprint_frame, bg="#232731", highlightbackground="#3b4252", highlightthickness=1)
        bottom_frame.pack(fill="x")

        self.inspect_lbl = tk.Label(
            bottom_frame,
            text="💡 Hover/Click any piece to inspect contour & support shelf (Cyan = Parent)  |  Right-Click any piece to toggle ★ RARE (2x)",
            bg="#1b1e26", fg="#ebcb8b", font=("Segoe UI", 9, "bold"), anchor="w", padx=10, pady=5,
        )
        self.inspect_lbl.pack(fill="x")

        list_container = tk.Frame(bottom_frame, bg="#232731")
        list_container.pack(fill="x")

        self.text = tk.Text(
            list_container, bg="#1e222a", fg="#e5e9f0",
            font=("Consolas", 10), height=9, wrap="none", bd=0, padx=10, pady=6,
        )
        scroll = ttk.Scrollbar(list_container, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        # Breeding & Roster Plan View (Dedicated Full-Height Tab)
        self.breeding_frame = tk.Frame(self.main_pane, bg="#232731", highlightbackground="#3b4252", highlightthickness=1)
        self.breeding_text = tk.Text(
            self.breeding_frame, bg="#1e222a", fg="#e5e9f0",
            font=("Consolas", 10), wrap="word", bd=0, padx=14, pady=10,
        )
        b_scroll = ttk.Scrollbar(self.breeding_frame, command=self.breeding_text.yview)
        self.breeding_text.configure(yscrollcommand=b_scroll.set)
        b_scroll.pack(side="right", fill="y")
        self.breeding_text.pack(side="left", fill="both", expand=True)

        self.blueprint_frame.pack(fill="both", expand=True)

    def sync_notalim_action(self):
        global NOTALIM_CATALOG, NOTALIM_HOUSE
        self.strat_lbl.config(text="🌐 Downloading furniture.json & house.json from notalim/mewgenics-house-planner...")
        self.root.update()
        NOTALIM_CATALOG, NOTALIM_HOUSE = load_notalim_databases(force_network=True)
        self.force_reoptimize()
        messagebox.showinfo("Notalim Sync Complete", f"Loaded {len(NOTALIM_CATALOG)} furniture definitions from notalim/mewgenics-house-planner!")

    def open_rare_manager_dialog(self):
        if not self.current_inventory:
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("★ Manage Owned Furniture & Mark Rare (2x) Pieces")
        dlg.geometry("780x580")
        dlg.configure(bg="#2b303c")
        dlg.transient(self.root)
        dlg.grab_set()

        search_bar = tk.Frame(dlg, bg="#232731", bd=1, relief="flat", padx=8, pady=6)
        search_bar.pack(fill="x", padx=12, pady=8)
        tk.Label(search_bar, text="🔍 Search:", bg="#232731", fg="#eceff4", font=("Segoe UI", 9, "bold")).pack(side="left")
        s_var = tk.StringVar()
        tk.Entry(search_bar, textvariable=s_var, width=30, bg="#1e222a", fg="#eceff4", insertbackground="white", font=("Segoe UI", 10)).pack(side="left", padx=6)

        list_frame = tk.Frame(dlg, bg="#1e222a", bd=1, relief="sunken")
        list_frame.pack(fill="both", expand=True, padx=12, pady=4)
        cv = tk.Canvas(list_frame, bg="#1e222a", highlightthickness=0)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=cv.yview)
        inner = tk.Frame(cv, bg="#1e222a")
        inner.bind("<Configure>", lambda _e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)

        recs = []
        for idx, p in enumerate(sorted(self.current_inventory, key=lambda x: (x.name.lower(), x.uid))):
            rf = tk.Frame(inner, bg="#252a34" if idx % 2 == 0 else "#1e222a", pady=2)
            rv = tk.BooleanVar(value=p.is_rare)
            can_r = getattr(p, "can_rare", True)
            tk.Checkbutton(
                rf, text="★ RARE (2x)" if can_r else "Fixed (1x)", variable=rv,
                state="normal" if can_r else "disabled", bg=rf["bg"], fg="#ebcb8b", selectcolor="#1e222a", font=("Segoe UI", 9, "bold"),
            ).pack(side="left", padx=4)
            tk.Label(
                rf, text=f"{p.name:<28} [{p.width}×{p.height} | {len(p.solid_cells)}■ {len(p.support_cells)}● {len(p.pin_cells)}+]  ({p.current_room_label})",
                bg=rf["bg"], fg="#d8dee9", font=("Consolas", 9),
            ).pack(side="left", padx=4)
            recs.append((p, rv, rf))

        def _filt(*_a):
            q = s_var.get().strip().lower()
            for p, _, rf in recs:
                if not q or q in p.name.lower() or q in p.item_id.lower() or q in p.current_room_label.lower():
                    rf.pack(fill="x", padx=4)
                else:
                    rf.pack_forget()

        s_var.trace_add("write", _filt)
        _filt()

        def _save():
            for p, rv, _ in recs:
                p.is_rare = bool(rv.get() and getattr(p, "can_rare", True))
                if p.is_rare:
                    self.rare_overrides.add(p.uid)
                else:
                    self.rare_overrides.discard(p.uid)
            save_rare_overrides(self.rare_overrides)
            self._run_closed_loop_solve(self.current_room_count, self.current_inventory)
            self._rebuild_room_tabs()
            self._render_current()
            dlg.destroy()

        tk.Button(
            dlg, text="✔ Save Rare (2x) Selection & Re-Solve", command=_save,
            bg="#689d6a", fg="#ffffff", font=("Segoe UI", 10, "bold"), bd=0, padx=16, pady=6, cursor="hand2",
        ).pack(pady=8)

    def _rebuild_room_tabs(self):
        for b in self.tab_buttons:
            b.destroy()
        self.tab_buttons.clear()

        for idx, r in enumerate(self.current_rooms):
            is_sel = idx == self.selected_tab_idx
            btn = tk.Button(
                self.tab_bar, text=r.short_tab, command=lambda i=idx: self.select_tab(i),
                bg="#d99b52" if is_sel else "#232731", fg="#1a1819" if is_sel else "#d8dee9",
                font=("Segoe UI", 9, "bold"), bd=0, padx=13, pady=5, cursor="hand2",
            )
            btn.pack(side="left", padx=3)
            self.tab_buttons.append(btn)

        breed_idx = len(self.current_rooms)
        is_breed = self.selected_tab_idx == breed_idx
        b_btn = tk.Button(
            self.tab_bar, text="🧬 Breeding & Roster Plan", command=lambda i=breed_idx: self.select_tab(i),
            bg="#a3be8c" if is_breed else "#232731", fg="#1a1819" if is_breed else "#a3be8c",
            font=("Segoe UI", 9, "bold"), bd=0, padx=14, pady=5, cursor="hand2",
        )
        b_btn.pack(side="left", padx=(10, 3))
        self.tab_buttons.append(b_btn)

    def select_tab(self, idx: int):
        self.selected_tab_idx = idx
        self.selected_info = None
        self.hovered_info = None
        self._rebuild_room_tabs()
        self._render_current()

    def toggle_move_filter(self):
        self.only_show_moves = not self.only_show_moves
        self.filter_btn.config(text=f"🎯 Moves Only: {'ON' if self.only_show_moves else 'OFF'}")
        self._render_current()

    def _set_inspector_info(self, inf: Dict[str, Any]):
        p = inf["piece"]
        r_str = "★ RARE (2x Stats)" if p.is_rare else "Normal (1x)"
        self.inspect_lbl.config(
            text=f"🔍 #{inf['order_num']:02d} {p.name} [{r_str}]  |  {inf['rests_on_label']}  |  "
            f"Footprint: {len(p.solid_cells)}■ Solid, {len(p.support_cells)}● Shelf Bolts, {len(p.pin_cells)}+ Pins, {len(p.headroom_cells)}□ Headroom  |  "
            f"A:{p.appeal:+d} C:{p.comfort:+d} S:{p.stim:+d} H:{p.health:+d} M:{p.mutation:+d}"
        )

    def _info_at_xy(self, ex: int, ey: int) -> Optional[Dict[str, Any]]:
        ox, oy, tile_px, gw, gh = self.last_grid_params
        if tile_px <= 0:
            return None
        gx = (ex - ox) // tile_px
        gy = gh - 1 - ((ey - oy) // tile_px)
        return self.cell_hit_map.get((gx, gy))

    def _on_canvas_hover(self, event):
        inf = self._info_at_xy(event.x, event.y)
        if inf is not self.hovered_info:
            self.hovered_info = inf
            active = inf or self.selected_info
            if active is not None:
                self._set_inspector_info(active)
            self._draw_blueprint_room()

    def _on_canvas_leave(self, _event):
        if self.hovered_info is not None:
            self.hovered_info = None
            if self.selected_info is not None:
                self._set_inspector_info(self.selected_info)
            self._draw_blueprint_room()

    def _on_canvas_left_click(self, event):
        inf = self._info_at_xy(event.x, event.y)
        self.selected_info = inf
        if inf is not None:
            self._set_inspector_info(inf)
        self._draw_blueprint_room()

    def _on_canvas_right_click(self, event):
        inf = self._info_at_xy(event.x, event.y)
        if inf is not None:
            p = inf["piece"]
            if not getattr(p, "can_rare", True):
                return
            p.is_rare = not p.is_rare
            if p.is_rare:
                self.rare_overrides.add(p.uid)
            else:
                self.rare_overrides.discard(p.uid)
            save_rare_overrides(self.rare_overrides)
            self._run_closed_loop_solve(self.current_room_count, self.current_inventory)
            self._rebuild_room_tabs()
            self._render_current()

    def force_reoptimize(self):
        self.locked_collection_sig = None
        self.locked_item_multiset = None
        self.last_mtime = 0.0
        self._poll_save(run_once=True)

    def _poll_save(self, run_once: bool = False):
        sav_path = find_latest_save()
        if sav_path and sav_path.exists():
            mtime = sav_path.stat().st_mtime
            if mtime != self.last_mtime:
                self.last_mtime = mtime
                try:
                    cats, raw_furniture, detected_rooms = load_save_cats_and_furniture(sav_path)
                    room_count = self._effective_room_count(detected_rooms)
                    self.current_cats = cats
                    self.current_sav = sav_path

                    furniture = self._canonicalize_inventory(raw_furniture, self.rare_overrides)
                    new_item_multiset = tuple(sorted(p.item_id.lower() for p in furniture))

                    # If owned furniture & unlocked rooms haven't changed, keep the locked 2D blueprint
                    # stable while still refreshing live breeding recommendations & protection sync!
                    if (
                        self.locked_item_multiset is not None
                        and new_item_multiset == self.locked_item_multiset
                        and self.current_rooms
                        and room_count == self.current_room_count
                        and self.locked_collection_sig is not None
                    ):
                        self._sync_live_room_locations_without_resolving(furniture)
                        solved_stim = self.current_rooms[0].totals["Stimulation"] if self.current_rooms else 0
                        res = AdaptiveOptimizer(cats, room_count, self.current_inventory, solved_stim=solved_stim).solve()
                        self.current_plan = res["plan"]
                        self.top_4, self.synced_cnt = sync_autocattery_config(res)
                        self._render_current()
                    else:
                        self.locked_item_multiset = new_item_multiset
                        self.current_inventory = furniture
                        self.current_room_count = room_count
                        self._run_closed_loop_solve(room_count, furniture)
                        if self.selected_tab_idx > len(self.current_rooms):
                            self.selected_tab_idx = 0
                        self._rebuild_room_tabs()
                        self._render_current()
                except Exception as e:
                    self.retired_lbl.config(text=f"Transient save read (retrying): {e}")
        if not run_once:
            self.root.after(2500, self._poll_save)

    def _draw_blueprint_room(self):
        c = self.canvas
        c.delete("all")
        self.cell_hit_map.clear()
        if not self.current_rooms or self.selected_tab_idx >= len(self.current_rooms):
            return
        room = self.current_rooms[self.selected_tab_idx]
        packer: RoomGridPacker = room.packer
        gw, gh = packer.w, packer.h

        cw, ch = max(980, c.winfo_width()), max(440, c.winfo_height())
        tile_px = max(24, min(50, (cw - 175) // gw, (ch - 76) // gh))
        grid_px_w, grid_px_h = gw * tile_px, gh * tile_px
        ox, oy = max(38, (cw - grid_px_w) // 2 - 30), max(36, (ch - grid_px_h) // 2 + 4)
        self.last_grid_params = (ox, oy, tile_px, gw, gh)

        active_inf = self.hovered_info or self.selected_info
        active_uid = active_inf["piece"].uid if active_inf else None
        parent_uids = active_inf.get("deps", set()) if active_inf else set()

        for y in range(gh):
            for x in range(gw):
                val = packer.base_grid[y][x]
                x1, y1 = ox + x * tile_px, oy + (gh - 1 - y) * tile_px
                x2, y2 = x1 + tile_px, y1 + tile_px
                if val == 0:
                    c.create_rectangle(x1, y1, x2, y2, fill="#2e3440", outline="#383f4d", width=1)
                elif val == 2:
                    c.create_rectangle(x1, y1, x2, y2, fill="#5c4938", outline="#3e3023", width=1)
                    c.create_line(x1, y1 + 2, x2, y1 + 2, fill="#806750", width=2)
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    r_dot = max(2, tile_px // 9)
                    c.create_oval(cx - r_dot, cy - r_dot, cx + r_dot, cy + r_dot, fill="#e5d6c5", outline="#2b2118")
                else:
                    c.create_rectangle(x1, y1, x2, y2, fill="#1b1e26", outline="#181b22", width=1)

        for x in range(gw):
            if any(packer.base_grid[y][x] in (0, 2) for y in range(gh)):
                c.create_text(ox + x * tile_px + tile_px // 2, oy + grid_px_h + 11, text=str(x), fill="#8892b0", font=("Segoe UI", 7, "bold"))
        for y in range(gh):
            lbl = "Flr" if y == 0 else ("Ceil" if (y == gh - 1 and not packer.is_attic) else f"R{y}")
            c.create_text(ox - 18, oy + (gh - 1 - y) * tile_px + tile_px // 2, text=lbl, fill="#8892b0", font=("Segoe UI", 7, "bold"))

        # Pass 1: Background / Headroom cells (t == 4)
        for inf in room.placements:
            p = inf["piece"]
            cells = inf.get("cells", p.cells)
            pal_fill, _, _ = self.PIECE_PALETTE[(inf["order_num"] - 1) % len(self.PIECE_PALETTE)]
            is_act = (p.uid == active_uid)
            hr_set = {(inf["x0"] + dx, inf["y0"] + dy) for dx, dy, t in cells if t == 4}
            for rx, ry in hr_set:
                self.cell_hit_map[(rx, ry)] = inf
                cx1, cy1 = ox + rx * tile_px + 4, oy + (gh - 1 - ry) * tile_px + 4
                cx2, cy2 = cx1 + tile_px - 8, cy1 + tile_px - 8
                c.create_rectangle(
                    cx1, cy1, cx2, cy2,
                    fill="#262c36", outline="#ffffff" if is_act else pal_fill,
                    width=2 if is_act else 1, dash=(3, 3),
                )
            if not p.solid_cells and hr_set:
                xs = [ox + rx * tile_px + tile_px // 2 for rx, _ in hr_set]
                ys = [oy + (gh - 1 - ry) * tile_px + tile_px // 2 for _, ry in hr_set]
                mcx, mcy = sum(xs) // len(xs), sum(ys) // len(ys)
                lbl = f"#{inf['order_num']} {p.name[:13]}"
                tw = len(lbl) * 3 + 6
                c.create_rectangle(mcx - tw, mcy - 8, mcx + tw, mcy + 8, fill="#1b1e26", outline=pal_fill, width=1)
                c.create_text(mcx, mcy, text=lbl, fill="#eceff4", font=("Segoe UI", 7, "bold"))

        # Pass 2: Solid & Support cells (t in 1, 2) + Pins (t == 3)
        pad = 4
        for inf in room.placements:
            p = inf["piece"]
            cells = inf.get("cells", p.cells)
            pal_fill, pal_dark, pal_hi = self.PIECE_PALETTE[(inf["order_num"] - 1) % len(self.PIECE_PALETTE)]
            if p.special_totem and p.special_totem != "food":
                pal_fill, pal_dark, pal_hi = ("#529471", "#143322", "#8fd4af")

            is_act = (p.uid == active_uid)
            is_parent = (p.uid in parent_uids)
            border_col = "#ffffff" if is_act else ("#00f5d4" if is_parent else ("#ffd166" if p.is_rare else pal_dark))
            border_w = 3 if (is_act or is_parent or p.is_rare) else 2

            occ_set = {(inf["x0"] + dx, inf["y0"] + dy) for dx, dy, t in cells if t in (1, 2)}
            sup_set = {(inf["x0"] + dx, inf["y0"] + dy) for dx, dy, t in cells if t == 2}
            pin_set = {(inf["x0"] + dx, inf["y0"] + dy) for dx, dy, t in cells if t == 3}

            for rx, ry in pin_set:
                px1, py1 = ox + rx * tile_px, oy + (gh - 1 - ry) * tile_px
                mcx, mcy = px1 + tile_px // 2, py1 + tile_px // 2
                if getattr(p, "kind", "") == "hanging":
                    c.create_line(mcx - 3, mcy, mcx - 3, py1 + tile_px + pad, fill="#d8dee9", width=2)
                    c.create_line(mcx + 3, mcy, mcx + 3, py1 + tile_px + pad, fill="#d8dee9", width=2)
                else:
                    c.create_line(mcx - 4, py1 - pad, mcx - 2, mcy, fill="#e5c07b", width=3)
                    c.create_line(mcx + 4, py1 - pad, mcx + 2, mcy, fill="#e5c07b", width=3)

            if not occ_set:
                continue

            for rx, ry in occ_set:
                self.cell_hit_map[(rx, ry)] = inf
                x1 = ox + rx * tile_px + (0 if (rx - 1, ry) in occ_set else pad)
                x2 = ox + (rx + 1) * tile_px - (0 if (rx + 1, ry) in occ_set else pad)
                y1 = oy + (gh - 1 - ry) * tile_px + (0 if (rx, ry + 1) in occ_set else pad)
                y2 = oy + (gh - ry) * tile_px - (0 if (rx, ry - 1) in occ_set else pad)

                c.create_rectangle(x1 + 2, y1 + 2, x2 + 2, y2 + 2, fill="#14171d", outline="")
                c.create_rectangle(x1, y1, x2, y2, fill=pal_fill, outline="")

                if (rx + 1, ry) in occ_set:
                    c.create_line(x2, y1 + 3, x2, y2 - 3, fill=pal_dark, dash=(2, 3))
                if (rx, ry - 1) in occ_set:
                    c.create_line(x1 + 3, y2, x2 - 3, y2, fill=pal_dark, dash=(2, 3))

            for rx, ry in sup_set:
                x1 = ox + rx * tile_px + (0 if (rx - 1, ry) in occ_set else pad)
                x2 = ox + (rx + 1) * tile_px - (0 if (rx + 1, ry) in occ_set else pad)
                y1 = oy + (gh - 1 - ry) * tile_px + (0 if (rx, ry + 1) in occ_set else pad)
                c.create_rectangle(x1, y1, x2, y1 + 6, fill=pal_dark, outline="")
                mcx = (ox + rx * tile_px) + tile_px // 2
                c.create_oval(mcx - 3, y1 + 1, mcx + 3, y1 + 7, fill="#ffffff", outline="#1a1819", width=1)

            for rx, ry in occ_set:
                x1 = ox + rx * tile_px + (0 if (rx - 1, ry) in occ_set else pad)
                x2 = ox + (rx + 1) * tile_px - (0 if (rx + 1, ry) in occ_set else pad)
                y1 = oy + (gh - 1 - ry) * tile_px + (0 if (rx, ry + 1) in occ_set else pad)
                y2 = oy + (gh - ry) * tile_px - (0 if (rx, ry - 1) in occ_set else pad)

                if (rx, ry + 1) not in occ_set:
                    c.create_line(x1, y1 + 1, x2, y1 + 1, fill=pal_hi, width=1)
                    c.create_line(x1, y1, x2, y1, fill=border_col, width=border_w)
                if (rx, ry - 1) not in occ_set:
                    c.create_line(x1, y2, x2, y2, fill=border_col, width=border_w)
                if (rx - 1, ry) not in occ_set:
                    c.create_line(x1 + 1, y1, x1 + 1, y2, fill=pal_hi, width=1)
                    c.create_line(x1, y1, x1, y2, fill=border_col, width=border_w)
                if (rx + 1, ry) not in occ_set:
                    c.create_line(x2, y1, x2, y2, fill=border_col, width=border_w)

            top_ry = max(ry for _, ry in occ_set)
            left_top_rx = min(rx for rx, ry in occ_set if ry == top_ry)
            bx = ox + left_top_rx * tile_px + pad
            by = oy + (gh - 1 - top_ry) * tile_px + pad
            c.create_rectangle(bx, by, bx + 22, by + 13, fill="#1b1e26", outline=border_col, width=1)
            c.create_text(bx + 11, by + 6, text=f"#{inf['order_num']}", fill="#ffd166" if p.is_rare else "#eceff4", font=("Segoe UI", 7, "bold"))

            xs = [ox + rx * tile_px + tile_px // 2 for rx, _ in occ_set]
            ys = [oy + (gh - 1 - ry) * tile_px + tile_px // 2 for _, ry in occ_set]
            mcx, mcy = sum(xs) // len(xs), sum(ys) // len(ys) + 4
            span_w = (max(rx for rx, _ in occ_set) - min(rx for rx, _ in occ_set) + 1) * tile_px - 10
            max_ch = max(4, span_w // 6)
            prefix = ("★" if p.is_rare else "") + ("⇄" if inf.get("is_flipped") else "")
            disp = (prefix + p.name)[:max_ch]
            pill_w = min(span_w // 2, len(disp) * 3 + 5)
            c.create_rectangle(mcx - pill_w, mcy - 7, mcx + pill_w, mcy + 7, fill="#1b1e26", outline=pal_dark, width=1)
            c.create_text(mcx, mcy, text=disp, fill="#ffd166" if p.is_rare else "#f2f4f8", font=("Segoe UI", 7, "bold"))

        # Room Stats Panel (including AutoCattery C+S+H+M Sum!)
        t = room.totals
        tx, ty = cw - 118, 12
        c.create_rectangle(tx, ty, tx + 106, ty + 146, fill="#232731", outline="#4c566a", width=2)
        for st_txt, col_fg, sy in [
            (f"✨ App: {t['Appeal']:+d}", "#ebcb8b", ty + 15),
            (f"🛋️ Comf: {t['Comfort']:+d}", "#a3be8c", ty + 37),
            (f"⚡ Stim: {t['Stimulation']:+d}", "#88c0d0", ty + 59),
            (f"🏥 Heal: {t['Health']:+d}", "#bf616a", ty + 81),
            (f"🧬 Mut: {t['Mutation']:+d}", "#b48ead", ty + 103),
            (f"∑ AC: {room.autocattery_breed_sum:+d}", "#d8dee9", ty + 128),
        ]:
            c.create_text(tx + 53, sy, text=st_txt, fill=col_fg, font=("Segoe UI", 9, "bold"))

        occ_sum = sum(len(p.solid_cells) for p in room.placed)
        eff_s = max(0, t["Stimulation"])
        p_high = ((1.0 + 0.01 * eff_s) / (2.0 + 0.01 * eff_s)) * 100.0
        p_sp1 = min(100.0, (0.20 + 0.025 * eff_s) * 100.0)
        p_pas = min(100.0, (0.05 + 0.01 * eff_s) * 100.0)
        c.create_text(
            ox, oy - 16,
            text=f"{room.name} — {len(room.placed)} Pieces ({occ_sum}/{packer.free_tiles}■ | Stat:{p_high:.1f}% | 1stSpell:{p_sp1:.0f}% | Passive:{p_pas:.0f}%)",
            fill="#eceff4", font=("Segoe UI", 10, "bold"), anchor="w",
        )

    def _render_breeding_plan_tab(self):
        plan = self.current_plan
        if plan is None:
            self.breeding_text.delete("1.0", "end")
            self.breeding_text.insert("1.0", "Waiting for save data...")
            return

        d = plan.demand
        eff_s = max(0, plan.room_stim_used)
        p_high = ((1.0 + 0.01 * eff_s) / (2.0 + 0.01 * eff_s)) * 100.0
        p_sp1 = min(100.0, (0.20 + 0.025 * eff_s) * 100.0)
        p_pas = min(100.0, (0.05 + 0.01 * eff_s) * 100.0)
        p_sp2 = min(100.0, (0.02 + 0.005 * eff_s) * 100.0)

        lines: List[str] = [
            f"🧬 CLOSED-LOOP BREEDING & HOUSE STRATEGY — STAGE: {plan.stage}",
            "=" * 116,
            f"  • Solved Room 1 Chapel Stim: {eff_s}  =>  P(Higher Stat): {p_high:.1f}% | 1st Spell: {p_sp1:.0f}% | Passive: {p_pas:.0f}% | 2nd Spell: {p_sp2:.0f}%",
            f"  • Active Room Roles ({d.unlocked_rooms} Unlocked): " + "  |  ".join(f"R{i+1}: {r}" for i, r in enumerate(d.room_roles)),
            f"  • AutoCattery Protection Sync: Top 4 Retired Defenders + Top 2 Foundation Breeders -> `config/protection.json` (NoCull, user rules preserved)",
        ]
        if plan.notes:
            for nt in plan.notes:
                lines.append(f"  ⚡ SYNERGY NOTE: {nt}")

        lines.append("\n💕 1. PRIMARY BREEDING CHAPEL PAIRS (Room 1 — Exact Wright's COI + Patch 1.1 Stim Attenuation):")
        lines.append("-" * 116)
        if not plan.primary_pairs:
            lines.append("  (No fertile compatible pairs found yet — build up adult roster)")
        for idx, pr in enumerate(plan.primary_pairs, 1):
            a, b = pr.cat_a, pr.cat_b
            lines.append(
                f"  Pair #{idx}: {a.name} ({a.sex[0]}, Sum:{a.combat_sum}, {a.sevens_count}×7)  ×  "
                f"{b.name} ({b.sex[0]}, Sum:{b.combat_sum}, {b.sevens_count}×7)  "
                f"=>  Exp Sum: {pr.expected_combat_sum:.1f} | Exp 7s: {pr.expected_sevens:.2f} | {pr.notes}"
            )

        if plan.secondary_pairs:
            lines.append("\n✨ 2. SECONDARY OUTCROSS PAIRS:")
            lines.append("-" * 116)
            for idx, pr in enumerate(plan.secondary_pairs, 1):
                a, b = pr.cat_a, pr.cat_b
                lines.append(
                    f"  Outcross #{idx} ({pr.room_target}): {a.name} (Sum:{a.combat_sum}) × {b.name} (Sum:{b.combat_sum}) "
                    f"=> Exp Sum: {pr.expected_combat_sum:.1f} | {pr.notes}"
                )

        lines.append("\n🛡️ 3. TOP 4 RETIRED HOUSE-BOSS DEFENDERS (Auto-Protected `NoCull` in `config/protection.json` -> Barracks):")
        lines.append("-" * 116)
        if not plan.retired_defenders:
            lines.append("  (No living retired cats under age 15 yet)")
        for idx, c in enumerate(plan.retired_defenders, 1):
            lines.append(
                f"  #{idx} {c.name:<18} | Age:{c.age:<2} | CombatSum:{c.combat_sum:<2} ({c.sevens_count}×7) | "
                f"Score:{c.defender_score:>5.1f} | Skills: {', '.join(c.abilities[:4]) or 'None'}"
            )

        lines.append("\n⚔️ 4. RECOMMENDED 4-CAT ADVENTURE SQUAD (Keep Healthy in Barracks / Ward):")
        lines.append("-" * 116)
        for idx, c in enumerate(plan.adventure_squad, 1):
            lines.append(
                f"  #{idx} {c.name:<18} | Age:{c.age:<2} | CombatSum:{c.combat_sum:<2} ({c.sevens_count}×7) | "
                f"STR:{c.stats['STR']} DEX:{c.stats['DEX']} CON:{c.stats['CON']} INT:{c.stats['INT']} SPD:{c.stats['SPD']} LCK:{c.stats['LCK']} (CHA:{c.stats['CHA']})"
            )

        if plan.mutation_candidates:
            lines.append("\n🧬 5. PATCH 1.1 >10 MUTATION LAB CANDIDATES (Room 4):")
            lines.append("-" * 116)
            for c in plan.mutation_candidates:
                lines.append(f"  • {c.name:<18} | Sum:{c.combat_sum} ({c.sevens_count}×7) | Existing Muts:{len(c.mutations)}")

        if plan.fight_pit_cats:
            lines.append("\n🥊 6. FIGHT PIT / BABY JACK RARE-FURNITURE FARMERS (Room 3 — Comfort <= -10):")
            lines.append("-" * 116)
            lines.append("  " + ", ".join(f"{c.name} (Sum:{c.combat_sum}{' 🩹' if c.is_injured else ''})" for c in plan.fight_pit_cats))

        if plan.cull_queue:
            lines.append("\n📦 7. SMART NPC DONATION QUEUE (Safe to Pipe when >25 Cats — Zero VIP Overlap):")
            lines.append("-" * 116)
            for c, npc_reason in plan.cull_queue:
                lines.append(f"  • {c.name:<18} (Age:{c.age}, Sum:{c.combat_sum})  ->  {npc_reason}")

        self.breeding_text.delete("1.0", "end")
        self.breeding_text.insert("1.0", "\n".join(lines))

    def _render_current(self):
        if not self.current_rooms:
            return
        ret_names = ", ".join(f"{c.name} (Sum:{c.combat_sum})" for c in self.top_4) or "None retired yet"
        self.retired_lbl.config(
            text=f"🛡️ AutoCattery `config/protection.json` Synced ({self.synced_cnt} mod dir) — Top 4 Retired Defenders: {ret_names}"
        )
        self.strat_lbl.config(text=f"🗿 {self.strat_name}")

        is_breeding_tab = self.selected_tab_idx >= len(self.current_rooms)
        if is_breeding_tab:
            self.blueprint_frame.pack_forget()
            self.breeding_frame.pack(fill="both", expand=True)
            self._render_breeding_plan_tab()
            return

        self.breeding_frame.pack_forget()
        self.blueprint_frame.pack(fill="both", expand=True)
        self._draw_blueprint_room()

        room = self.current_rooms[self.selected_tab_idx]
        placements = [inf for inf in room.placements if not self.only_show_moves or inf["piece"].current_room != room.room_id]

        lines = [f"📋 LOCKED TOPOLOGICAL BUILD ORDER (#01 -> #{len(room.placements):02d}) FOR {room.name.upper()}:", "-" * 124]
        if not placements:
            lines.append("   ✔ Every item for this room is ALREADY in place!" if self.only_show_moves else "   (Leave Room Empty)")
        else:
            for inf in placements:
                p = inf["piece"]
                r_tag = " [★RARE 2x]" if p.is_rare else ""
                fl_tag = " [⇄Flip]" if inf.get("is_flipped") else ""
                t_tag = f" [🗿{p.special_totem.upper()}]" if p.special_totem else ""
                mv = f"✔ Keep in {room.internal_room_name}" if p.current_room == room.room_id else f"👉 Move {p.current_room_label} -> {room.internal_room_name}"
                st = f"A:{p.appeal:+d} C:{p.comfort:+d} S:{p.stim:+d} H:{p.health:+d} M:{p.mutation:+d}"
                cs = f"Col {inf['x0']:02d}, R{inf['y0']} ({len(p.solid_cells)}■,{len(p.support_cells)}●,{len(p.pin_cells)}+)"
                lines.append(f"  #{inf['order_num']:02d} {inf['rests_on_label']:<28} | {(p.name + r_tag + fl_tag + t_tag):<32} | {cs:<22} | [{st}] | {mv}")

        if self.current_storage:
            lines.append("-" * 124)
            lines.append("📦 LEAVE IN STORAGE: " + ", ".join(f"{p.name}{'★' if p.is_rare else ''}" for p in self.current_storage))

        self.text.delete("1.0", "end")
        self.text.insert("1.0", "\n".join(lines))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    FurnitureArchitectUI().run()