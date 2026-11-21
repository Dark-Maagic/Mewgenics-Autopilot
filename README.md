# Mewgenics Closed-Loop Breeding & 2D Spatial Furniture Architect

A **100% legitimate, non-cheating** automation companion and 2D spatial furniture solver for ***Mewgenics*** (Windows x64).

This repository couples **recursive evolutionary genetics** (Wright's Coefficient of Inbreeding, complementary 7-stat pair matching, anti-Charisma-Drift weighting, and Retired House-Boss protection) with a **gravity-constrained 2D polyomino furniture optimizer** (exact 4-cell physics, horizontal mirroring, and multi-move Simulated Annealing) in a single closed loop that adapts dynamically to your save's progression.

> **Strict Vanilla Constraint:** This mod **never** alters game RNG, stat rolls, food counts, or save files. It only reads your live save safely (via atomic WAL snapshots), computes optimal decisions, renders step-by-step 2D furniture blueprints, and syncs non-destructive cat protection rules to **AutoCattery**.

---

## Repository Contents

| File | Role |
| :--- | :--- |
| **`mew_autopilot.py`** | Main closed-loop engine & Studio UI. Parses your live `steamcampaign01.sav` (SQLite + LZ4 blobs), computes Wright's COI breeding pairs, adapts room roles to Patch 1.1+ milestones, solves optimal 2D furniture layouts across 1–5 rooms, and safely syncs VIP `NoCull` protections to AutoCattery's `config/protection.json`. |
| **`ingamebutton.py`** | Optional transparent cardboard HUD overlay positioned on the in-game House top bar. **Left-Click** syncs pedigree protections & opens AutoCattery (`F10`); **Shift + Left-Click** launches the 2D Architect window; **Right-Click Drag** repositions the sign. |
| **`start_autopilot.bat`** | One-click Windows launcher that starts the Python Architect companion alongside `Mewtator.exe`. |

---

## Prerequisites (Required Mods, Tools & Files)

Because `mew_autopilot.py` and `ingamebutton.py` act as the **strategic brain & 2D spatial planner** on top of in-game room-sorting hooks, you must download and install the following components **first**:

### 1. Game & Runtime
* ***Mewgenics*** (Steam, Windows x64) — installed with at least 1 in-game day saved (`%APPDATA%\Glaiel Games\Mewgenics\<SteamID>\saves\steamcampaign01.sav`).
* **Python 3.12+** (tested on **Python 3.14** via the Windows `py` launcher) with `tkinter` enabled (included in the standard Windows installer from [python.org](https://www.python.org/downloads/)).
* **Required Python packages:**
  ```powershell
  py -3.14 -m pip install lz4
  ```
  *(If you use another Python 3.x version, replace `-3.14` with your version or run `pip install lz4`.)*

### 2. Mod Manager & DLL Chainloader
* **Mewtator (`v0.6.0+`)** — The mod manager used to launch *Mewgenics* with DLL and SWF mod support.
  * In Mewtator settings, ensure **"Enable DLL Mod Support"** is toggled **ON** (this deploys/chainloads **Mewjector** / `version.dll` into your game folder).

### 3. In-Game Housekeeping Mod
* **AutoCattery (`v0.5.35+`)** — Handles physical in-game cat room-routing, poop cleanup, and new-day NPC culling via its in-game hanging signs and `F10` panel.
  * Install `AutoCattery` into your `Mewtator\mods\AutoCattery\` directory (containing `AutoCattery.dll`, `description.json`, `data\`, and `swfs\`).
  * **SWF Conflict Warning:** Do **not** enable `QuickCleanup` alongside `AutoCattery`. `QuickCleanup` overwrites AutoCattery's modified House SWF (`swfs\`), and `AutoCattery` already includes native poop cleanup.

### 4. Save Parser & Furniture Data Sources
* **`MewgenicsBreedingManager` (`src/save_parser.py`)** — Download/clone [`frankieg33/MewgenicsBreedingManager`](https://github.com/frankieg33/MewgenicsBreedingManager) (or [`whyayala/MewgenicsBreedingManager`](https://github.com/whyayala/MewgenicsBreedingManager)) so `src/save_parser.py` sits alongside this repository's files.
  * *Note:* On first run with internet access, `mew_autopilot.py` also automatically fetches and caches:
    * `whyayala_save_parser_cache.py` (from `whyayala/MewgenicsBreedingManager`)
    * `notalim_furniture_cache.json` and `notalim_house_cache.json` (from [`notalim/mewgenics-house-planner`](https://github.com/notalim/mewgenics-house-planner))
  * It additionally reads your local `resources.gpak` for localization fallbacks.

---

## Installation & Setup Guide

### Step 1: Arrange Your Folder Structure
Place the three files from this repository into the root folder of your extracted `MewgenicsBreedingManager` directory (so `src\save_parser.py` is directly accessible):

```text
MewgenicsBreedingManager-main/
├── src/
│   └── save_parser.py
├── mew_autopilot.py
├── ingamebutton.py
└── start_autopilot.bat
```

### Step 2: Update `start_autopilot.bat` Paths
Open `start_autopilot.bat` in any text editor and update the path to **your own** `Mewtator.exe` (and Python version flag if you are not on `3.14`):

```bat
@echo off
cd /d "%~dp0"
start "" pyw -3.14 "%~dp0mew_autopilot.py"
REM Uncomment the line below if you also want the in-game floating cardboard HUD button:
REM start "" pyw -3.14 "%~dp0ingamebutton.py"
start "" "C:\Path\To\Your\Mewtator\Mewtator.exe"
```

### Step 3: Configure AutoCattery In-Game (`F10`)
Launch *Mewgenics* through **Mewtator** (with **Enable DLL Mod Support = ON**), load your house, press **`F10`** to open AutoCattery's settings, and apply these recommended vanilla-legit settings so the in-game sorter synergizes with `mew_autopilot.py`:

| Setting | Recommended Value | Why |
| :--- | :--- | :--- |
| **Read-Only Mode** | `Off` | Allows AutoCattery to move cats, clean poop, and trim excess cats on new days. |
| **Single-Click Execution** | `On` | Clicking the in-game *Auto-Organize Cattery* sign executes immediately. |
| **Newborn All-Seven Assist** | **`Off`** | Keeps gameplay 100% legit (no RNG cheats). |
| **Food Assist** | **`Off`** | Keeps gameplay 100% legit (no infinite food). |
| **Cat Limit (Auto Trim on New Day)** | `25` | Automatically pipes dead/surplus cats to NPCs without touching protected VIPs. |
| **Breeding CHA Weight** | `0.20` | Keeps `STR/DEX/CON/INT/SPD/LCK` at `1.00` while preventing Charisma Drift. |
| **Avoid Inbreeding Pairs** | `On` | Enforces low Wright's COI ($\le 0.10$) to avoid Patch 1.1 Stim attenuation & birth defects. |
| **Keep Breeding Pair Together** | `On` | Locks monogamous `Loves` pairs and prevents rival/cheating drama. |
| **Separate Kittens When Possible** | `On` | Evacuates kittens to safe rooms so they don't mature and inbreed with parents. |

---

## How to Use

1. **Double-click `start_autopilot.bat`** to open the **Closed-Loop Architect UI** and **Mewtator**.
2. Launch *Mewgenics* from Mewtator.
3. **Build Your Rooms Using the Blueprint Tabs (`R1`–`R5`):**
   * Each room tab renders the exact tile grid (`Flr`, `R1`–`R8`, sloped Attic roof, support bolts `●`, and background layers `□`).
   * Follow the **Topological Build Order (`#01 → #N`)** listed below the canvas—shelf providers are always numbered before the toppers that rest on them.
   * **Hover / Left-Click** any furniture piece to inspect its stats and highlight its parent shelf in **cyan**.
   * **Right-Click** any furniture piece (or click **`★ Rare (2x)...`**) to toggle `★ Rare (2x Stats)` if your save didn't flag it automatically.
   * Toggle **`🎯 Moves Only: ON`** to hide items already in the correct room.
   * Items marked **`⇄Flip`** should be right-clicked in-game to mirror horizontally.
   * If you just unlocked a new empty room and `Auto` hasn't detected it yet, use the **`Rooms:`** dropdown (`Auto / 1–5`) in the top bar.
4. **Check the `🧬 Breeding & Roster Plan` Tab:**
   * Displays your detected campaign stage (`EARLY_FOUNDATION`, `STAT_CONSOLIDATION`, or `ENDGAME_MUTATION_SKILLS`), recommended non-overlapping breeding pairs with exact **Wright's COI %** and expected offspring stats at your **actual solved Room 1 Stimulation**, Top 4 Retired House-Boss Defenders, Adventure Squad, Mutation Lab candidates, Fight Pit farmers, and safe NPC donation queue.
5. **Confirm AutoCattery Sync:**
   * Look for **`AutoCattery Lock: ✔`** in the status banner—this guarantees Room 1 strictly outranks all other breeding-eligible rooms on AutoCattery's `Comfort + Stimulation + Health + Mutation` formula, and that the Fight Pit stays at `Comfort <= -10`.
   * Your Top 4 Retired Defenders (+ Top 2 Foundation Breeders) are automatically merged as `NoCull` into `Mods\AutoCattery\config\protection.json` while preserving all manual `F10` rules.

---

## How the Closed-Loop Synergy Works

1. **Dynamic Progression Roles:**
   * **Room 1 (`Attic`):** Primary *Breeding Chapel* — maximizes SciresM's inheritance curve $P(\text{high}) = \frac{1 + 0.01 S}{2 + 0.01 S}$ and skill milestones (`32` 1st Spell, `95` Passive, `196` 2nd Spell) with dynamic Comfort buffers scaled to your live cat count and `Mutation <= 0`. Soft-caps Health at `<= 10` if a primary breeder holds a beneficial disorder (e.g., *Schrödinger's Syndrome*, *Lycanthropy*, *Dwarfism*).
   * **Room 2 (`Floor2_Large`):** *Chastity Barracks & Disorder Ward* — locks `Idol of Chastity`, buffers overcrowding Comfort, and pushes Health `> 10` to heal fighters and cure bad run disorders overnight.
   * **Room 3 (`Floor1_Small`):** *Chaos Fight Pit & Baby Jack Farm* — locks `Idol of Chaos` and targets `Comfort <= -10` (excluded by AutoCattery) + `Health 0..5` to farm fight stat boosts and injured donations for Baby Jack's Rare furniture shop scaling.
   * **Room 4 (`Floor1_Large`):** *Patch 1.1 Evolution Lab* — only activates once your inventory can exceed **`Mutation > 10`** (avoiding the Patch 1.1 `1..10` simple stat-shift dead zone); before then, Room 4 is automatically repurposed as a *Secondary Outcross Suite*.
   * **Room 5 (`Floor2_Small`):** *Secondary Outcross / Appeal Vault* — pushes whole-house Appeal toward the `50 / 100 / 200` Stray milestones.
2. **Locked Blueprint Stability:** Once solved, the 2D blueprint stays locked while you drag furniture in-game (updating only your live "Keep / Move" checklist) and only re-solves when you acquire new furniture, unlock a room, toggle Rare status, or click **`🔄 Force Re-Solve`**.

---

## Troubleshooting

* **`mew_autopilot.py` closes immediately when launched from `start_autopilot.bat`:**
  Run it from PowerShell/CMD to see the error message:
  ```powershell
  py -3.14 mew_autopilot.py
  ```
  Usually this means Python 3.14 isn't installed (change `-3.14` to `-3` in `start_autopilot.bat`) or `lz4` needs to be installed (`pip install lz4`).
* **"No Save!" or empty furniture list:**
  Ensure you have played and saved at least 1 day in-game, and click **`🌐 Sync Notalim DB`** once while connected to the internet to populate the local furniture cache (`notalim_furniture_cache.json`).
* **AutoCattery isn't loading in-game / `F10` doesn't open:**
  1. Launch the game **through Mewtator**, not directly via Steam.
  2. Confirm **"Enable DLL Mod Support"** is enabled in Mewtator.
  3. Confirm `QuickCleanup` is disabled in Mewtator.
  4. Verify `AutoCattery.dll` exists inside `Mewtator\mods\AutoCattery\`.
* **Files generated automatically in the project folder:**
  `rare_overrides.json`, `autopilot_managed_protections.json`, `autopilot_plan_summary.json`, `notalim_furniture_cache.json`, `notalim_house_cache.json`, and `whyayala_save_parser_cache.py`. You can add these to `.gitignore` if publishing your own fork.

---

## Credits & Acknowledgments
* **[AutoCattery](https://www.nexusmods.com/)** — In-game Cattery sorting, cleanup, and protection hooks.
* **[notalim/mewgenics-house-planner](https://github.com/notalim/mewgenics-house-planner)** — Exact 4-cell furniture geometry and room grid definitions.
* **[frankieg33/MewgenicsBreedingManager](https://github.com/frankieg33/MewgenicsBreedingManager)** & **[whyayala/MewgenicsBreedingManager](https://github.com/whyayala/MewgenicsBreedingManager)** — Save parsing foundations.
* **SciresM & the Mewgenics Wiki community** — Datamined breeding inheritance and Patch 1.1 mutation formulas.