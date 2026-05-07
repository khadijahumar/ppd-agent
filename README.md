# PPD Assistant — AI Agent for Steel Manufacturing

A focused, **skill-limited** AI agent for the Product Planning & Design (PPD)
domain in steel manufacturing. Built specifically because general-purpose
agents (Hermes, QwenPaw, etc.) are too broad and lose focus on domain-specific
questions.

The agent does **only** what it has tools for — there are 16 deterministic
Python tools across 4 modules. The LLM (via OpenRouter) only decides which
tool to call and how to summarise the result. All numerical computation
(filtering, statistics, Deboer formulas, compliance checks) happens in
Python, never in the LLM. This guarantees correctness on the things that
matter.

## Skills (16 tools, 4 modules)

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

## Setup

### 1. Install Python (>=3.10) & dependencies

```bash
git clone https://github.com/khadijahumar/ppd-agent.git
cd ppd-agent
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

### 2. Place raw Excel files

The raw `.xlsx` data is **not** committed to this repo (sensitive internal
data + the production file is ~68 MB). Drop the following files into
`data/raw/` before continuing:

```
data/raw/
├── FT_CT_Design.xlsx
├── HR_Chem_Std.xlsx
├── HR_Elongation_Std.xlsx
├── HR_Mech_Std.xlsx
├── HR_Thick_Toler.xlsx
├── Z001.xlsx
├── Chemical_Design.xls
└── Produksi_2021_HRC.xlsx
```

(Filenames must match exactly; see `scripts/prepare_data.py` for the mapping.)

### 3. Convert raw Excel → Parquet (run once)

```bash
python scripts/prepare_data.py
```

This creates `data/parquet/*.parquet` (8 files, ~10 MB total). The
production HRC file (~290k rows) takes ~2 minutes the first time; after
that everything loads in <1 second.

### 4. Configure secrets

```bash
cp .env.example .env
```

Edit `.env`:

- **`OPENROUTER_API_KEY`** — sign up at [openrouter.ai](https://openrouter.ai/),
  create a key at [openrouter.ai/keys](https://openrouter.ai/keys), top up
  $5–10 to start. Default model is `anthropic/claude-sonnet-4` (best for
  tool-calling). Other good options: `openai/gpt-4o`, `openai/gpt-4o-mini`
  (cheaper).
- **`TELEGRAM_BOT_TOKEN`** — chat [@BotFather](https://t.me/BotFather) on
  Telegram, run `/newbot`, follow prompts. Copy the token.
- **`TELEGRAM_ALLOWED_USER_IDS`** — get each user's Telegram ID by chatting
  [@userinfobot](https://t.me/userinfobot). Comma-separate, e.g.
  `TELEGRAM_ALLOWED_USER_IDS=123456789,987654321`.

### 5. Run the bot

```bash
python scripts/run_bot.py
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
│   ├── agent.py                  # OpenRouter tool-calling loop
│   ├── telegram_bot.py           # bot handlers
│   └── tools/
│       ├── _types.py             # ToolResult dataclass
│       ├── product_design.py     # Module 1
│       ├── hrc.py                # Module 2
│       ├── deboer.py             # Module 3
│       └── compliance.py         # Module 4
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
