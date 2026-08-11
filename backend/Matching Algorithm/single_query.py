# -*- coding: utf-8 -*-
"""
功能模块一：单条查询

- 文本框输入商品名称
- 显示 Top1 匹配结果（名称 + 产品编码 + 品牌/规格/属性）
- 下拉列表显示 Top50 候选

可独立运行，也可通过 build_ui() 集成到主应用的标签页中。
"""

import os
import sys

import gradio as gr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from service import get_matcher


# ============================================
# 查询处理函数
# ============================================

def search_product(query_text: str):
    """
    查询处理: 返回 Top1 信息 + Top50 下拉列表
    """
    if not query_text or not query_text.strip():
        return "请输入商品名称", "", gr.update(choices=[], value=None)

    matcher = get_matcher()
    results = matcher.query_extended(query_text.strip(), top_n=50)

    if not results:
        return "未找到匹配结果", "", gr.update(choices=[], value=None)

    # Top1 结果
    top1 = results[0]
    top1_info = (
        f"商品名称: {top1['标准产品名称']}\n"
        f"产品编码: {top1['标准产品编码']}\n"
        f"品牌: {top1['detected_brand'] or '未识别'}\n"
        f"规格: {top1['normalized_spec'] or '无'}\n"
        f"属性: {', '.join(top1['attributes']) if top1['attributes'] else '无'}\n"
        f"匹配得分: {top1['score']}"
    )

    top1_code = str(top1['标准产品编码'])

    # Top50 下拉列表
    choices = []
    for r in results:
        label = f"[{r['rank']}] {r['标准产品名称']}  (编码:{r['标准产品编码']}, 得分:{r['score']})"
        choices.append(label)

    return top1_info, top1_code, gr.update(choices=choices, value=choices[0] if choices else None)


# ============================================
# 界面构建
# ============================================

def build_ui():
    """在当前 Blocks 上下文中构建单条查询界面"""
    gr.Markdown("### 单条查询")
    gr.Markdown("输入订单商品名称，匹配标准商品库中最相似的产品。")

    # 左右布局：左侧查询 + 结果，右侧备选列表
    with gr.Row(equal_height=False):
        # 左侧：查询输入 + Top1 结果
        with gr.Column(scale=2, min_width=400):
            query_input = gr.Textbox(
                label="输入商品名称",
                placeholder="例如：五得利五星特精小麦粉 25kg",
                lines=2,
            )
            search_btn = gr.Button("查询", variant="primary")
                
            gr.Markdown("#### Top 1 匹配结果")
            top1_output = gr.Textbox(label="匹配详情", lines=6, interactive=False)
            top1_code_output = gr.Textbox(label="产品编码", interactive=False, elem_id="code-output")
    
        # 右侧：备选列表
        with gr.Column(scale=3, min_width=500):
            gr.Markdown("#### Top 50 候选列表")
            dropdown_output = gr.Dropdown(
                label="候选商品（点击选择查看）",
                choices=[],
                interactive=True,
            )

    # 绑定事件
    search_btn.click(
        fn=search_product,
        inputs=[query_input],
        outputs=[top1_output, top1_code_output, dropdown_output],
    )
    # 回车触发查询
    query_input.submit(
        fn=search_product,
        inputs=[query_input],
        outputs=[top1_output, top1_code_output, dropdown_output],
    )


# ============================================
# 独立运行入口
# ============================================

if __name__ == '__main__':
    print("正在初始化匹配器...")
    get_matcher()
    print("初始化完成，启动单条查询界面...")

    with gr.Blocks(title="商品匹配 - 单条查询") as app:
        gr.Markdown("# 商品价格推荐 - 单条查询")
        build_ui()

    app.launch(server_name="127.0.0.1", server_port=7861, theme=gr.themes.Soft())
