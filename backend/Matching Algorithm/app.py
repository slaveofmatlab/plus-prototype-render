# -*- coding: utf-8 -*-
"""
商品价格推荐 - 商品匹配查询 主入口

整合两个功能模块（标签页）:
- 模块一: 单条查询 (single_query)
- 模块二: 批量匹配 (batch_match)
"""

import os
import sys

import gradio as gr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from service import get_matcher
import single_query
import batch_match


# 自定义CSS: 字体/间距/组件风格统一美化
_CUSTOM_CSS = """
/* ---------- 全局字体 ---------- */
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif;
}
.gradio-container {
    max-width: 1500px !important;
    margin: 0 auto;
}
/* 强制 Row 内 Column 横向排列 */
.gradio-container .gr-row {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
}

/* ---------- 标题层级 ---------- */
.prose h1 {
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 0.02em;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 10px;
}
.prose h3 { font-size: 19px; font-weight: 600; }
.prose h4 { font-size: 16px; font-weight: 600; color: #334155; }
.prose p, .prose li { font-size: 14px; line-height: 1.7; color: #475569; }

/* ---------- 标签页 ---------- */
.tab-nav { border-bottom: 2px solid #e2e8f0; }
.tab-nav button {
    font-size: 15px !important;
    font-weight: 600;
    padding: 10px 22px !important;
}

/* ---------- 表单控件 ---------- */
label > span { font-size: 13px; font-weight: 600; color: #475569; }
input, textarea, .wrap.svelte-1ipelgc {
    font-size: 14px !important;
}

/* ---------- 按钮 ---------- */
button.primary {
    font-size: 14px !important;
    font-weight: 600;
    border-radius: 8px !important;
    padding: 8px 18px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.12);
}
button.secondary {
    font-size: 14px !important;
    border-radius: 8px !important;
    padding: 8px 14px !important;
}

/* ---------- 匹配结果表：表头与行 ---------- */
[id^="result-row"] { align-items: center; gap: 8px; }
/* 偶数行（0,2,4...）白色背景 */
#result-row-0, #result-row-2, #result-row-4, #result-row-6, #result-row-8,
#result-row-10, #result-row-12, #result-row-14 {
    background: #ffffff;
    border-radius: 6px;
    padding: 6px 8px;
}
/* 奇数行（1,3,5...）浅蓝背景 */
#result-row-1, #result-row-3, #result-row-5, #result-row-7, #result-row-9,
#result-row-11, #result-row-13 {
    background: #eef6fc;
    border-radius: 6px;
    padding: 6px 8px;
}
[id^="cell-name"] input {
    font-weight: 600;
    color: #0f172a;
}
/* 编码与数值列使用等宽字体，数字更清晰 */
[id^="cell-code"] input, [id^="cell-recall"] input, [id^="cell-conf"] input {
    font-family: "Cascadia Code", "Consolas", "Segoe UI", monospace !important;
    font-size: 14px;
}
[id^="cell-recall"] input, [id^="cell-conf"] input { font-weight: 600; color: #0369a1; }

/* ---------- 筛选工具栏 ---------- */
#filter-toolbar {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 10px 12px;
}

/* ---------- 单条查询页编码输出 ---------- */
#code-output input {
    font-family: "Cascadia Code", "Consolas", "Segoe UI", monospace !important;
    font-size: 16px;
    font-weight: 600;
}
"""


def create_app():
    with gr.Blocks(title="商品匹配查询 V1") as app:
        gr.Markdown("# 商品价格推荐 - 商品匹配查询 V1")
        gr.Markdown("输入订单商品名称或上传询价表单，匹配标准商品库中最相似的产品。")

        with gr.Tab("单条查询"):
            single_query.build_ui()

        with gr.Tab("批量匹配"):
            batch_match.build_ui()

    return app


if __name__ == '__main__':
    # 预加载
    print("正在初始化匹配器...")
    get_matcher()
    print("初始化完成，启动界面...")

    app = create_app()
    # Gradio 6: theme/css 需传给 launch()
    app.launch(server_name="127.0.0.1", server_port=7861,
               theme=gr.themes.Soft(), css=_CUSTOM_CSS)
