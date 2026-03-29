import os
import json
import pandas as pd


def read_estoque_files(estoque_exp_path, estoque_pce_path, file_format='csv'):
    """Read estoque_exp and estoque_pce with pandas (CSV or JSON)."""
    if not os.path.exists(estoque_exp_path):
        raise FileNotFoundError(f"estoque_exp file not found: {estoque_exp_path}")
    if not os.path.exists(estoque_pce_path):
        raise FileNotFoundError(f"estoque_pce file not found: {estoque_pce_path}")

    format_lower = file_format.lower()
    if format_lower not in {'csv', 'json', 'xlsx'}:
        raise ValueError("Unsupported file_format: choose 'csv', 'json' or 'xlsx'")

    if pd is None:
        raise ImportError("pandas is required for this function. Install with `pip install pandas`.")

    if format_lower == 'csv':
        estoque_exp = pd.read_csv(estoque_exp_path, dtype=str).fillna('')
        estoque_pce = pd.read_csv(estoque_pce_path, dtype=str).fillna('')
    elif format_lower == 'xlsx':
        estoque_exp = pd.read_excel(estoque_exp_path, dtype=str).fillna('')
        estoque_pce = pd.read_excel(estoque_pce_path, dtype=str).fillna('')
    else:
        estoque_exp = pd.read_json(estoque_exp_path, dtype=False)
        estoque_pce = pd.read_json(estoque_pce_path, dtype=False)

    return {'estoque_exp': estoque_exp, 'estoque_pce': estoque_pce}


def merge_estoque_by_progressivo(estoque_exp, estoque_pce, key='progressivo'):
    """Merge estoque_exp and estoque_pce by key with estoque_exp priority using pandas."""
    if pd is None:
        raise ImportError("pandas is required for this function. Install with `pip install pandas`.")

    def _to_df(data):
        if isinstance(data, pd.DataFrame):
            df = data.copy()
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            raise TypeError('estoque data must be pandas DataFrame or list of dicts')

        if key not in df.columns:
            # tenta correspondência case-insensitive
            cols_lower = {c.lower(): c for c in df.columns}
            if key.lower() in cols_lower:
                mapped_key = cols_lower[key.lower()]
                df = df.rename(columns={mapped_key: key})
            else:
                raise KeyError(
                    f"Missing key '{key}' in data (colunas encontradas: {list(df.columns)})"
                )

        return df.astype({key: str}).set_index(key, drop=False)

    df_exp = _to_df(estoque_exp)
    df_pce = _to_df(estoque_pce)

    merged_df = df_exp.combine_first(df_pce).reset_index(drop=True)
    return merged_df.to_dict(orient='records')


def pack_loads_by_weight(df, weight_col='peso', capacity_kg=27000, client_col=None):
    """Pack items in loads by weight (First-Fit Decreasing) and compute occupancy.

    Args:
        df (pd.DataFrame or list[dict]): source dataset with weight values.
        weight_col (str): column name that stores weight in kg.
        capacity_kg (float): maximum load capacity in kg (default 27000).
        client_col (str): if provided, groups by client first (each client gets separate loads).

    Returns:
        pd.DataFrame: source columns plus load_id, load_total_weight, load_occupancy.
    """
    if pd is None:
        raise ImportError("pandas is required for this function. Install with `pip install pandas`.")

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    if weight_col not in df.columns:
        cols_lower = {c.lower(): c for c in df.columns}
        if weight_col.lower() in cols_lower:
            weight_col = cols_lower[weight_col.lower()]
        else:
            raise KeyError(
                f"Weight column '{weight_col}' not found (colunas disponíveis: {list(df.columns)})"
            )

    df = df.copy()
    df['__item_weight'] = pd.to_numeric(df[weight_col], errors='coerce').fillna(0)

    # se client_col fornecido, agrupa por cliente
    if client_col and client_col in df.columns:
        load_counter = 1
        for client in df[client_col].unique():
            client_df = df[df[client_col] == client]
            client_indices = client_df.index
            
            # FFD para este cliente
            sorted_idx = client_df['__item_weight'].sort_values(ascending=False).index
            loads = []
            assignment = {}
            
            for i in sorted_idx:
                weight = float(df.at[i, '__item_weight'])
                if weight <= 0:
                    assignment[i] = 0
                    continue
                
                placed = False
                for load in loads:
                    if load['weight'] + weight <= capacity_kg:
                        load['weight'] += weight
                        assignment[i] = load['id']
                        placed = True
                        break
                
                if not placed:
                    new_load_id = load_counter if load_counter > 0 else len(loads) + load_counter
                    loads.append({'id': new_load_id, 'weight': weight})
                    assignment[i] = new_load_id
                    load_counter += 1
            
            # atribui load_id do cliente
            for idx, load_id in assignment.items():
                df.at[idx, 'load_id'] = load_id
        
        # computa load_total_weight e occupancy
        df['load_total_weight'] = 0.0
        df['load_occupancy'] = 0.0
        for load_id in df['load_id'].unique():
            if load_id == 0:
                continue
            load_rows = df[df['load_id'] == load_id]
            total_weight = load_rows['__item_weight'].sum()
            df.loc[load_rows.index, 'load_total_weight'] = total_weight
            df.loc[load_rows.index, 'load_occupancy'] = total_weight / capacity_kg
        
        df.loc[df['load_id'] == 0, 'load_occupancy'] = 0.0
    else:
        # FFD simples (sem agrupamento por cliente)
        sorted_idx = df['__item_weight'].sort_values(ascending=False).index

        loads = []
        assignment = []

        for i in sorted_idx:
            weight = float(df.at[i, '__item_weight'])
            if weight <= 0:
                assignment.append((i, 0))
                continue

            placed = False
            for load in loads:
                if load['weight'] + weight <= capacity_kg:
                    load['weight'] += weight
                    assignment.append((i, load['id']))
                    placed = True
                    break

            if not placed:
                new_load_id = len(loads) + 1
                loads.append({'id': new_load_id, 'weight': weight})
                assignment.append((i, new_load_id))

        assign_df = pd.DataFrame(assignment, columns=['index', 'load_id'])
        assign_df = assign_df.set_index('index')
        df = df.join(assign_df)

        load_weights = pd.DataFrame(loads).set_index('id')
        df['load_total_weight'] = df['load_id'].map(load_weights['weight']).fillna(0)
        df['load_occupancy'] = (df['load_total_weight'] / capacity_kg).clip(0, 1)

        df.loc[df['load_id'] == 0, 'load_occupancy'] = 0.0

    df.drop(columns=['__item_weight'], inplace=True)
    return df


def save_packed_loads(df, output_path, index=False):
    """Salva a planilha com os dados de carga já empacotados."""
    if isinstance(output_path, str) and output_path.lower().endswith(('.xlsx', '.xls')):
        df.to_excel(output_path, index=index)
    else:
        df.to_csv(output_path, index=index)


def filter_estoque(df, mi_me_col='MI/ME', mi_me_value='ME', fardo_col='Fardo Padrão', fardo_value='Sim'):
    """Filtra estoque por MI/ME e Fardo Padrão.
    
    Args:
        df (pd.DataFrame or list[dict]): dados originais.
        mi_me_col (str): nome da coluna MI/ME.
        mi_me_value (str): valor a filtrar em MI/ME (default 'ME').
        fardo_col (str): nome da coluna Fardo Padrão.
        fardo_value (str): valor a filtrar em Fardo Padrão (default 'Sim').
    
    Returns:
        pd.DataFrame: dados filtrados.
    """
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    df = df.copy()
    
    # filtro case-insensitive para MI/ME
    if mi_me_col in df.columns:
        df = df[df[mi_me_col].astype(str).str.strip() == mi_me_value]
    
    # filtro case-insensitive para Fardo Padrão
    if fardo_col in df.columns:
        df = df[df[fardo_col].astype(str).str.strip() == fardo_value]
    
    return df


def convert_to_numeric(df, col_name, replace_comma=True):
    """Converte coluna para número, substituindo vírgula por ponto se necessário.
    
    Args:
        df (pd.DataFrame or list[dict]): dataframe ou lista de dicts.
        col_name (str): nome da coluna a converter.
        replace_comma (bool): se True, substitui ',' por '.' antes de converter.
    
    Returns:
        pd.DataFrame: dataframe com coluna convertida.
    """
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    
    df = df.copy()
    
    if col_name in df.columns:
        if replace_comma:
            df[col_name] = df[col_name].astype(str).str.replace(',', '.', regex=False)
        df[col_name] = pd.to_numeric(df[col_name], errors='coerce').fillna(0)
    
    return df


if __name__ == '__main__':
    estoque_exp_path = 'estoque_exp.xlsx'
    estoque_pce_path = 'estoque_pce.xlsx'
    merged_output = 'merged.xlsx'
    output_path = 'packed_loads.xlsx'

    dados = read_estoque_files(estoque_exp_path, estoque_pce_path, file_format='xlsx')
    merged = merge_estoque_by_progressivo(dados['estoque_exp'], dados['estoque_pce'])
    
    # converter Volume Geral antes de salvar merged
    merged_converted = convert_to_numeric(merged, col_name='Volume Geral', replace_comma=True)
    
    # salvar merged com Volume Geral em número
    if isinstance(merged_converted, list):
        merged_df = pd.DataFrame(merged_converted)
    else:
        merged_df = merged_converted
    save_packed_loads(merged_df, merged_output)
    
    filtered = filter_estoque(merged_converted, mi_me_col='MI/ME', mi_me_value='ME', fardo_col='Fardo Padrão', fardo_value='Sim')
    packed = pack_loads_by_weight(filtered, weight_col='Volume Geral', capacity_kg=27000, client_col='Cliente')
    save_packed_loads(packed, output_path)

    print(f'Gerado: {merged_output} (merged com Volume Geral em kg)')
    print(f'Gerado: {output_path} | cargas: {packed.load_id.nunique()} | total itens: {len(packed)}')
