"""Excel 文件解析服务：支持多sheet、自动表头探测、用户选列"""
import pandas as pd
import os
from typing import List, Dict, Tuple, Optional

# 商品名称列的强识别关键词（按优先级）
_NAME_KEYWORDS_STRONG = [
    # 标准叫法
    "商品名称", "品名", "产品名称", "商品名", "货品名称",
    "物料名称", "品种名称", "货物名称", "物资名称",
    # 常见变体
    "物品名称", "物件名称", "货品名", "物料名", "产品名",
    "商品", "货品", "物料", "产品", "物品",
    # 英文/混合
    "Item Name", "Product Name", "Name", "Description", "描述",
    # 其他可能
    "规格型号", "型号规格", "品牌规格",
]


def _detect_name_column(df: pd.DataFrame) -> Optional[str]:
    """自动识别商品名称列"""
    for kw in _NAME_KEYWORDS_STRONG:
        for c in df.columns:
            if kw in str(c):
                return c
    # 宽松回退
    for c in df.columns:
        if "名称" in str(c) or "name" in str(c).lower():
            return c
    return None


def _load_sheet_auto_header(file_path: str, sheet_name: str, max_scan: int = 10) -> Optional[pd.DataFrame]:
    """
    读取指定 sheet，自动探测表头行。
    增强版策略：
    1. 先找出列数最多的几行作为候选表头
    2. 从候选中选择包含商品名称关键词的行
    3. 如果都没有关键词，选择列数最多的行
    
    Args:
        file_path: Excel文件路径
        sheet_name: 工作表名称
        max_scan: 最大扫描行数（默认10行）
    """
    try:
        raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    except Exception:
        return None
    if raw is None or raw.empty:
        return None

    # 第一步：收集所有候选表头行及其信息
    candidates = []  # [(row_index, non_empty_count, has_keyword)]
    
    for i in range(min(max_scan, len(raw))):
        vals = [str(v).strip() for v in raw.iloc[i].tolist()]
        non_empty_count = sum(1 for v in vals if v)
        
        # 跳过空行或几乎空的行
        if non_empty_count < 2:
            continue
        
        # 跳过明显是数据行的情况：包含大量数字
        numeric_count = sum(1 for v in vals if v and v.replace('.', '').replace('-', '').isdigit())
        if numeric_count > len(vals) * 0.5:
            continue
        
        # 检查是否包含商品名称关键词
        has_keyword = any(any(kw.lower() in v.lower() for kw in _NAME_KEYWORDS_STRONG) for v in vals if v)
        
        candidates.append((i, non_empty_count, has_keyword))
    
    # 第二步：从候选中选择最佳表头
    # 优先选择：有关键词且列数最多的行
    keyword_candidates = [(idx, cnt) for idx, cnt, has_kw in candidates if has_kw]
    
    if keyword_candidates:
        # 在有关键词的候选中，选择列数最多的
        best_header_row = max(keyword_candidates, key=lambda x: x[1])[0]
    elif candidates:
        # 如果没有关键词候选，选择列数最多的行
        best_header_row = max(candidates, key=lambda x: x[1])[0]
    else:
        # 如果没有任何候选，使用第一行
        best_header_row = 0
    
    # 第三步：读取数据
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=best_header_row)
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def load_all_sheets(file_path: str) -> Dict[str, pd.DataFrame]:
    """读取所有非空 sheet，返回 {sheet_name: df}"""
    xl = pd.ExcelFile(file_path)
    sheets = {}
    for sn in xl.sheet_names:
        df = _load_sheet_auto_header(file_path, sn)
        if df is not None and len(df) > 0 and len(df.columns) > 0:
            sheets[sn] = df
    return sheets




def _common_columns(sheets_dict: Dict[str, pd.DataFrame], selected_sheets: List[str]) -> List[str]:
    """
    计算所选工作表的公共列标签（保持首表顺序）；无交集时回退到首表全部列。
    参考 batch_match.py 的 _common_columns 实现。
    
    Args:
        sheets_dict: {sheet_name: DataFrame} 字典
        selected_sheets: 选中的工作表名称列表
    
    Returns:
        公共列名列表
    """
    if not selected_sheets:
        return []
    
    first_cols = [str(c) for c in sheets_dict[selected_sheets[0]].columns]
    if len(selected_sheets) == 1:
        return first_cols
    
    common_set = set(first_cols)
    for sn in selected_sheets[1:]:
        if sn in sheets_dict:
            common_set &= {str(c) for c in sheets_dict[sn].columns}
    
    # 保持第一个 sheet 的列顺序
    common = [c for c in first_cols if c in common_set]
    return common if common else first_cols


def _detect_common_name_column(
    sheets_dict: Dict[str, pd.DataFrame], 
    selected_sheets: List[str]
) -> Optional[str]:
    """
    在所选工作表中识别一个通用的商品名称列标签。
    参考 batch_match.py 的 _detect_common_name_column 实现。
    
    Args:
        sheets_dict: {sheet_name: DataFrame} 字典
        selected_sheets: 选中的工作表名称列表
    
    Returns:
        检测到的商品名称列名，失败返回 None
    """
    if not selected_sheets:
        return None
    
    common = _common_columns(sheets_dict, selected_sheets)
    
    # 优先从第一个 sheet 检测
    first_col = _detect_name_column(sheets_dict[selected_sheets[0]])
    if first_col is not None and str(first_col) in common:
        return str(first_col)
    
    # 尝试其他 sheet
    for sn in selected_sheets:
        c = _detect_name_column(sheets_dict[sn])
        if c is not None and str(c) in common:
            return str(c)
    
    # 最后回退到第一个 sheet 的检测结果（即使不在公共列中）
    return str(first_col) if first_col is not None else None




def _common_columns(sheets_dict: Dict[str, pd.DataFrame], selected_sheets: List[str]) -> List[str]:
    """
    计算所选工作表的公共列标签（保持首表顺序）；无交集时回退到首表全部列。
    参考 batch_match.py 的 _common_columns 实现。
    
    Args:
        sheets_dict: {sheet_name: DataFrame} 字典
        selected_sheets: 选中的工作表名称列表
    
    Returns:
        公共列名列表
    """
    if not selected_sheets:
        return []
    
    first_cols = [str(c) for c in sheets_dict[selected_sheets[0]].columns]
    if len(selected_sheets) == 1:
        return first_cols
    
    common_set = set(first_cols)
    for sn in selected_sheets[1:]:
        if sn in sheets_dict:
            common_set &= {str(c) for c in sheets_dict[sn].columns}
    
    # 保持第一个 sheet 的列顺序
    common = [c for c in first_cols if c in common_set]
    return common if common else first_cols


def _detect_common_name_column(
    sheets_dict: Dict[str, pd.DataFrame], 
    selected_sheets: List[str]
) -> Optional[str]:
    """
    在所选工作表中识别一个通用的商品名称列标签。
    参考 batch_match.py 的 _detect_common_name_column 实现。
    
    Args:
        sheets_dict: {sheet_name: DataFrame} 字典
        selected_sheets: 选中的工作表名称列表
    
    Returns:
        检测到的商品名称列名，失败返回 None
    """
    if not selected_sheets:
        return None
    
    common = _common_columns(sheets_dict, selected_sheets)
    
    # 优先从第一个 sheet 检测
    first_col = _detect_name_column(sheets_dict[selected_sheets[0]])
    if first_col is not None and str(first_col) in common:
        return str(first_col)
    
    # 尝试其他 sheet
    for sn in selected_sheets:
        c = _detect_name_column(sheets_dict[sn])
        if c is not None and str(c) in common:
            return str(c)
    
    # 最后回退到第一个 sheet 的检测结果（即使不在公共列中）
    return str(first_col) if first_col is not None else None


def parse_excel(
    file_path: str,
    sheet_name: Optional[str] = None,
    column_name: Optional[str] = None,
) -> Tuple[List[Dict], List[str], Dict[str, List[str]]]:
    """
    解析 Excel 文件，提取商品列表。

    Args:
        file_path: Excel 文件路径
        sheet_name: 指定工作表名（None 则自动合并所有有效 sheet）
        column_name: 指定商品名称列（None 则自动检测）

    Returns:
        (items, columns, sheets_info)
        items: [{"index": 0, "raw_name": "商品名"}, ...]
        columns: 当前 sheet 的列名列表
        sheets_info: {sheet_name: [column_names]} 所有 sheet 的列信息
    """
    # 先只获取 sheet 名称列表（快速操作）
    try:
        xl = pd.ExcelFile(file_path)
        all_sheet_names = xl.sheet_names
    except Exception:
        return [], [], {}

    if not all_sheet_names:
        return [], [], {}

    # 初始化 valid_sheets_dict（用于计算公共列）
    valid_sheets_dict = {}

    # 如果指定了 sheet_name，只处理该 sheet
    if sheet_name:
        target_sheets = [sheet_name] if sheet_name in all_sheet_names else []
        # 加载指定的 sheet
        if target_sheets:
            df = _load_sheet_auto_header(file_path, sheet_name)
            if df is not None:
                valid_sheets_dict[sheet_name] = df
    else:
        # 未指定 sheet：找出所有包含商品名称列的有效 sheet
        target_sheets = []
        for sn in all_sheet_names:
            test_df = _load_sheet_auto_header(file_path, sn)
            if test_df is not None and _detect_name_column(test_df) is not None:
                target_sheets.append(sn)
                valid_sheets_dict[sn] = test_df
        
        # 如果没找到任何有效 sheet，使用第一个 sheet
        if not target_sheets:
            target_sheets = [all_sheet_names[0]]
            # 重新加载第一个 sheet
            first_df = _load_sheet_auto_header(file_path, all_sheet_names[0])
            if first_df is not None:
                valid_sheets_dict[all_sheet_names[0]] = first_df

    if not target_sheets:
        return [], [], {}

    # 合并所有目标 sheet 的数据
    merged_items = []
    merged_columns = None
    
    # 计算公共列（用于多 sheet 合并时的列对齐）
    common_cols = _common_columns(valid_sheets_dict, target_sheets) if len(target_sheets) > 1 else None
    
    for sn in target_sheets:
        df = _load_sheet_auto_header(file_path, sn)
        if df is None or df.empty:
            continue
        
        # 如果有公共列，只保留公共列（确保列对齐）
        if common_cols:
            available_cols = [c for c in common_cols if c in df.columns]
            if available_cols:
                df = df[available_cols]
        
        # 记录列名（使用第一个有效 sheet 的列名）
        if merged_columns is None:
            merged_columns = [str(c) for c in df.columns]
        
        # 选择目标列
        if column_name:
            col = column_name
            if col not in df.columns:
                # 尝试模糊匹配
                for c in df.columns:
                    if column_name in str(c):
                        col = c
                        break
                else:
                    continue  # 该 sheet 没有目标列，跳过
        else:
            col = _detect_name_column(df)
            if col is None:
                continue  # 该 sheet 没有检测到商品名称列，跳过
        
        # 提取商品名
        series = df[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        
        for val in series.tolist():
            if pd.isna(val) or not str(val).strip():
                continue
            merged_items.append({
                "index": len(merged_items),
                "raw_name": str(val).strip(),
                "_source_sheet": sn  # 记录来源 sheet（用于调试）
            })

    if not merged_items:
        return [], merged_columns or [], {}

    # 移除内部使用的 _source_sheet 字段
    items = [{"index": i, "raw_name": item["raw_name"]} for i, item in enumerate(merged_items)]

    # 构建 sheets_info（使用正确的表头检测获取列名）
    sheets_info = {}
    for sn in all_sheet_names:
        try:
            # 使用 _load_sheet_auto_header 来正确检测表头并获取列名
            temp_df = _load_sheet_auto_header(file_path, sn)
            if temp_df is not None and not temp_df.empty:
                sheets_info[sn] = [str(c) for c in temp_df.columns]
        except Exception:
            pass

    return items, merged_columns or [], sheets_info
