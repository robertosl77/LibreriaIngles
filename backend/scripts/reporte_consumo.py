"""Reporte de consumo de IA para medir la eficiencia (T-168) sin escribir SQL.

Uso (desde la carpeta backend, con el venv activo):

    python scripts/reporte_consumo.py                          # todo el historial
    python scripts/reporte_consumo.py --desde 2026-10-06       # desde una fecha (hora local)
    python scripts/reporte_consumo.py --desde 2026-10-06 --hasta 2026-10-07 --email vos@mail.com
    python scripts/reporte_consumo.py --csv consumo.csv        # además, detalle por llamada en CSV

Secciones:
  1. Por día: llamadas, clases generadas, tokens totales y tokens por clase.
  2. Por operación y modelo: promedios de entrada / pensamiento / salida / total y caché.
  3. Por clase: cuánto costó cada clase completa (generar + corregir + audio).
  4. Desperdicio: intentos fallidos y clases/exámenes que no se generaron.

No muestra prompts, respuestas ni API keys. Los health checks ("Probar") no se cuentan.
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.accounts.models import Account  # noqa: E402
from app.ai.models import AIUsageEvent  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402

TZ = ZoneInfo(settings.display_timezone)
OPERATIONS = {
    "generate_class": "Generar clase",
    "generate_exam": "Generar examen",
    "evaluate_answer": "Corregir",
    "evaluate_batch": "Corregir en lote",
    "transcribe_audio": "Audio",
    "campaign_assist": "Asistente campañas",
    "campaign_policy_assist": "Asistente políticas",
}


def _local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(TZ)


def _bound(value: str | None, end: bool) -> datetime | None:
    if not value:
        return None
    day = datetime.strptime(value, "%Y-%m-%d").date()
    if end:
        day += timedelta(days=1)
    return datetime.combine(day, time.min, tzinfo=TZ).astimezone(ZoneInfo("UTC"))


def _n(v) -> int:
    return int(v or 0)


def _avg(values: list[int]) -> str:
    return f"{sum(values) / len(values):,.0f}" if values else "-"


def _table(headers: list[str], rows: list[list], align_left: int = 1) -> None:
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(headers)]
    fmt = "  ".join(
        f"{{:<{w}}}" if i < align_left else f"{{:>{w}}}" for i, w in enumerate(widths)
    )
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt.format(*[str(x) for x in r]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--desde")
    parser.add_argument("--hasta")
    parser.add_argument("--email")
    parser.add_argument("--csv")
    args = parser.parse_args()

    with SessionLocal() as db:
        query = select(AIUsageEvent).where(AIUsageEvent.operation != "health_check")
        if (since := _bound(args.desde, end=False)) is not None:
            query = query.where(AIUsageEvent.created_at >= since)
        if (until := _bound(args.hasta, end=True)) is not None:
            query = query.where(AIUsageEvent.created_at < until)
        if args.email:
            account = db.scalar(select(Account).where(Account.email == args.email.strip().lower()))
            if account is None:
                print(f"No existe la cuenta {args.email}.")
                return 1
            query = query.where(AIUsageEvent.account_id == account.id)
        events = db.scalars(query.order_by(AIUsageEvent.created_at)).all()

    if not events:
        print("No hay consumo en ese período.")
        return 0
    print(f"Consumo de IA · {len(events)} llamadas · horario {settings.display_timezone}\n")

    # 1. Por día
    days: dict[str, dict] = defaultdict(lambda: {"calls": 0, "ok": 0, "tokens": 0, "classes": set()})
    for e in events:
        d = days[_local(e.created_at).strftime("%Y-%m-%d")]
        d["calls"] += 1
        d["ok"] += 1 if e.success else 0
        d["tokens"] += _n(e.total_tokens)
        if e.subject_type == "CLASS" and e.subject_id:
            d["classes"].add(e.subject_id)
    print("1. POR DÍA")
    _table(
        ["día", "llamadas", "ok", "clases", "tokens", "tokens/clase"],
        [
            [day, d["calls"], d["ok"], len(d["classes"]), f"{d['tokens']:,}",
             f"{d['tokens'] / len(d['classes']):,.0f}" if d["classes"] else "-"]
            for day, d in sorted(days.items())
        ],
    )

    # 2. Por operación y modelo (solo llamadas exitosas, que son las que tienen tokens)
    groups: dict[tuple, dict] = defaultdict(lambda: defaultdict(list))
    for e in events:
        key = (OPERATIONS.get(e.operation, e.operation), e.model or "-")
        g = groups[key]
        g["count"].append(1)
        if not e.success:
            g["fail"].append(1)
            continue
        g["in"].append(_n(e.input_tokens))
        g["think"].append(_n(e.reasoning_tokens))
        g["out"].append(_n(e.output_tokens))
        g["total"].append(_n(e.total_tokens))
        cached = ((e.diagnostic_snapshot or {}).get("details") or {}).get("cachedInputTokens")
        if cached is not None:
            g["cached"].append(_n(cached))
    print("\n2. POR OPERACIÓN Y MODELO (promedio por llamada exitosa)")
    _table(
        ["operación", "modelo", "llamadas", "fallidas", "entrada", "pensam.", "salida", "total", "caché"],
        [
            [op, model, len(g["count"]), len(g["fail"]), _avg(g["in"]), _avg(g["think"]),
             _avg(g["out"]), _avg(g["total"]), _avg(g["cached"])]
            for (op, model), g in sorted(groups.items())
        ],
        align_left=2,
    )

    # 3. Por clase completa
    classes: dict[int, dict] = defaultdict(lambda: defaultdict(int))
    for e in events:
        if e.subject_type != "CLASS" or not e.subject_id:
            continue
        c = classes[e.subject_id]
        c["day"] = c["day"] or _local(e.created_at).strftime("%d/%m %H:%M")
        part = "gen" if e.operation == "generate_class" else "audio" if e.operation == "transcribe_audio" else "corr"
        c[part] += _n(e.total_tokens)
        c["total"] += _n(e.total_tokens)
        c["calls"] += 1
    if classes:
        print("\n3. POR CLASE (generar + corregir + audio)")
        _table(
            ["clase", "fecha", "llamadas", "generar", "corregir", "audio", "total"],
            [
                [f"#{cid}", c["day"], c["calls"], f"{c['gen']:,}", f"{c['corr']:,}", f"{c['audio']:,}", f"{c['total']:,}"]
                for cid, c in sorted(classes.items())
            ],
        )
        totals = [c["total"] for c in classes.values()]
        print(f"   promedio por clase: {sum(totals) / len(totals):,.0f} tokens · {len(totals)} clases")

    # 4. Desperdicio
    failed = [e for e in events if not e.success]
    not_generated = {e.execution_id for e in events if e.subject_type in ("CLASS_NOT_GENERATED", "EXAM_NOT_GENERATED")}
    wasted = sum(_n(e.total_tokens) for e in events if e.subject_type in ("CLASS_NOT_GENERATED", "EXAM_NOT_GENERATED"))
    by_code: dict[str, int] = defaultdict(int)
    for e in failed:
        by_code[e.error_code or "-"] += 1
    print("\n4. DESPERDICIO")
    codes = ", ".join(f"{k}: {v}" for k, v in sorted(by_code.items()))
    print(f"   llamadas fallidas: {len(failed)}" + (f" · {codes}" if codes else ""))
    print(f"   clases/exámenes que no se generaron: {len(not_generated)} · tokens gastados en ellos: {wasted:,}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["fecha_local", "operacion", "proveedor", "modelo", "ok", "error", "referencia",
                             "entrada", "pensamiento", "salida", "total"])
            for e in events:
                writer.writerow([_local(e.created_at).strftime("%Y-%m-%d %H:%M:%S"), e.operation, e.provider,
                                 e.model, e.success, e.error_code, e.subject_label, e.input_tokens,
                                 e.reasoning_tokens, e.output_tokens, e.total_tokens])
        print(f"\nDetalle por llamada guardado en {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
