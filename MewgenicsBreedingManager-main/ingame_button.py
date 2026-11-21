#!/usr/bin/env python3
"""
ingame_button.py (v2.0 — Closed-Loop Mewgenics Cardboard & Masking-Tape HUD)
Synced with mew_autopilot v10.0:
  - Left-Click: Runs full closed-loop pedigree + furniture analysis, safely updates
    `Mods/AutoCattery/config/protection.json` (preserving user F10 rules), and triggers F10.
  - Shift + Left-Click: Launches the full 2D Furniture & Breeding Architect window.
  - Right-Click Drag: Reposition sign anywhere on screen.
"""

import os
import sys
import time
import shutil
import ctypes
import subprocess
import tkinter as tk
from pathlib import Path
import mew_autopilot as brain

user32 = ctypes.windll.user32
CHROMA_KEY = "#00ff01"  # Rendered 100% invisible by Windows
SCRIPT_DIR = Path(__file__).resolve().parent


def ensure_dll_linked():
    """Ensures AutoCattery.dll is present inside Mewtator's mods folder so Mewjector loads it."""
    steam_candidates = [
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Mewgenics\Mods\AutoCattery\AutoCattery.dll"),
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Mewgenics\Mods\AutoCattery.dll"),
    ]
    steam_dll = next((p for p in steam_candidates if p.exists()), None)
    downloads = Path.home() / "Downloads"
    if steam_dll and downloads.exists():
        for mewtator_mod_dir in downloads.rglob("Mewtator/mods/AutoCattery"):
            target_dll = mewtator_mod_dir / "AutoCattery.dll"
            if not target_dll.exists():
                try:
                    shutil.copy2(steam_dll, target_dll)
                except Exception:
                    pass


def tap_key(vk_code: int):
    user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.06)
    user32.keybd_event(vk_code, 0, 2, 0)


class MewgenicsCardboardButton:
    def __init__(self):
        ensure_dll_linked()

        self.root = tk.Tk()
        self.root.title("Mewgenics Autopilot HUD")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", CHROMA_KEY)
        self.root.configure(bg=CHROMA_KEY)

        screen_w = self.root.winfo_screenwidth()
        x_pos = int(screen_w * 0.255)
        y_pos = 10
        self.w = 290
        self.h = 112
        self.root.geometry(f"{self.w}x{self.h}+{x_pos}+{y_pos}")

        self.canvas = tk.Canvas(
            self.root,
            width=self.w,
            height=self.h,
            bg=CHROMA_KEY,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)

        self._is_hovered = False
        self._status_text = "Click: Sync F10 | Shift+Click: Blueprint"
        self._main_text = "Auto-Breed"
        self._drag_x = 0
        self._drag_y = 0
        self._draw_sign()

        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_click)
        self.canvas.bind("<ButtonPress-3>", self._start_move)
        self.canvas.bind("<B3-Motion>", self._on_move)

    def _draw_sign(self):
        self.canvas.delete("all")
        dy = 2 if self._is_hovered else 0

        ink = "#1a1819"
        paper_main = "#d2d0cc" if self._is_hovered else "#c2c0bd"
        paper_hi = "#dedcd8" if self._is_hovered else "#d1cfcb"
        paper_shadow = "#94918c"
        tape_color = "#dcd9d0"

        # 1. Drop shadow behind cardboard sign
        self.canvas.create_polygon(
            18, 22 + dy,  274, 18 + dy,  278, 80 + dy,  268, 102 + dy,  14, 98 + dy,  12, 50 + dy,
            fill="#0d0c0e", outline="",
        )

        # 2. Main hand-cut jagged cardboard sign (thick charcoal ink border)
        card_pts = [
            14, 17 + dy,   140, 14 + dy,  268, 16 + dy,
            273, 54 + dy,  266, 95 + dy,  145, 97 + dy,
            15, 93 + dy,   10, 52 + dy,
        ]
        self.canvas.create_polygon(
            card_pts, fill=paper_main, outline=ink, width=4, joinstyle="round"
        )

        # 3. Bottom shaded bevel & top highlight
        self.canvas.create_polygon(
            16, 76 + dy,  266, 77 + dy,  264, 93 + dy,  17, 91 + dy,
            fill=paper_shadow, outline="",
        )
        self.canvas.create_line(18, 21 + dy, 263, 20 + dy, fill=paper_hi, width=3)
        self.canvas.create_line(19, 71 + dy, 261, 72 + dy, fill="#7a7772", width=2)

        # 4. Crooked masking tape at top center
        tape_pts = [106, 4 + dy,  184, 6 + dy,  180, 24 + dy,  102, 22 + dy]
        self.canvas.create_polygon(tape_pts, fill=tape_color, outline=ink, width=2)

        # 5. Hand-drawn black-ink cat head silhouette
        cx, cy = 44, 46 + dy
        self.canvas.create_polygon(
            cx - 16, cy + 10,
            cx - 18, cy - 16,
            cx - 6,  cy - 7,
            cx + 6,  cy - 7,
            cx + 18, cy - 16,
            cx + 16, cy + 10,
            cx,      cy + 15,
            fill=ink, outline=ink, width=2,
        )
        self.canvas.create_oval(cx - 10, cy - 2, cx - 3, cy + 5, fill=paper_main, outline="")
        self.canvas.create_oval(cx + 3,  cy - 2, cx + 10, cy + 5, fill=paper_main, outline="")

        # 6. Title & Status text
        self.canvas.create_text(
            156, 43 + dy,
            text=self._main_text,
            fill=ink,
            font=("Comic Sans MS", 16, "bold"),
        )
        self.canvas.create_text(
            142, 83 + dy,
            text=self._status_text,
            fill="#242223",
            font=("Comic Sans MS", 8, "bold"),
        )

        # 7. Tiny close '×' in top-right corner
        self.canvas.create_text(
            258, 28 + dy,
            text="×",
            fill="#5c5955",
            font=("Comic Sans MS", 12, "bold"),
            tags="close_btn",
        )

    def _on_enter(self, _event):
        self._is_hovered = True
        self._draw_sign()

    def _on_leave(self, _event):
        self._is_hovered = False
        self._draw_sign()

    def _start_move(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_move(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_x)
        y = self.root.winfo_y() + (event.y - self._drag_y)
        self.root.geometry(f"+{x}+{y}")

    def _launch_architect(self):
        script = SCRIPT_DIR / "mew_autopilot.py"
        if script.exists():
            try:
                subprocess.Popen([sys.executable, str(script)], cwd=str(SCRIPT_DIR))
                self._status_text = "Opened 2D Architect!"
                self._draw_sign()
            except Exception as e:
                self._status_text = f"Launch err: {str(e)[:22]}"
                self._draw_sign()

    def _on_left_click(self, event):
        if event.x >= 242 and event.y <= 38:
            self.root.destroy()
            return
        # Shift+Click launches the full 2D Furniture & Breeding Architect UI
        if event.state & 0x0001:
            self._launch_architect()
            return
        self.run_one_click_autopilot()

    def run_one_click_autopilot(self):
        self._main_text = "Solving..."
        self._status_text = "Pedigree COI + Furniture Synergy..."
        self._draw_sign()
        self.root.update()

        try:
            sav_path = brain.find_latest_save()
            if not sav_path:
                self._main_text = "No Save!"
                self._status_text = "Play 1 day first"
                self._draw_sign()
                return

            cats, furniture, room_count = brain.load_save_cats_and_furniture(sav_path)
            opt = brain.AdaptiveOptimizer(cats, room_count, furniture)
            plan_dict = opt.solve()
            top_4, synced = brain.sync_autocattery_config(plan_dict)

            # Trigger F10 in Mewgenics to open/refresh AutoCattery
            tap_key(0x79)  # VK_F10

            plan_obj = plan_dict.get("plan")
            if plan_obj and plan_obj.primary_pairs:
                p0 = plan_obj.primary_pairs[0]
                pair_lbl = f"{p0.cat_a.name[:8]}×{p0.cat_b.name[:8]} COI:{p0.coi*100:.0f}%"
                self._main_text = "Synced ✔"
                self._status_text = f"{pair_lbl} | Prot:{len(top_4)}"
            else:
                squad = ", ".join(c.name[:7] for c in plan_dict.get("adventure_squad", [])[:3])
                self._main_text = "House Ready!"
                self._status_text = f"Run: {squad} | Prot:{len(top_4)}" if squad else f"Synced ({synced} cfg)!"
            self._draw_sign()
        except Exception as e:
            self._main_text = "Retry"
            self._status_text = str(e)[:30]
            self._draw_sign()

        self.root.after(5000, self._reset_label)

    def _reset_label(self):
        self._main_text = "Auto-Breed"
        self._draw_sign()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    MewgenicsCardboardButton().run()