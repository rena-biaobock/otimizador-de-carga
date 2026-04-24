import os
from typing import Union

import pandas as pd

DataInput = Union[pd.DataFrame, list[dict]]


def _coerce_to_df(data: DataInput, label: str = "data") -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data.copy()
    if isinstance(data, list):
        return pd.DataFrame(data)
    raise TypeError(f"{label} must be a DataFrame or list of dicts")


def _resolve_col(df: pd.DataFrame, col: str) -> str:
    """Return the actual column name, resolving case-insensitively if needed."""
    if col in df.columns:
        return col
    lower_map = {c.lower(): c for c in df.columns}
    if col.lower() in lower_map:
        return lower_map[col.lower()]
    raise KeyError(f"Column '{col}' not found (available: {list(df.columns)})")


def _ffd_assign(
    indices: list,
    weights: dict,
    capacity: float,
    start_id: int = 1,
) -> tuple[dict, int]:
    """First-Fit Decreasing bin assignment.

    Returns (assignment, next_start_id) where assignment maps index → load_id.
    Items with weight <= 0 are assigned load_id 0.
    """
    loads: list[dict] = []
    assignment: dict[int, int] = {}
    next_id = start_id

    for i in indices:
        w = weights[i]
        if w <= 0:
            assignment[i] = 0
            continue
        for load in loads:
            if load["remaining"] >= w:
                load["remaining"] -= w
                assignment[i] = load["id"]
                break
        else:
            loads.append({"id": next_id, "remaining": capacity - w})
            assignment[i] = next_id
            next_id += 1

    return assignment, next_id


def read_estoque_files(
    estoque_exp_path: str,
    estoque_pce_path: str,
    file_format: str = "csv",
) -> dict[str, pd.DataFrame]:
    """Read estoque_exp and estoque_pce files (CSV, JSON, or XLSX)."""
    if not os.path.exists(estoque_exp_path):
        raise FileNotFoundError(f"estoque_exp file not found: {estoque_exp_path}")
    if not os.path.exists(estoque_pce_path):
        raise FileNotFoundError(f"estoque_pce file not found: {estoque_pce_path}")

    fmt = file_format.lower()
    if fmt not in {"csv", "json", "xlsx"}:
        raise ValueError("Unsupported file_format: choose 'csv', 'json' or 'xlsx'")

    readers = {
        "csv": lambda p: pd.read_csv(p, dtype=str).fillna(""),
        "xlsx": lambda p: pd.read_excel(p, dtype=str).fillna(""),
        "json": lambda p: pd.read_json(p, dtype=False),
    }
    read = readers[fmt]
    return {"estoque_exp": read(estoque_exp_path), "estoque_pce": read(estoque_pce_path)}


def merge_estoque_by_progressivo(
    estoque_exp: DataInput,
    estoque_pce: DataInput,
    key: str = "progressivo",
) -> list[dict]:
    """Merge two inventory sources by key, with estoque_exp taking priority."""
    def to_indexed(data: DataInput) -> pd.DataFrame:
        df = _coerce_to_df(data, "estoque")
        actual_key = _resolve_col(df, key)
        if actual_key != key:
            df = df.rename(columns={actual_key: key})
        return df.astype({key: str}).set_index(key, drop=False)

    merged = to_indexed(estoque_exp).combine_first(to_indexed(estoque_pce))
    return merged.reset_index(drop=True).to_dict(orient="records")


def pack_loads_by_weight(
    df: DataInput,
    weight_col: str = "peso",
    capacity_kg: float = 27000,
    client_col: str | None = None,
    date_col: str | None = None,
) -> pd.DataFrame:
    """Pack items into loads using First-Fit Decreasing by weight.

    Args:
        df: Source data with weight values.
        weight_col: Column storing weight in kg.
        capacity_kg: Maximum load capacity in kg.
        client_col: If set, each client gets independent load numbering.
        date_col: If set, older items are packed before heavier ones.

    Returns:
        Input columns plus load_id, load_total_weight, load_occupancy.
        Items with weight <= 0 receive load_id 0 and occupancy 0.
    """
    df = _coerce_to_df(df)
    weight_col = _resolve_col(df, weight_col)

    df["__weight"] = pd.to_numeric(df[weight_col], errors="coerce").fillna(0)
    df["__date"] = (
        pd.to_datetime(df[date_col], errors="coerce")
        if date_col and date_col in df.columns
        else pd.NaT
    )

    weights = df["__weight"].to_dict()
    all_assignments: dict = {}
    next_id = 1

    groups = (
        df.groupby(client_col, dropna=False, sort=False).groups
        if client_col and client_col in df.columns
        else {"_all": df.index}
    )

    for group_indices in groups.values():
        sorted_idx = (
            df.loc[group_indices]
            .sort_values(["__date", "__weight"], ascending=[True, False])
            .index.tolist()
        )
        assignment, next_id = _ffd_assign(sorted_idx, weights, capacity_kg, next_id)
        all_assignments.update(assignment)

    df["load_id"] = pd.Series(all_assignments)
    active = df["load_id"] != 0
    load_totals = df[active].groupby("load_id")["__weight"].sum()
    df["load_total_weight"] = df["load_id"].map(load_totals).fillna(0)
    df["load_occupancy"] = (df["load_total_weight"] / capacity_kg).clip(0, 1)
    df.loc[~active, "load_occupancy"] = 0.0

    return df.drop(columns=["__weight", "__date"])


def save_packed_loads(df: pd.DataFrame, output_path: str, index: bool = False) -> None:
    """Save DataFrame to XLSX or CSV based on file extension."""
    if output_path.lower().endswith((".xlsx", ".xls")):
        df.to_excel(output_path, index=index)
    else:
        df.to_csv(output_path, index=index)


def filter_estoque(
    df: DataInput,
    mi_me_col: str = "MI/ME",
    mi_me_value: str = "ME",
    fardo_col: str = "Fardo Padrão",
    fardo_value: str = "Sim",
    date_col: str = "Data Saida Pedido",
    max_date=None,
) -> pd.DataFrame:
    """Filter inventory by MI/ME type, standard-bale flag, and optional max date."""
    df = _coerce_to_df(df, "estoque")

    if mi_me_col in df.columns:
        df = df[df[mi_me_col].astype(str).str.strip() == mi_me_value]
    if fardo_col in df.columns:
        df = df[df[fardo_col].astype(str).str.strip() == fardo_value]
    if max_date and date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df[df[date_col] <= pd.to_datetime(max_date)]

    return df


def convert_to_numeric(
    df: DataInput,
    col_name: str,
    replace_comma: bool = True,
) -> pd.DataFrame:
    """Convert a column to float, optionally replacing comma decimals first."""
    df = _coerce_to_df(df)

    if col_name in df.columns:
        if replace_comma:
            df[col_name] = df[col_name].astype(str).str.replace(",", ".", regex=False)
        df[col_name] = pd.to_numeric(df[col_name], errors="coerce").fillna(0)

    return df


def main() -> None:
    estoque_exp_path = "estoque_exp.xlsx"
    estoque_pce_path = "estoque_pce.xlsx"
    merged_output = "merged.xlsx"
    output_path = "packed_loads.xlsx"

    dados = read_estoque_files(estoque_exp_path, estoque_pce_path, file_format="xlsx")
    merged = merge_estoque_by_progressivo(dados["estoque_exp"], dados["estoque_pce"])
    merged_df = convert_to_numeric(merged, col_name="Volume Geral")
    save_packed_loads(merged_df, merged_output)

    filtered = filter_estoque(
        merged_df,
        mi_me_col="MI/ME",
        mi_me_value="ME",
        fardo_col="Fardo Padrão",
        fardo_value="Sim",
        date_col="Data Saida Pedido",
        max_date="2026-03-31",
    )
    packed = pack_loads_by_weight(
        filtered,
        weight_col="Volume Geral",
        capacity_kg=27000,
        client_col="Cliente",
        date_col="Data Saida Pedido",
    )
    save_packed_loads(packed, output_path)

    print(f"Gerado: {merged_output} (merged com Volume Geral em kg)")
    print(f"Gerado: {output_path} | cargas: {packed['load_id'].nunique()} | total itens: {len(packed)}")


if __name__ == "__main__":
    main()
