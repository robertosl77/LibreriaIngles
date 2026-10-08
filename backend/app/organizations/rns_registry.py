"""Cache local del Registro Nacional de Sociedades (RNS).

Fuente oficial: Portal de Datos Abiertos de Justicia Argentina.
El sync descarga el ZIP mensual completo y construye un índice SQLite por CUIT.
No se versiona la base generada.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import sqlite3
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

CKAN_PACKAGE_URL = (
    "https://datos.jus.gob.ar/api/3/action/package_show"
    "?id=registro-nacional-de-sociedades"
)
RESOURCE_NAME = re.compile(r"^Registro Nacional de Sociedades - (\d{4})$")


@dataclass(frozen=True)
class RegistryCompany:
    cuit: str
    legal_name: str
    legal_entity_type: str | None
    contract_date: str | None
    updated_at: str | None
    registry_number: str | None
    fiscal_address: str | None
    legal_address: str | None
    fiscal_province: str | None
    legal_province: str | None
    activity_code: str | None
    activity_description: str | None
    activity_state: str | None
    source_updated_at: str | None


def _request_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "LibreriaIngles/0.1 organization-registry-sync"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _latest_full_resource() -> dict:
    payload = _request_json(CKAN_PACKAGE_URL)
    if not payload.get("success"):
        raise RuntimeError("El catálogo de Datos Justicia no respondió correctamente.")

    candidates: list[tuple[int, dict]] = []
    for resource in payload["result"].get("resources", []):
        name = str(resource.get("name") or "").strip()
        match = RESOURCE_NAME.fullmatch(name)
        if not match:
            continue
        if str(resource.get("format") or "").upper() != "ZIP":
            continue
        candidates.append((int(match.group(1)), resource))

    if not candidates:
        raise RuntimeError("No se encontró un ZIP anual del Registro Nacional de Sociedades.")

    return max(candidates, key=lambda item: item[0])[1]


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "LibreriaIngles/0.1 organization-registry-sync"},
    )
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 1024)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: str | None) -> int:
    text = _clean(value)
    if text is None:
        return 999
    try:
        return int(float(text))
    except ValueError:
        return 999


def _address(row: dict[str, str], prefix: str) -> str | None:
    street = _clean(row.get(f"{prefix}_calle"))
    number = _clean(row.get(f"{prefix}_numero"))
    floor = _clean(row.get(f"{prefix}_piso"))
    department = _clean(row.get(f"{prefix}_departamento"))
    locality = _clean(row.get(f"{prefix}_localidad"))
    province = _clean(row.get(f"{prefix}_provincia"))
    postal = _clean(row.get(f"{prefix}_cp"))

    line = " ".join(part for part in (street, number) if part)
    extra = " ".join(
        part
        for part in (
            f"Piso {floor}" if floor else None,
            f"Dpto. {department}" if department else None,
        )
        if part
    )
    place = ", ".join(part for part in (locality, province) if part)
    chunks = [part for part in (line, extra, place, f"CP {postal}" if postal else None) if part]
    return " · ".join(chunks) or None


def registry_available(path: Path | None = None) -> bool:
    db_path = path or settings.resolved_organization_registry_path
    if not db_path.exists() or db_path.stat().st_size == 0:
        return False
    try:
        with sqlite3.connect(db_path) as db:
            row = db.execute(
                "SELECT value FROM metadata WHERE key = 'source'"
            ).fetchone()
            return bool(row and row[0] == "RNS_OPEN_DATA")
    except (sqlite3.DatabaseError, OSError):
        return False


def lookup_company(cuit: str, path: Path | None = None) -> RegistryCompany | None:
    db_path = path or settings.resolved_organization_registry_path
    if not registry_available(db_path):
        return None

    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            """
            SELECT c.*, m.value AS source_updated_at
            FROM companies c
            LEFT JOIN metadata m ON m.key = 'source_updated_at'
            WHERE c.cuit = ?
            """,
            (cuit,),
        ).fetchone()

    if row is None:
        return None

    return RegistryCompany(
        cuit=row["cuit"],
        legal_name=row["legal_name"],
        legal_entity_type=row["legal_entity_type"],
        contract_date=row["contract_date"],
        updated_at=row["updated_at"],
        registry_number=row["registry_number"],
        fiscal_address=row["fiscal_address"],
        legal_address=row["legal_address"],
        fiscal_province=row["fiscal_province"],
        legal_province=row["legal_province"],
        activity_code=row["activity_code"],
        activity_description=row["activity_description"],
        activity_state=row["activity_state"],
        source_updated_at=row["source_updated_at"],
    )


def sync_registry(destination: Path | None = None) -> dict[str, object]:
    destination = destination or settings.resolved_organization_registry_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    resource = _latest_full_resource()
    url = str(resource.get("url") or "").strip()
    if not url:
        raise RuntimeError("El recurso RNS no contiene URL de descarga.")

    with tempfile.TemporaryDirectory(prefix="libreria-rns-") as tmp:
        tmp_dir = Path(tmp)
        zip_path = tmp_dir / "rns.zip"
        db_path = tmp_dir / "rns_registry.db"

        print(f"Descargando RNS: {resource.get('name')}...")
        _download(url, zip_path)

        with zipfile.ZipFile(zip_path) as archive:
            csv_names = [
                name for name in archive.namelist()
                if name.lower().endswith(".csv") and not name.endswith("/")
            ]
            if not csv_names:
                raise RuntimeError("El ZIP del RNS no contiene un CSV.")
            csv_name = max(csv_names, key=lambda name: archive.getinfo(name).file_size)

            db = sqlite3.connect(db_path)
            try:
                db.execute("PRAGMA journal_mode=OFF")
                db.execute("PRAGMA synchronous=OFF")
                db.execute("PRAGMA temp_store=MEMORY")
                db.execute(
                    """
                    CREATE TABLE companies (
                        cuit TEXT PRIMARY KEY,
                        legal_name TEXT NOT NULL,
                        legal_entity_type TEXT,
                        contract_date TEXT,
                        updated_at TEXT,
                        registry_number TEXT,
                        fiscal_address TEXT,
                        legal_address TEXT,
                        fiscal_province TEXT,
                        legal_province TEXT,
                        activity_code TEXT,
                        activity_description TEXT,
                        activity_state TEXT,
                        activity_order INTEGER,
                        activity_rank INTEGER NOT NULL
                    )
                    """
                )
                db.execute(
                    "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )

                upsert = """
                    INSERT INTO companies (
                        cuit, legal_name, legal_entity_type, contract_date, updated_at,
                        registry_number, fiscal_address, legal_address,
                        fiscal_province, legal_province,
                        activity_code, activity_description, activity_state,
                        activity_order, activity_rank
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cuit) DO UPDATE SET
                        legal_name = excluded.legal_name,
                        legal_entity_type = COALESCE(excluded.legal_entity_type, companies.legal_entity_type),
                        contract_date = COALESCE(excluded.contract_date, companies.contract_date),
                        updated_at = COALESCE(excluded.updated_at, companies.updated_at),
                        registry_number = COALESCE(excluded.registry_number, companies.registry_number),
                        fiscal_address = COALESCE(excluded.fiscal_address, companies.fiscal_address),
                        legal_address = COALESCE(excluded.legal_address, companies.legal_address),
                        fiscal_province = COALESCE(excluded.fiscal_province, companies.fiscal_province),
                        legal_province = COALESCE(excluded.legal_province, companies.legal_province),
                        activity_code = CASE
                            WHEN excluded.activity_rank < companies.activity_rank
                            THEN excluded.activity_code ELSE companies.activity_code END,
                        activity_description = CASE
                            WHEN excluded.activity_rank < companies.activity_rank
                            THEN excluded.activity_description ELSE companies.activity_description END,
                        activity_state = CASE
                            WHEN excluded.activity_rank < companies.activity_rank
                            THEN excluded.activity_state ELSE companies.activity_state END,
                        activity_order = MIN(excluded.activity_order, companies.activity_order),
                        activity_rank = MIN(excluded.activity_rank, companies.activity_rank)
                """

                rows: list[tuple] = []
                processed = 0
                with archive.open(csv_name) as raw, io.TextIOWrapper(
                    raw, encoding="utf-8-sig", newline=""
                ) as text:
                    reader = csv.DictReader(text)
                    for source in reader:
                        cuit = "".join(ch for ch in str(source.get("cuit") or "") if ch.isdigit())
                        legal_name = _clean(source.get("razon_social"))
                        if len(cuit) != 11 or not legal_name:
                            continue

                        order = _number(source.get("actividad_orden"))
                        state = (_clean(source.get("actividad_estado")) or "").upper()
                        rank = (0 if state == "AC" else 1000) + order

                        rows.append(
                            (
                                cuit,
                                legal_name,
                                _clean(source.get("tipo_societario")),
                                _clean(source.get("fecha_hora_contrato_social")),
                                _clean(source.get("fecha_hora_actualizacion")),
                                _clean(source.get("numero_inscripcion")),
                                _address(source, "dom_fiscal"),
                                _address(source, "dom_legal"),
                                _clean(source.get("dom_fiscal_provincia")),
                                _clean(source.get("dom_legal_provincia")),
                                _clean(source.get("actividad_codigo")),
                                _clean(source.get("actividad_descripcion")),
                                state or None,
                                order,
                                rank,
                            )
                        )
                        processed += 1
                        if len(rows) >= 5000:
                            db.executemany(upsert, rows)
                            rows.clear()
                        if processed % 100000 == 0:
                            print(f"Procesados {processed:,} registros...")

                if rows:
                    db.executemany(upsert, rows)

                now = datetime.now(timezone.utc).isoformat()
                source_updated = (
                    resource.get("last_modified")
                    or resource.get("metadata_modified")
                    or resource.get("created")
                    or ""
                )
                metadata = {
                    "source": "RNS_OPEN_DATA",
                    "source_name": str(resource.get("name") or ""),
                    "source_url": url,
                    "source_updated_at": str(source_updated),
                    "synced_at": now,
                }
                db.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    metadata.items(),
                )
                db.commit()
                companies = db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
            finally:
                db.close()

        shutil.copy2(db_path, destination)

    return {
        "path": str(destination),
        "companies": companies,
        "source": resource.get("name"),
        "sourceUpdatedAt": source_updated,
    }


def main() -> None:
    result = sync_registry()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
