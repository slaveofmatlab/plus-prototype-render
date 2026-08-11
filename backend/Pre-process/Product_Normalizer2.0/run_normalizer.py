# -*- coding: utf-8 -*-
"""
运行脚本 - 商品名称标准化工具的快速启动脚本

使用方法:
    python run_normalizer.py <输入Excel文件> [输出Excel文件]

示例:
    python run_normalizer.py products.xlsx
    python run_normalizer.py products.xlsx output.xlsx
"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from normalizer.main import process_excel


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("="*60)
        print("商品名称标准化工具 (Product Name Normalizer)")
        print("="*60)
        print("\n使用方法:")
        print("  python run_normalizer.py <输入Excel文件> [输出Excel文件]")
        print("\n示例:")
        print("  python run_normalizer.py products.xlsx")
        print("  python run_normalizer.py products.xlsx output.xlsx")
        print("\n参数说明:")
        print("  输入Excel文件: 必需，包含商品名称的Excel文件")
        print("  输出Excel文件: 可选，默认在原文件名后添加_normalized_时间戳")
        print("\nExcel文件要求:")
        print("  必须包含列: 商品名称")
        print("  可选列: 品牌, 一级分类, 商品ID")
        print("="*60)
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        print(f"错误: 文件不存在: {input_file}")
        sys.exit(1)
    
    print("="*60)
    print("商品名称标准化工具")
    print("="*60)
    print(f"输入文件: {input_file}")
    if output_file:
        print(f"输出文件: {output_file}")
    else:
        print("输出文件: 自动生成 (原文件名_normalized_时间戳.xlsx)")
    print("="*60)
    print()
    
    try:
        df = process_excel(input_file, output_file, log_level='INFO')
        print("\n" + "="*60)
        print("处理完成!")
        print(f"共处理 {len(df)} 条记录")
        print("="*60)
    except Exception as e:
        print(f"\n错误: 处理失败 - {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
