# PPD Assistant — AI Agent for Steel Manufacturing

A focused, **skill-limited** AI agent for the Product Planning & Design (PPD)
domain in steel manufacturing. Built specifically because general-purpose
agents (Hermes, QwenPaw, etc.) are too broad and lose focus on domain-specific
questions.

The agent does **only** what it has tools for — there are **20 deterministic
Python tools across 5 modules**. The LLM (via OpenRouter) only decides which
tool to call and how to summarise the result. All numerical computation
(filtering, statistics, Deboer formulas, compliance, feasibility synthesis)
happens in Python, never in the LLM. This guarantees correctness on the
things that matter.

All tool outputs are **plain text** (no markdown), so they render cleanly
on Telegram.

## Skills (20 tools, 5 modules)

| Module | Tool | Purpose |
|---|---|---|
| **1. Product Design Lookup** | `lookup_steel_grade` | Steel Grade + HR Spec Code dari spec + thickness |
| | `lookup_chem_standard` | Standar kimia min/max per spec |
| | `lookup_mech_standard` | Standar TS/YS/Charpy/HIC/DWTT per spec |
| | `lookup_elongation_standard` | Standar elongation per spec + thickness |
| | `lookup_thickness_tolerance` | Toleransi tebal per dim_thickness + width |
| | `lookup_ft_ct_design` | Rekomendasi Finish/Coil Temperature codes |
| **2. HRC Production Analysis** (~290k coils 2021) | `hrc_filter` | Filter dataset, return ringkasan + sample |
| | `hrc_statistics` | n / mean / std / min / p25 / median / p75 / max |
| | `hrc_histogram` | Histogram PNG |
| | `hrc_scatter` | Scatter plot + Pearson correlation |
| | `hrc_correlation_heatmap` | Correlation heatmap |
| | `hrc_lookup_coil` | Detail satu coil |
| **3. Deboer Property Prediction** | `deboer_predict_for_grade` | Prediksi YS/TS/CE/PCM/Tnr/Ar3/Liquidus dari grade + parameter produksi |
| **4. Compliance Check** | `check_chem_compliance` | Cek komposisi vs HR_Chem_Std |
| | `check_mech_compliance` | Cek YS/TS/Impact vs HR_Mech_Std |
| | `full_compliance_report` | Gabungan chem + mech |
| **5. Feasibility Analysis** (sintesis profesional) | `feasibility_analysis` | Bisa-kah Steel Grade X memenuhi Spec Y? Chem + mech (Deboer) + CEQ/PCM + history → verdict PASS/FAIL. Auto-sweep FT/CT/thickness kalau user nggak kasih. |
| | `find_compatible_grades` | Semua grade yang chem-compat untuk satu spec, sorted by riwayat produksi 2021 |
| | `compare_grades` | Bandingkan komposisi + CEQ/PCM + history dua grade berdampingan |
| | `recommend_production_params` | Sweep semua FT × CT × thickness, return kombinasi paling optimal supaya prediksi mech masuk target spec |

### Catatan Modul 5 (Feasibility)

- **Shortname & full name**: `steel_grade` dan `specification` keduanya
  menerima shortname (`A2010`, `SS400`) atau lengkap (`0A2010`,
  `JIS G 3101 SS400`). Resolver: exact > token-exact > prefix > substring.
- **Default parameter**: kalau `thickness_mm` / `ft_code` / `ct_code`
  tidak diisi, app akan **sweep** semua kombinasi (24 FT × 25 CT ×
  default-thickness list) dan tampilkan kombinasi paling optimal.
- **Tabel FT/CT**: hard-coded di `ppd_agent/ft_ct_codes.py` (24 FT codes,
  25 CT codes — pakai tabel target+variance versi user, bukan
  `FT_CT_Design.xlsx`).
- **Verdict**: PASS atau FAIL — tidak ada RISKY.

## Architecture

```
Telegram
    │
    ▼
┌────────────────────────────────────────┐
│  ppd_agent.telegram_bot                │
│  (whitelist, /start /reset /myid)      │
└──────────────┬─────────────────────────┘
               ▼
┌────────────────────────────────────────┐
│  ppd_agent.agent.PPDAgent              │
│  - OpenRouter via OpenAI SDK           │
│  - Tool-calling loop (max 6 iter)      │
│  - System prompt: domain ketat, multi-bahasa │
└──────────────┬─────────────────────────┘
               ▼
┌────────────────────────────────────────┐
│  ppd_agent.tools.{product_design,      │
│                   hrc, deboer,         │
│                   compliance}          │
└──────────────┬─────────────────────────┘
               ▼
┌────────────────────────────────────────┐
│  Parquet datasets                       │
│  ft_ct_design, hr_chem_std,            │
│  hr_elongation_std, hr_mech_std,       │
│  hr_thick_toler, z001,                 │
│  chemical_design, produksi_2021_hrc    │
└────────────────────────────────────────┘
```

## Install (Windows, one-liner)

Open **PowerShell** and paste:

```powershell
iwr -useb https://raw.githubusercontent.com/khadijahumar/ppd-agent/main/install.ps1 | iex
```

The installer will:

1. Verify Python ≥ 3.10 is on PATH.
2. Install [pipx](https://pipx.pypa.io/) if missing and add it to PATH.
3. `pipx install git+https://github.com/khadijahumar/ppd-agent.git` — gives
   you a globally-available `ppd` command.
4. Create `%USERPROFILE%\.ppd\` with `data\{raw,parquet,plots}` folders.

If you don't have Python yet, install it from
[python.org/downloads](https://www.python.org/downloads/windows/) and
**tick "Add python.exe to PATH"** during the installer.

## Setup (after install)

Everything is driven by the `ppd` CLI:

```powershell
ppd init           # interactive wizard: enter OpenRouter key, BotFather token, etc.
ppd prepare-data   # convert .xlsx -> parquet (run after dropping data files)
ppd start          # run the Telegram bot in the foreground
ppd doctor         # diagnose your install (paths, env, deps, data)
ppd config show    # print current .env (secrets masked)
ppd config set KEY VALUE
ppd --help
```

### 1. Run the wizard

```powershell
ppd init
```

It will prompt you for:

- **`OPENROUTER_API_KEY`** — sign up at [openrouter.ai](https://openrouter.ai/),
  create a key at [openrouter.ai/keys](https://openrouter.ai/keys), top up
  $5–10 to start. Default model is `anthropic/claude-sonnet-4` (best for
  tool-calling). Other good options: `openai/gpt-4o`, `openai/gpt-4o-mini`
  (cheaper), `google/gemini-2.0-flash-001`.
- **`PPD_MODEL`** — model name (default: `anthropic/claude-sonnet-4`).
- **`TELEGRAM_BOT_TOKEN`** — chat [@BotFather](https://t.me/BotFather) on
  Telegram, run `/newbot`, follow prompts. Copy the token.
- **`TELEGRAM_ALLOWED_USER_IDS`** — get each user's Telegram ID by chatting
  [@userinfobot](https://t.me/userinfobot). Comma-separate, e.g.
  `123456789,987654321`. Leave empty to block everybody (safe default).

Values are saved to `%USERPROFILE%\.ppd\.env` (file is `chmod 600` on POSIX).

### 2. Place raw Excel files

The raw `.xlsx` data is **not** distributed (sensitive internal + ~68 MB
production file). Drop these 8 files into `%USERPROFILE%\.ppd\data\raw\`:

```
FT_CT_Design.xlsx
HR_Chem_Std.xlsx
HR_Elongation_Std.xlsx
HR_Mech_Std.xlsx
HR_Thick_Toler.xlsx
Z001.xlsx
Chemical_Design.xls
Produksi_2021_HRC.xlsx
```

(Filenames must match exactly.)

### 3. Convert raw Excel → Parquet (run once)

```powershell
ppd prepare-data
```

This creates `%USERPROFILE%\.ppd\data\parquet\*.parquet` (8 files, ~10 MB
total). The production HRC file (~290k rows) takes ~2 minutes the first
time; after that everything loads in <1 second.

### 4. Run the bot

```powershell
ppd start
```

You should see:

```
[INFO] warming up data ...
[INFO] loading produksi_2021_hrc.parquet ...
[INFO]   loaded 290052 rows
[INFO] starting Telegram polling ...
```

Open Telegram, search your bot's username, send `/start`. If your user
ID is in the whitelist, you'll get the welcome message. Send a question
and the bot replies with text + plots.

### Updating

Re-run the installer; pipx will reinstall the latest from GitHub:

```powershell
iwr -useb https://raw.githubusercontent.com/khadijahumar/ppd-agent/main/install.ps1 | iex
```

Or directly:

```powershell
pipx upgrade ppd-agent
```

### Uninstall

```powershell
pipx uninstall ppd-agent
Remove-Item -Recurse -Force $env:USERPROFILE\.ppd   # also remove data + .env
```

## Develop locally (clone + edit)

If you want to hack on the source instead of installing via pipx:

```powershell
git clone https://github.com/khadijahumar/ppd-agent.git
cd ppd-agent
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
# data/raw + data/parquet live next to the package in this mode (auto-detected).
ppd doctor
```

## Example interactions

- **Compliance check**:
  > "Coil ASC111 lulus standar EN 10025 S275JR nggak?"

  Agent calls `full_compliance_report(coil_id="ASC111", specification="EN 10025 S275JR")`,
  returns a pass/fail table per element + per mechanical property.

- **Statistical analysis**:
  > "Histogram YS untuk spec MS EN 10025-2:2011 S275JR+AR di tebal 8-10 mm"

  Agent calls `hrc_histogram(variable="YS", spec_code="MS EN 10025-2:2011 S275JR+AR", thickness_min_mm=8, thickness_max_mm=10)`,
  returns a PNG chart with summary stats.

- **Property prediction**:
  > "Prediksi YS/TS untuk grade 0A1810, tebal 8mm, FT 860, CT 590"

  Agent calls `deboer_predict_for_grade(steel_grade="0A1810", thickness_min_mm=8, thickness_max_mm=8, ct_min_c=590, ct_max_c=590, ft_min_c=860, ft_max_c=860)`.

- **Multi-step**:
  > "Cari steel grade untuk KI-A36 tebal 8mm, terus prediksi propertinya pakai Deboer di FT 860 CT 590"

  Agent calls `lookup_steel_grade` then `deboer_predict_for_grade`.

- **Feasibility — sintesis profesional**:
  > "A2010 bisa untuk SS400?"

  Agent calls `feasibility_analysis(steel_grade="A2010", specification="SS400")`.
  Output: chem compatibility (PASS/FAIL per element), mech feasibility
  (Deboer YS/TS + auto-sweep FT/CT/thickness paling optimal),
  hardenability (CEQ + PCM), riwayat produksi 2021, plus verdict PASS/FAIL.

- **Saran parameter optimal**:
  > "Saran FT/CT untuk A2010 supaya masuk SS400?"

  Agent calls `recommend_production_params(...)`. Sweeps semua kombinasi
  FT × CT × thickness, return top-N kombinasi paling pas dengan target spec.

- **Cari grade kompatibel**:
  > "Spec SS400 cocoknya pakai grade apa aja?"

  Agent calls `find_compatible_grades(specification="JIS G 3101 SS400")`.
  Mengembalikan semua grade yang chem-compat, prioritas ke grade yang
  pernah diproduksi untuk spec ini di 2021.

- **Bandingkan dua grade**:
  > "Bandingkan A2010 sama 0A1810"

  Agent calls `compare_grades(grade_a="A2010", grade_b="0A1810")`.

## Project layout

```
ppd-agent/
├── README.md
├── pyproject.toml
├── .env.example                  # template (.env is gitignored)
├── .gitignore
├── data/
│   ├── raw/                      # original .xlsx files (committed)
│   ├── parquet/                  # generated, gitignored
│   └── plots/                    # generated PNGs, gitignored
├── ppd_agent/
│   ├── config.py                 # env vars
│   ├── parsing.py                # parseToNumber + range parser
│   ├── data_loader.py            # cached parquet loaders
│   ├── prompts.py                # system prompt
│   ├── ft_ct_codes.py            # 24 FT + 25 CT temperature codes
│   ├── format.py                 # plain-text formatters (Telegram-friendly)
│   ├── aliases.py                # shortname → canonical resolver
│   ├── agent.py                  # OpenRouter tool-calling loop
│   ├── telegram_bot.py           # bot handlers
│   └── tools/
│       ├── _types.py             # ToolResult dataclass
│       ├── product_design.py     # Module 1
│       ├── hrc.py                # Module 2
│       ├── deboer.py             # Module 3
│       ├── compliance.py         # Module 4
│       └── feasibility.py        # Module 5 (sintesis profesional)
└── scripts/
    ├── prepare_data.py           # xlsx → parquet
    └── run_bot.py                # entry point
```

## Design notes

- **Skill isolation**: the LLM is NEVER asked to compute numbers. All
  formulas (Deboer, CEQ, PCM, etc.) live in `ppd_agent/tools/deboer.py`
  in deterministic Python.
- **Strict system prompt**: the agent refuses out-of-domain questions and
  is instructed to call tools rather than guess.
- **Multi-language**: instruction `respond in the same language as the user's
  last message` — no language-detection library needed.
- **One conversation per chat**: each Telegram chat gets its own
  `PPDAgent` instance (with its own message history). `/reset` clears it.
- **Plots**: histogram / scatter / heatmap saved as PNG to
  `data/plots/`, sent to Telegram via `bot.send_photo`.
- **Sentinel handling**: source data uses `9.999%` etc. as "no constraint";
  parsing logic clamps these to avoid blowing up downstream formulas.

## Limitations

- Single-machine, polling-mode bot — needs to be running 24/7 if you want
  always-on access.
- Production data is 2021 only; add new years by dropping new xlsx into
  `data/raw/` and extending `scripts/prepare_data.py`.
- Tool calls are sequential within a turn (max 6); for very complex
  multi-step queries the agent may hit the iteration limit.
- ELO compliance lives in a separate standard (HR_Elongation_Std) and is
  not yet wired into `check_mech_compliance` — easy follow-up.

## Development

```bash
pip install -e .[dev]
pytest tests/
ruff check ppd_agent/ scripts/
```
