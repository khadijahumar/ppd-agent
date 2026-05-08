"""Tool-calling agent loop using OpenAI-compatible API (multi-provider)."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import OpenAI

from .config import CONFIG
from .prompts import SYSTEM_PROMPT
from .tools import compliance, deboer, feasibility, hrc, product_design
from .tools._types import as_str, collect_images

log = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 6
_MAX_RETRIES = 3
_RETRY_BACKOFF = [1, 3, 9]


# ---------------------------------------------------------------------------
# tool registry
# ---------------------------------------------------------------------------


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]


def _t(name: str, desc: str, params: dict, fn: Callable[..., Any]) -> ToolDef:
    return ToolDef(name=name, description=desc, parameters=params, fn=fn)


def _string(desc: str = "") -> dict:
    return {"type": "string", "description": desc}


def _number(desc: str = "") -> dict:
    return {"type": "number", "description": desc}


def _bool(desc: str = "") -> dict:
    return {"type": "boolean", "description": desc}


def _array(item_type: str, desc: str = "") -> dict:
    return {"type": "array", "items": {"type": item_type}, "description": desc}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


# Common HRC filter params (reused across many tools).
_HRC_FILTER_PROPS = {
    "spec_code": _string("Spec Code substring (case-insensitive)."),
    "customer": _string("Customer substring (case-insensitive)."),
    "grade": _string("Steel Grade substring."),
    "thickness_min_mm": _number("Minimum TBL_ACT (mm)."),
    "thickness_max_mm": _number("Maximum TBL_ACT (mm)."),
    "date_from": _string("Rolldate >= this (YYYY-MM-DD)."),
    "date_to": _string("Rolldate <= this (YYYY-MM-DD)."),
    "only_finished": _bool("Only include finished coils (Sta Akhir == 1). Default true."),
}


TOOLS: list[ToolDef] = [
    # ----- Module 1: Product Design Lookup -----
    _t(
        "lookup_steel_grade",
        "Cari Steel Grade + HR Spec Code dari specification (substring) dan optional thickness.",
        _obj({
            "specification": _string("Specification standard (e.g. 'KI-A36', 'EN 10025 S275JR')."),
            "thickness_mm": _number("Plate thickness (mm), optional."),
            "limit": {"type": "integer", "description": "Max rows (default 10)."},
        }, required=["specification"]),
        product_design.lookup_steel_grade,
    ),
    _t(
        "lookup_chem_standard",
        "Standar kimia (min/max) per specification dari HR_Chem_Std.",
        _obj({
            "specification": _string("Specification (e.g. 'AS/NZS 3678 - 250')."),
            "limit": {"type": "integer", "description": "Max specifications shown (default 3)."},
        }, required=["specification"]),
        product_design.lookup_chem_standard,
    ),
    _t(
        "lookup_mech_standard",
        "Standar mekanik (TS, YS, Charpy, HIC, DWTT) per specification + thickness.",
        _obj({
            "specification": _string("Specification."),
            "thickness_mm": _number("Plate thickness (mm), optional."),
            "limit": {"type": "integer"},
        }, required=["specification"]),
        product_design.lookup_mech_standard,
    ),
    _t(
        "lookup_elongation_standard",
        "Standar elongation per specification + thickness.",
        _obj({
            "specification": _string(),
            "thickness_mm": _number(),
            "limit": {"type": "integer"},
        }, required=["specification"]),
        product_design.lookup_elongation_standard,
    ),
    _t(
        "lookup_thickness_tolerance",
        "Toleransi tebal per dim_thickness + thickness + width.",
        _obj({
            "dim_thickness": _string("Dim Thickness identifier (e.g. 'HTS G 3101')."),
            "thickness_mm": _number(),
            "width_mm": _number(),
            "limit": {"type": "integer"},
        }, required=["dim_thickness"]),
        product_design.lookup_thickness_tolerance,
    ),
    _t(
        "lookup_ft_ct_design",
        "Rekomendasi Finish Temperature (FT) & Coil Temperature (CT) codes per HR Spec Code + thickness.",
        _obj({
            "hr_spec_code": _string("HR Spec Code (e.g. 'KIA36', 'ABSAH36')."),
            "thickness_mm": _number(),
            "limit": {"type": "integer"},
        }, required=["hr_spec_code"]),
        product_design.lookup_ft_ct_design,
    ),

    # ----- Module 2: HRC Production Analysis -----
    _t(
        "hrc_filter",
        "Filter dataset produksi HRC 2021 (290k coils) dan kembalikan ringkasan + sample.",
        _obj({
            **_HRC_FILTER_PROPS,
            "coil_id": _string("Substring filter on Coil ID."),
            "heat_no": _string("Substring filter on Heat No."),
            "width_min_mm": _number(),
            "width_max_mm": _number(),
            "sample": {"type": "integer", "description": "Number of sample rows shown (default 5)."},
        }),
        hrc.hrc_filter,
    ),
    _t(
        "hrc_statistics",
        "Statistik (n, mean, std, min, p25, median, p75, max) untuk variabel numerik dari subset.",
        _obj({
            **_HRC_FILTER_PROPS,
            "variables": _array("string", f"List variabel numerik. Pilihan: {hrc.NUMERIC_VARS}"),
        }),
        hrc.hrc_statistics,
    ),
    _t(
        "hrc_histogram",
        "Buat histogram PNG untuk satu variabel numerik dari subset terfilter.",
        _obj({
            **_HRC_FILTER_PROPS,
            "variable": _string(f"Variabel numerik. Pilihan: {hrc.NUMERIC_VARS}"),
            "bins": {"type": "integer", "description": "Number of bins (default 40)."},
        }, required=["variable"]),
        hrc.hrc_histogram,
    ),
    _t(
        "hrc_scatter",
        "Buat scatter plot (x vs y) PNG dari subset terfilter, dengan korelasi Pearson.",
        _obj({
            **_HRC_FILTER_PROPS,
            "x": _string(f"X variable. Pilihan: {hrc.NUMERIC_VARS}"),
            "y": _string(f"Y variable. Pilihan: {hrc.NUMERIC_VARS}"),
            "max_points": {"type": "integer", "description": "Subsample size (default 5000)."},
        }, required=["x", "y"]),
        hrc.hrc_scatter,
    ),
    _t(
        "hrc_correlation_heatmap",
        "Heatmap korelasi antar beberapa variabel pada subset terfilter.",
        _obj({
            **_HRC_FILTER_PROPS,
            "variables": _array("string", "Variabel-variabel yang mau dihitung korelasinya."),
        }),
        hrc.hrc_correlation_heatmap,
    ),
    _t(
        "hrc_lookup_coil",
        "Detail satu coil (dimensions, mech, kimia, FT/CT, defect reasons).",
        _obj({"coil_id": _string("Coil ID exact or substring.")}, required=["coil_id"]),
        hrc.hrc_lookup_coil,
    ),

    # ----- Module 3: Deboer -----
    _t(
        "deboer_predict_for_grade",
        "Prediksi YS/TS/CE/PCM/Tnr/Ar3/Liquidus untuk satu Steel Grade + range produksi.",
        _obj({
            "steel_grade": _string("Steel Grade (e.g. '0A1810')."),
            "thickness_min_mm": _number(),
            "thickness_max_mm": _number(),
            "ct_min_c": _number("CT minimum (°C)."),
            "ct_max_c": _number("CT maximum (°C)."),
            "ft_min_c": _number("FT minimum (°C)."),
            "ft_max_c": _number("FT maximum (°C)."),
        }, required=["steel_grade", "thickness_min_mm", "thickness_max_mm",
                     "ct_min_c", "ct_max_c", "ft_min_c", "ft_max_c"]),
        deboer.deboer_predict_for_grade,
    ),

    # ----- Module 4: Compliance -----
    _t(
        "check_chem_compliance",
        "Cek kepatuhan komposisi kimia satu coil terhadap standar (HR_Chem_Std).",
        _obj({
            "coil_id": _string("Coil ID exact."),
            "specification": _string("Specification override; default = coil's own Spec Code."),
        }, required=["coil_id"]),
        compliance.check_chem_compliance,
    ),
    _t(
        "check_mech_compliance",
        "Cek kepatuhan properti mekanik (YS, TS, Impact) satu coil terhadap standar (HR_Mech_Std).",
        _obj({
            "coil_id": _string("Coil ID exact."),
            "specification": _string(),
        }, required=["coil_id"]),
        compliance.check_mech_compliance,
    ),
    _t(
        "full_compliance_report",
        "Laporan lengkap chem + mech compliance untuk satu coil.",
        _obj({
            "coil_id": _string("Coil ID exact."),
            "specification": _string(),
        }, required=["coil_id"]),
        compliance.full_compliance_report,
    ),

    # ----- Module 5: Feasibility Analysis -----
    _t(
        "feasibility_analysis",
        "Analisis profesional: bisakah Steel Grade X memenuhi Specification Y? "
        "Menggabungkan Chemical_Design, HR_Chem_Std, HR_Mech_Std, prediksi Deboer, "
        "dan history produksi 2021. Output: chem compatibility + mech feasibility "
        "+ hardenability/weldability (CEQ, PCM) + verdict PASS/FAIL.",
        _obj({
            "steel_grade": _string("Steel Grade (lengkap atau shortname, e.g. 'A2010' / '0A2010')."),
            "specification": _string("Specification (lengkap atau shortname, e.g. 'SS400' / 'JIS G 3101 SS400')."),
            "thickness_mm": _number("Plate thickness (mm). Optional — kalau dilewati, app sweep beberapa thickness."),
            "ft_code": _string("FT code (A–Z, skip J/O). Optional."),
            "ct_code": _string("CT code (A–Z, skip J). Optional."),
        }, required=["steel_grade", "specification"]),
        feasibility.feasibility_analysis,
    ),
    _t(
        "find_compatible_grades",
        "Cari semua Steel Grade yang chemical design-nya cocok untuk Specification target. "
        "Grade yang sudah pernah diproduksi untuk spec ini ditampilkan duluan.",
        _obj({
            "specification": _string("Specification (lengkap atau shortname)."),
            "top_n": {"type": "integer", "description": "Max grade ditampilkan (default 10)."},
        }, required=["specification"]),
        feasibility.find_compatible_grades,
    ),
    _t(
        "compare_grades",
        "Bandingkan komposisi kimia + CEQ/PCM dua Steel Grade berdampingan, plus jumlah "
        "produksi 2021 masing-masing.",
        _obj({
            "grade_a": _string("Steel Grade pertama."),
            "grade_b": _string("Steel Grade kedua."),
        }, required=["grade_a", "grade_b"]),
        feasibility.compare_grades,
    ),
    _t(
        "recommend_production_params",
        "Sweep semua kombinasi FT × CT × thickness untuk Steel Grade tertentu, lalu return "
        "kombinasi paling optimal (paling masuk standar) untuk target specification. Dipakai "
        "kalau user mau saran parameter rolling untuk grade-spec tertentu.",
        _obj({
            "steel_grade": _string("Steel Grade (lengkap atau shortname)."),
            "target_specification": _string("Target Specification."),
            "thickness_mm": _number("Plate thickness (mm). Optional — kalau dilewati, sweep default thickness."),
            "top_n": {"type": "integer", "description": "Berapa kombinasi terbaik dikembalikan (default 5)."},
        }, required=["steel_grade", "target_specification"]),
        feasibility.recommend_production_params,
    ),
]


_TOOL_INDEX: dict[str, ToolDef] = {t.name: t for t in TOOLS}


def openai_tool_specs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in TOOLS
    ]


# ---------------------------------------------------------------------------
# agent loop
# ---------------------------------------------------------------------------


@dataclass
class AgentTurn:
    """Result of a single user turn."""
    text: str
    image_paths: list[Path] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    error: str | None = None


class PPDAgent:
    """Stateful conversation agent (one instance per Telegram chat)."""

    def __init__(self, model: str | None = None) -> None:
        api_key = CONFIG.effective_api_key
        if not api_key:
            raise RuntimeError(
                "No LLM API key configured. Set OPENROUTER_API_KEY (or "
                "LLM_PROVIDER + matching key) in .env. See .env.example."
            )
        headers: dict[str, str] = {}
        if CONFIG.llm_provider == "openrouter":
            headers["HTTP-Referer"] = CONFIG.site_url or "https://github.com/zandyumar10-afk/ppd-agent"
            headers["X-Title"] = CONFIG.app_name
        self.client = OpenAI(
            base_url=CONFIG.llm_base_url,
            api_key=api_key,
            default_headers=headers or None,
        )
        self.model = model or CONFIG.model
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # -- context window management ------------------------------------------

    def _trim_context(self) -> None:
        """Keep conversation within max_context_messages.

        Preserves the system prompt (index 0) and the most recent messages.
        Old messages are summarised into a single compact message so the LLM
        retains some context of earlier turns.
        """
        limit = CONFIG.max_context_messages
        if len(self.messages) <= limit:
            return

        keep = limit - 2  # room for system + summary
        old = self.messages[1:-keep]
        recent = self.messages[-keep:]

        summary_parts: list[str] = []
        for m in old:
            role = m.get("role", "")
            content = (m.get("content") or "")[:200]
            if role == "user":
                summary_parts.append(f"User: {content}")
            elif role == "assistant" and content:
                summary_parts.append(f"Assistant: {content}")

        summary_text = (
            "[Earlier conversation trimmed for context limit]\n"
            + "\n".join(summary_parts[-10:])
        )
        self.messages = (
            [self.messages[0]]
            + [{"role": "system", "content": summary_text}]
            + recent
        )
        log.info("trimmed context: %d old msgs → summary + %d recent", len(old), len(recent))

    # -- tool execution -----------------------------------------------------

    def _execute_tool(self, name: str, args_json: str) -> tuple[str, list[Path]]:
        if name not in _TOOL_INDEX:
            return (f"ERROR: tool '{name}' tidak terdaftar.", [])
        try:
            args = json.loads(args_json) if args_json else {}
        except json.JSONDecodeError as exc:
            return (f"ERROR parsing args: {exc}", [])
        try:
            result = _TOOL_INDEX[name].fn(**args)
        except TypeError as exc:
            return (f"ERROR memanggil tool {name}: {exc}", [])
        except Exception as exc:
            log.exception("tool %s raised", name)
            return (f"ERROR di tool {name}: {exc}", [])
        return (as_str(result), collect_images(result))

    # -- LLM call with retry ------------------------------------------------

    def _llm_call(self, messages: list[dict]) -> Any:
        """Call the LLM with exponential-backoff retry."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=openai_tool_specs(),
                    tool_choice="auto",
                    temperature=0.1,
                )
            except Exception as exc:
                last_exc = exc
                wait = _RETRY_BACKOFF[attempt] if attempt < len(_RETRY_BACKOFF) else 9
                log.warning("LLM call attempt %d failed: %s — retrying in %ds", attempt + 1, exc, wait)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    # -- main chat loop -----------------------------------------------------

    def chat(self, user_message: str) -> AgentTurn:
        self.messages.append({"role": "user", "content": user_message})
        self._trim_context()
        collected_images: list[Path] = []
        called_tools: list[str] = []

        for it in range(MAX_TOOL_ITERATIONS):
            try:
                resp = self._llm_call(self.messages)
            except Exception as exc:
                log.exception("LLM call failed after retries")
                return AgentTurn(text="", error=f"LLM call failed: {exc}")

            choice = resp.choices[0]
            msg = choice.message
            tool_calls = msg.tool_calls or []

            assistant_msg: dict = {"role": "assistant", "content": msg.content or ""}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                    for tc in tool_calls
                ]
            self.messages.append(assistant_msg)

            if not tool_calls:
                return AgentTurn(
                    text=msg.content or "",
                    image_paths=collected_images,
                    tool_calls=called_tools,
                )

            for tc in tool_calls:
                tool_name = tc.function.name
                tool_args = tc.function.arguments or "{}"
                called_tools.append(tool_name)
                log.info("tool[%d] %s args=%s", it, tool_name, tool_args[:200])
                text, images = self._execute_tool(tool_name, tool_args)
                collected_images.extend(images)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": text,
                })

        return AgentTurn(
            text="(maaf, agent mencapai batas iterasi tool tanpa menghasilkan jawaban final.)",
            image_paths=collected_images,
            tool_calls=called_tools,
            error="max_iterations_reached",
        )
