# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Load optimizer (otimizador de carga) for packing freight items into truck loads. It reads inventory exports from two sources (`estoque_exp` and `estoque_pce`), merges them by a `progressivo` key (exp has priority), filters by MI/ME type and standard-bale flag, then runs a First-Fit Decreasing (FFD) bin-packing algorithm that respects a 27,000 kg capacity per load. Output is an Excel/CSV with `load_id`, `load_total_weight`, and `load_occupancy` columns added.

## Architecture

```
main.py          — core Python library (all business logic lives here)
api.py           — Flask REST API wrapping pack_loads_by_weight (single route)
test_main.py     — pytest test suite covering all functions in main.py
bin-packing-visualizer/  — React app that calls the Flask API to visualize packing
```

### Key functions in `main.py`

| Function | Purpose |
|---|---|
| `read_estoque_files` | Load CSV/JSON/XLSX inventory files into DataFrames |
| `merge_estoque_by_progressivo` | Merge two inventories, exp-priority, by `progressivo` key |
| `filter_estoque` | Filter by MI/ME column, Fardo Padrão column, and max date |
| `convert_to_numeric` | Convert comma-decimal strings to float (e.g. `"1,5"` → `1.5`) |
| `pack_loads_by_weight` | FFD bin-packing; optional grouping by client and date sorting |
| `save_packed_loads` | Save DataFrame to CSV or XLSX based on file extension |

The `pack_loads_by_weight` function has two modes:
- **Simple (no `client_col`)**: global FFD across all items, sorted by date then weight desc.
- **Grouped (`client_col` set)**: each client gets independent load numbering; load IDs are globally unique via a shared counter.

### Flask API (`api.py`)

Single endpoint: `POST /pack_loads`  
Body: `{ items: [...], capacity_kg, weight_col, client_col?, date_col? }`  
Returns the packed DataFrame as a list of records (JSON).

### React visualizer (`bin-packing-visualizer/`)

Calls `http://localhost:5000/pack_loads` and renders each load as a card with total weight. The local `binPacking.js` FFD implementation is currently commented out in favor of the API call.

## Commands

### Python backend

```bash
# Run the main pipeline (requires estoque_exp.xlsx and estoque_pce.xlsx in working dir)
python main.py

# Start the Flask API (default port 5000)
python api.py

# Run all tests
pytest test_main.py

# Run a specific test class or test
pytest test_main.py::TestPackLoadsByWeightSimple
pytest test_main.py::TestPackLoadsByWeightSimple::test_overflow_creates_second_load
```

### React frontend

```bash
cd bin-packing-visualizer
npm start        # dev server at http://localhost:3000
npm run build    # production build
npm test         # run React tests
```

## Input data notes

- Weight column in production data is `Volume Geral` (in kg), stored as comma-decimal strings — `convert_to_numeric` must be called before `pack_loads_by_weight`.
- Merge key `progressivo` is matched case-insensitively.
- Date column `Data Saida Pedido` controls sort order within each client group (oldest items packed first).
- Items with weight ≤ 0 receive `load_id = 0` and are excluded from occupancy calculations.
