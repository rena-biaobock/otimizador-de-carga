# Otimizador de Carga

Ferramenta de otimização de cargas para transporte. Lê inventários de duas fontes (`estoque_exp` e `estoque_pce`), realiza o merge priorizando a fonte exportada, filtra os itens elegíveis e distribui os volumes entre carretas usando o algoritmo **First-Fit Decreasing (FFD)**, respeitando a capacidade máxima por carga.

---

## Pré-requisitos

- Python 3.10+
- Node.js 18+ (apenas para o visualizador)

## Instalação

```bash
# Criar e ativar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Instalar dependências Python
pip install pandas openpyxl flask flask-cors

# Instalar dependências do visualizador (opcional)
cd bin-packing-visualizer && npm install
```

---

## Como executar

### Pipeline principal

Coloque os arquivos `estoque_exp.xlsx` e `estoque_pce.xlsx` na raiz do projeto e execute:

```bash
python main.py
```

Saída gerada:
- `merged.xlsx` — inventário consolidado com `Volume Geral` convertido para número
- `packed_loads.xlsx` — itens distribuídos em cargas com `load_id`, `load_total_weight` e `load_occupancy`

### API REST (Flask)

```bash
python api.py
# Servidor disponível em http://localhost:5000
```

**Verificar saúde da API:**
```bash
curl http://localhost:5000/health
```

**Empacotar cargas via API:**
```bash
curl -X POST http://localhost:5000/pack_loads \
  -H "Content-Type: application/json" \
  -d '{
    "items": [{"weight": 10000}, {"weight": 8000}, {"weight": 15000}],
    "capacity_kg": 27000,
    "weight_col": "weight"
  }'
```

Parâmetros do corpo (JSON):

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `items` | `list` | sim | Lista de objetos com os dados dos itens |
| `capacity_kg` | `float` | sim | Capacidade máxima por carga em kg |
| `weight_col` | `string` | sim | Nome da coluna de peso nos itens |
| `client_col` | `string` | não | Agrupa por cliente (cada cliente tem cargas independentes) |
| `date_col` | `string` | não | Ordena por data ascendente antes do peso |

### Visualizador (React)

Com a API rodando em `localhost:5000`:

```bash
cd bin-packing-visualizer
npm start
# Abre em http://localhost:3000
```

---

## Testes

```bash
# Todos os testes
.venv/bin/pytest test_main.py -v

# Uma classe específica
.venv/bin/pytest test_main.py::TestPackLoadsByWeightSimple -v

# Um teste específico
.venv/bin/pytest test_main.py::TestPackLoadsByWeightSimple::test_overflow_creates_second_load -v
```

---

## Referência da API Python (`main.py`)

### `read_estoque_files(estoque_exp_path, estoque_pce_path, file_format='csv')`

Lê os dois arquivos de estoque. Suporta `'csv'`, `'json'` e `'xlsx'`. Retorna `dict` com chaves `estoque_exp` e `estoque_pce` (DataFrames).

---

### `merge_estoque_by_progressivo(estoque_exp, estoque_pce, key='progressivo')`

Consolida os dois estoques usando `combine_first`: campos presentes em `estoque_exp` têm prioridade; lacunas são preenchidas por `estoque_pce`. O match da coluna-chave é case-insensitive. Retorna `list[dict]`.

---

### `filter_estoque(df, mi_me_col, mi_me_value, fardo_col, fardo_value, date_col, max_date)`

Filtra o DataFrame por tipo MI/ME, flag de Fardo Padrão e data máxima (inclusive). Colunas ausentes são ignoradas sem erro. Retorna `pd.DataFrame`.

---

### `convert_to_numeric(df, col_name, replace_comma=True)`

Converte uma coluna para `float`, substituindo vírgula por ponto antes de converter (padrão brasileiro). Valores inválidos viram `0`. Retorna `pd.DataFrame`.

---

### `pack_loads_by_weight(df, weight_col, capacity_kg, client_col, date_col)`

Algoritmo FFD: itens com peso zero recebem `load_id = 0`; demais são ordenados por data (ascendente) e depois peso (descendente) e encaixados nas cargas existentes antes de abrir uma nova. Com `client_col`, cada cliente tem numeração de carga independente mas IDs globalmente únicos. Retorna `pd.DataFrame` com as colunas originais mais:

| Coluna | Descrição |
|---|---|
| `load_id` | Identificador da carga (0 = sem carga) |
| `load_total_weight` | Peso total da carga em kg |
| `load_occupancy` | Ocupação da carga (0.0 – 1.0) |

---

### `save_packed_loads(df, output_path, index=False)`

Salva o DataFrame em XLSX (se a extensão for `.xlsx` ou `.xls`) ou CSV.
