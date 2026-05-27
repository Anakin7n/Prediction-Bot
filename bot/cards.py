"""飞书消息模板 — 纯文本版本"""


def ask_date():
    return "📅 请输入**预测日期**，格式如 `6.15`"


def ask_movies(date_str: str):
    return (
        f"🎬 预测日期: **{date_str}**\n\n"
        "请输入需要预测的**影片名称及累计新增占比**：\n"
        "`影片A:17.6%, 影片B:0.147, 影片C=5.6%`\n\n"
        "> 支持格式: 小数/百分比，中英文冒号、等号、横线分隔，逗号、分号、顿号分隔多部"
    )


def ask_dapan(date_str: str, matched_movies: list[dict], unmatched_names: list[str], total_show_count: int):
    return "请输入**大盘场次(D)**（如 `420000`）"


def result(date_str: str, movie_count: int, dapan: int):
    return (
        f"✅ 预测 Excel 已生成\n\n"
        f"📅 预测日期: **{date_str}**\n"
        f"🎬 影片数量: **{movie_count}** 部\n"
        f"🏟️ 大盘场次: **{dapan:,}** 场\n\n"
        f"📎 请查收下方 Excel 文件"
    )


def error(msg: str):
    return f"⚠️ 出错了: {msg}"


def welcome():
    return "👋 欢迎使用影片落位预测 Bot！\n请发送 **/start** 开始预测。"


def invalid_format(hint: str):
    return f"⚠️ {hint}"
