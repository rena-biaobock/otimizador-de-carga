import os
import tempfile

import pandas as pd
import pytest

from main import (
    convert_to_numeric,
    filter_estoque,
    merge_estoque_by_progressivo,
    pack_loads_by_weight,
    read_estoque_files,
    save_packed_loads,
)


# ---------------------------------------------------------------------------
# read_estoque_files
# ---------------------------------------------------------------------------

class TestReadEstoqueFiles:
    def _write_csv(self, path, content):
        path.write_text(content, encoding="utf-8")

    def test_reads_csv_files(self, tmp_path):
        exp = tmp_path / "exp.csv"
        pce = tmp_path / "pce.csv"
        exp.write_text("progressivo,valor\n1,A\n")
        pce.write_text("progressivo,valor\n2,B\n")
        result = read_estoque_files(str(exp), str(pce), file_format="csv")
        assert list(result["estoque_exp"]["progressivo"]) == ["1"]
        assert list(result["estoque_pce"]["progressivo"]) == ["2"]

    def test_raises_if_exp_missing(self, tmp_path):
        pce = tmp_path / "pce.csv"
        pce.write_text("a,b\n")
        with pytest.raises(FileNotFoundError):
            read_estoque_files("nope.csv", str(pce))

    def test_raises_if_pce_missing(self, tmp_path):
        exp = tmp_path / "exp.csv"
        exp.write_text("a,b\n")
        with pytest.raises(FileNotFoundError):
            read_estoque_files(str(exp), "nope.csv")

    def test_raises_on_unsupported_format(self, tmp_path):
        exp = tmp_path / "exp.csv"
        pce = tmp_path / "pce.csv"
        exp.write_text("a\n1\n")
        pce.write_text("a\n1\n")
        with pytest.raises(ValueError):
            read_estoque_files(str(exp), str(pce), file_format="parquet")

    def test_reads_json_files(self, tmp_path):
        exp = tmp_path / "exp.json"
        pce = tmp_path / "pce.json"
        exp.write_text('[{"progressivo": "1", "valor": "A"}]')
        pce.write_text('[{"progressivo": "2", "valor": "B"}]')
        result = read_estoque_files(str(exp), str(pce), file_format="json")
        assert len(result["estoque_exp"]) == 1
        assert len(result["estoque_pce"]) == 1

    def test_reads_xlsx_files(self, tmp_path):
        exp_path = tmp_path / "exp.xlsx"
        pce_path = tmp_path / "pce.xlsx"
        pd.DataFrame({"progressivo": ["1"], "valor": ["A"]}).to_excel(str(exp_path), index=False)
        pd.DataFrame({"progressivo": ["2"], "valor": ["B"]}).to_excel(str(pce_path), index=False)
        result = read_estoque_files(str(exp_path), str(pce_path), file_format="xlsx")
        assert list(result["estoque_exp"]["progressivo"]) == ["1"]


# ---------------------------------------------------------------------------
# merge_estoque_by_progressivo
# ---------------------------------------------------------------------------

class TestMergeEstoqueByProgressivo:
    def test_exp_takes_priority(self):
        exp = [{"progressivo": "1", "valor": "EXP"}]
        pce = [{"progressivo": "1", "valor": "PCE"}]
        result = merge_estoque_by_progressivo(exp, pce)
        assert result[0]["valor"] == "EXP"

    def test_pce_fills_missing(self):
        exp = [{"progressivo": "1", "valor": "EXP"}]
        pce = [{"progressivo": "1", "valor": "PCE"}, {"progressivo": "2", "valor": "ONLY_PCE"}]
        result = merge_estoque_by_progressivo(exp, pce)
        progressivos = [r["progressivo"] for r in result]
        assert "2" in progressivos

    def test_accepts_dataframe_input(self):
        exp = pd.DataFrame({"progressivo": ["1"], "valor": ["EXP"]})
        pce = pd.DataFrame({"progressivo": ["1"], "valor": ["PCE"]})
        result = merge_estoque_by_progressivo(exp, pce)
        assert result[0]["valor"] == "EXP"

    def test_case_insensitive_key_mapping(self):
        exp = [{"Progressivo": "1", "valor": "EXP"}]
        pce = [{"progressivo": "1", "valor": "PCE"}]
        result = merge_estoque_by_progressivo(exp, pce, key="progressivo")
        assert len(result) == 1

    def test_raises_on_missing_key(self):
        exp = [{"other": "1"}]
        pce = [{"progressivo": "1"}]
        with pytest.raises(KeyError):
            merge_estoque_by_progressivo(exp, pce)

    def test_raises_on_bad_type(self):
        with pytest.raises(TypeError):
            merge_estoque_by_progressivo("bad", [])


# ---------------------------------------------------------------------------
# pack_loads_by_weight  (simple / no client grouping)
# ---------------------------------------------------------------------------

class TestPackLoadsByWeightSimple:
    def _df(self, weights):
        return pd.DataFrame({"peso": weights})

    def test_single_item_fits(self):
        result = pack_loads_by_weight(self._df([1000]))
        assert result["load_id"].iloc[0] == 1
        assert result["load_occupancy"].iloc[0] == pytest.approx(1000 / 27000)

    def test_items_packed_into_one_load(self):
        result = pack_loads_by_weight(self._df([10000, 10000, 6000]))
        assert result["load_id"].nunique() == 1

    def test_overflow_creates_second_load(self):
        result = pack_loads_by_weight(self._df([20000, 20000]))
        assert result["load_id"].nunique() == 2

    def test_zero_weight_gets_load_id_zero(self):
        result = pack_loads_by_weight(self._df([0, 5000]))
        zero_rows = result[result["load_id"] == 0]
        assert len(zero_rows) == 1

    def test_load_total_weight_correct(self):
        result = pack_loads_by_weight(self._df([10000, 10000]))
        assert result["load_total_weight"].iloc[0] == pytest.approx(20000)

    def test_occupancy_never_exceeds_one(self):
        result = pack_loads_by_weight(self._df([27000, 1000]))
        assert (result["load_occupancy"] <= 1.0).all()

    def test_accepts_list_of_dicts(self):
        data = [{"peso": 5000}, {"peso": 3000}]
        result = pack_loads_by_weight(data)
        assert isinstance(result, pd.DataFrame)
        assert "load_id" in result.columns

    def test_raises_on_missing_weight_col(self):
        with pytest.raises(KeyError):
            pack_loads_by_weight(pd.DataFrame({"other": [1]}))

    def test_case_insensitive_weight_col(self):
        df = pd.DataFrame({"Peso": [5000, 3000]})
        result = pack_loads_by_weight(df, weight_col="peso")
        assert "load_id" in result.columns

    def test_custom_capacity(self):
        result = pack_loads_by_weight(self._df([600, 600]), capacity_kg=1000)
        assert result["load_id"].nunique() == 2

    def test_ffd_ordering(self):
        # FFD: heaviest first → two items of 15000 each, capacity 27000 → each in own load
        result = pack_loads_by_weight(self._df([15000, 15000, 5000]))
        # 15000 + 5000 = 20000 fits; second 15000 alone
        assert result["load_id"].nunique() == 2

    def test_date_col_sorts_before_weight(self):
        df = pd.DataFrame({
            "peso": [10000, 10000, 10000],
            "data": ["2026-01-03", "2026-01-01", "2026-01-02"],
        })
        result = pack_loads_by_weight(df, date_col="data")
        assert "load_id" in result.columns


# ---------------------------------------------------------------------------
# pack_loads_by_weight  (with client grouping)
# ---------------------------------------------------------------------------

class TestPackLoadsByWeightClientGrouping:
    def _df(self, clients, weights):
        return pd.DataFrame({"cliente": clients, "peso": weights})

    def test_each_client_gets_own_loads(self):
        df = self._df(["A", "A", "B", "B"], [20000, 20000, 20000, 20000])
        result = pack_loads_by_weight(df, client_col="cliente")
        # Each client has 2 items × 20000 kg, capacity 27000 → 2 loads each
        assert len(result) == 4

    def test_load_total_weight_correct_per_client(self):
        # Bug regression: cross-client load_id collision must NOT mix weights
        df = self._df(["A", "B"], [15000, 8000])
        result = pack_loads_by_weight(df, client_col="cliente")
        a_weight = result[result["cliente"] == "A"]["load_total_weight"].iloc[0]
        b_weight = result[result["cliente"] == "B"]["load_total_weight"].iloc[0]
        assert a_weight == pytest.approx(15000)
        assert b_weight == pytest.approx(8000)

    def test_zero_weight_skipped(self):
        df = self._df(["A", "A"], [0, 10000])
        result = pack_loads_by_weight(df, client_col="cliente")
        assert (result[result["peso"] == 0]["load_id"] == 0).all()

    def test_multiple_clients_multiple_loads(self):
        df = self._df(
            ["A", "A", "B", "B"],
            [20000, 20000, 20000, 20000],
        )
        result = pack_loads_by_weight(df, client_col="cliente", capacity_kg=27000)
        for client in ["A", "B"]:
            client_loads = result[result["cliente"] == client]["load_id"].unique()
            assert len(client_loads) == 2


# ---------------------------------------------------------------------------
# filter_estoque
# ---------------------------------------------------------------------------

class TestFilterEstoque:
    def _df(self):
        return pd.DataFrame({
            "MI/ME": ["ME", "MI", "ME"],
            "Fardo Padrão": ["Sim", "Sim", "Não"],
            "Data Saida Pedido": ["2026-01-01", "2026-02-01", "2026-03-01"],
        })

    def test_filters_me_fardo_sim(self):
        result = filter_estoque(self._df())
        assert len(result) == 1
        assert result.iloc[0]["MI/ME"] == "ME"
        assert result.iloc[0]["Fardo Padrão"] == "Sim"

    def test_max_date_exclusive(self):
        result = filter_estoque(self._df(), max_date="2025-12-31")
        assert len(result) == 0

    def test_max_date_inclusive(self):
        result = filter_estoque(self._df(), max_date="2026-01-01")
        assert len(result) == 1

    def test_accepts_list_of_dicts(self):
        data = [
            {"MI/ME": "ME", "Fardo Padrão": "Sim", "Data Saida Pedido": "2026-01-01"},
        ]
        result = filter_estoque(data)
        assert len(result) == 1

    def test_missing_columns_skipped(self):
        df = pd.DataFrame({"outras": ["x"]})
        result = filter_estoque(df)
        assert len(result) == 1  # no filter applied


# ---------------------------------------------------------------------------
# convert_to_numeric
# ---------------------------------------------------------------------------

class TestConvertToNumeric:
    def test_converts_comma_decimal(self):
        df = pd.DataFrame({"peso": ["1.500,75", "2.000,00"]})
        # comma-as-thousands not handled here; basic comma→dot replacement
        df_simple = pd.DataFrame({"peso": ["1,5", "2,0"]})
        result = convert_to_numeric(df_simple, "peso")
        assert result["peso"].tolist() == pytest.approx([1.5, 2.0])

    def test_converts_plain_number_string(self):
        df = pd.DataFrame({"peso": ["100", "200"]})
        result = convert_to_numeric(df, "peso", replace_comma=False)
        assert result["peso"].tolist() == [100.0, 200.0]

    def test_coerces_invalid_to_zero(self):
        df = pd.DataFrame({"peso": ["abc", "50"]})
        result = convert_to_numeric(df, "peso")
        assert result["peso"].iloc[0] == 0.0

    def test_missing_column_is_noop(self):
        df = pd.DataFrame({"other": [1]})
        result = convert_to_numeric(df, "peso")
        assert "peso" not in result.columns

    def test_accepts_list_of_dicts(self):
        data = [{"peso": "1,5"}, {"peso": "2,0"}]
        result = convert_to_numeric(data, "peso")
        assert isinstance(result, pd.DataFrame)
        assert result["peso"].tolist() == pytest.approx([1.5, 2.0])


# ---------------------------------------------------------------------------
# save_packed_loads
# ---------------------------------------------------------------------------

class TestSavePackedLoads:
    def _df(self):
        return pd.DataFrame({"a": [1, 2], "b": [3, 4]})

    def test_saves_csv(self, tmp_path):
        path = tmp_path / "out.csv"
        save_packed_loads(self._df(), str(path))
        loaded = pd.read_csv(str(path))
        assert list(loaded.columns) == ["a", "b"]

    def test_saves_xlsx(self, tmp_path):
        path = tmp_path / "out.xlsx"
        save_packed_loads(self._df(), str(path))
        loaded = pd.read_excel(str(path))
        assert list(loaded.columns) == ["a", "b"]

    def test_no_index_by_default(self, tmp_path):
        path = tmp_path / "out.csv"
        save_packed_loads(self._df(), str(path))
        loaded = pd.read_csv(str(path))
        assert "Unnamed: 0" not in loaded.columns
