"""Read MaoYan show counts from its current dashboard response."""

import json
import logging
import re
from datetime import date as dt_date
from functools import lru_cache
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_DASHBOARD = "https://piaofang.maoyan.com/i/dashboard/movie"
_SESSION = "https://piaofang.maoyan.com/session"


class MaoyanClient:
    def fetch_by_date(self, user_names: list[str], date_str: str) -> tuple[list[dict], int]:
        from playwright.sync_api import sync_playwright

        requested_date = _to_api_date(date_str)
        today = dt_date.today().isoformat()
        with sync_playwright() as playwright:
            browser = _launch_browser(playwright)
            try:
                today_page, today_data = _read_dashboard(browser, today)
                session = _read_session()
                known_digits = _learn_digits(today_data, session["movieRankList"])
                templates = _render_digits(today_page, today_data, known_digits)
                if requested_date == today:
                    page, data = today_page, today_data
                else:
                    page, data = _read_dashboard(browser, requested_date)
                digit_map = _match_digits(page, data, templates)
                movies = data["movieList"]["list"]
                by_name = {}
                for movie in movies:
                    name = movie["movieInfo"]["movieName"]
                    if name in by_name:
                        logger.warning(
                            "猫眼 %s 有同名影片「%s」(movieId=%s、%s)，采用页面中排名靠前的影片",
                            requested_date,
                            name,
                            by_name[name]["movieInfo"]["movieId"],
                            movie["movieInfo"]["movieId"],
                        )
                    else:
                        by_name[name] = movie
                session_by_name = {
                    m["movieName"]: m["count"] for m in session["movieRankList"]
                }
                results = []
                for name in user_names:
                    name = name.strip()
                    movie = by_name.get(name)
                    if movie is None:
                        raise RuntimeError(
                            f"影片「{name}」不在猫眼 {requested_date} 大盘影片列表中"
                        )
                    count = _decode_number(movie["showCount"], digit_map)
                    if requested_date == today and name in session_by_name:
                        count = session_by_name[name]
                    results.append({
                        "name": name,
                        "show_count": count,
                        "box_rate": "N/A",
                        "movie_id": movie["movieInfo"]["movieId"],
                    })
                if requested_date == today:
                    total = session["totalCount"]
                else:
                    desc = data["movieList"]["nationBoxInfo"]["showCountDesc"]
                    total = _parse_show_count_desc(_decode_text(desc, digit_map))
                if not results or total <= 0:
                    raise RuntimeError("猫眼未返回有效的影片场次或大盘总场次")
                logger.info("猫眼 %s：%d 部影片，总场次 %d", requested_date, len(movies), total)
                return results, total
            finally:
                browser.close()


def _read_session() -> dict:
    try:
        response = requests.get(_SESSION, timeout=20)
        response.raise_for_status()
        match = re.search(
            r'"pageData":\s*(\{"movieRankList":\[.*?\],"totalCount":\d+\})',
            response.text,
        )
        if match is None:
            raise ValueError("缺少 pageData.movieRankList / totalCount")
        data = json.loads(match.group(1))
        if not data["movieRankList"] or data["totalCount"] <= 0:
            raise ValueError("排片数据为空")
        return data
    except Exception as exc:
        raise RuntimeError(f"猫眼今日排片页读取失败: {exc}") from exc


def _launch_browser(playwright):
    for options in ({}, {"channel": "chrome"}, {"channel": "msedge"}):
        if not options and not Path(playwright.chromium.executable_path).exists():
            continue
        try:
            return playwright.chromium.launch(headless=True, **options)
        except Exception as exc:
            logger.warning(
                "启动浏览器 %s 失败: %s",
                options or "Playwright Chromium",
                str(exc).splitlines()[0],
            )
    raise RuntimeError("无法启动 Playwright Chromium、系统 Chrome 或 Edge")


def _read_dashboard(browser, api_date: str):
    page = browser.new_page(viewport={"width": 375, "height": 812})
    url = f"{_DASHBOARD}?date={api_date}"
    expected_date = api_date.replace("-", "")
    try:
        with page.expect_response(
            lambda response: (
                "/i/api/encrypt/dashboard-ajax/movie" in response.url
                and (
                    f"showDate={expected_date}" in response.url
                    or (api_date == dt_date.today().isoformat()
                        and "showDate=" not in response.url)
                )
                and response.status == 200
            ),
            timeout=30000,
        ) as response_info:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        data = response_info.value.json()
        movies = data["movieList"]["list"]
        if not movies:
            raise ValueError("影片列表为空")
        return page, data
    except Exception as exc:
        page.close()
        raise RuntimeError(f"猫眼 {api_date} 大盘读取失败: {exc}") from exc


def _glyphs(data: dict) -> list[str]:
    return sorted({
        char
        for movie in data["movieList"]["list"]
        for char in str(movie["showCount"])
        if not char.isascii() or not char.isdigit()
    })


def _learn_digits(data: dict, session_movies: list[dict]) -> dict[str, str]:
    glyphs = _glyphs(data)
    if len(glyphs) != 10:
        raise RuntimeError(f"猫眼数字字体格式变化：识别到 {len(glyphs)} 个字形")
    votes = {glyph: [0] * 10 for glyph in glyphs}
    counts = {movie["movieName"]: movie["count"] for movie in session_movies}
    for movie in data["movieList"]["list"]:
        name = movie["movieInfo"]["movieName"]
        if name not in counts:
            continue
        raw, plain = str(movie["showCount"]), str(counts[name])
        if len(raw) == len(plain):
            for glyph, digit in zip(raw, plain):
                if glyph in votes:
                    votes[glyph][int(digit)] += 1

    @lru_cache(None)
    def assign(index: int, used: int):
        if index == len(glyphs):
            return 0, ()
        best = (-1, ())
        for digit in range(10):
            if not used & (1 << digit):
                score, tail = assign(index + 1, used | (1 << digit))
                candidate = (score + votes[glyphs[index]][digit], (digit,) + tail)
                if candidate[0] > best[0]:
                    best = candidate
        return best

    _, digits = assign(0, 0)
    mapping = {glyph: str(digit) for glyph, digit in zip(glyphs, digits)}
    for glyph, digit in mapping.items():
        agreement = votes[glyph][int(digit)]
        opposition = max(votes[glyph][:int(digit)] + votes[glyph][int(digit) + 1:])
        if agreement < 1 or agreement <= opposition:
            raise RuntimeError("猫眼今日排片与大盘数字字体无法可靠对应")
    return mapping


def _render_digits(page, data: dict, mapping: dict[str, str]) -> dict[str, str]:
    font_match = re.search(r'url\("?(//[^")]+\.woff)"?\)', data["fontStyle"])
    if font_match is None:
        raise RuntimeError("猫眼响应缺少数字字体文件")
    font_url = "https:" + font_match.group(1)
    bitmaps = page.evaluate(
        """async ({chars, url}) => {
            const face = new FontFace('codex-digit-font', `url("${url}")`);
            await face.load();
            document.fonts.add(face);
            const result = {};
            for (const ch of chars) {
                const canvas = document.createElement('canvas');
                canvas.width = 80; canvas.height = 90;
                const ctx = canvas.getContext('2d');
                ctx.font = '64px codex-digit-font';
                ctx.fillText(ch, 8, 70);
                const rgba = ctx.getImageData(0, 0, 80, 90).data;
                let bits = '';
                for (let i = 3; i < rgba.length; i += 4)
                    bits += rgba[i] > 127 ? '1' : '0';
                result[ch] = bits;
            }
            return result;
        }""",
        {"chars": list(mapping), "url": font_url},
    )
    return {mapping[char]: bitmap for char, bitmap in bitmaps.items()}


def _match_digits(page, data: dict, templates: dict[str, str]) -> dict[str, str]:
    glyphs = _glyphs(data)
    bitmaps = _render_digits(page, data, {glyph: glyph for glyph in glyphs})
    mapping = {}
    for glyph, bitmap in bitmaps.items():
        distances = sorted(
            (sum(a != b for a, b in zip(bitmap, template)), digit)
            for digit, template in templates.items()
        )
        if distances[0][0] > 250 or distances[1][0] - distances[0][0] < 50:
            raise RuntimeError("猫眼数字字形无法可靠解码")
        mapping[glyph] = distances[0][1]
    if len(mapping) != 10 or len(set(mapping.values())) != 10:
        raise RuntimeError("猫眼数字字体映射不完整")
    return mapping


def _decode_text(raw: str, mapping: dict[str, str]) -> str:
    return "".join(mapping.get(char, char) for char in str(raw))


def _decode_number(raw: str, mapping: dict[str, str]) -> int:
    value = _decode_text(raw, mapping).replace(",", "")
    if not value.isdigit():
        raise RuntimeError(f"猫眼场次数字无法解码: {raw!r}")
    return int(value)


def _to_api_date(date_str: str) -> str:
    parts = date_str.strip().split(".")
    month = int(parts[0])
    day = int(parts[1])
    return dt_date(dt_date.today().year, month, day).isoformat()


def _parse_show_count_desc(desc: str) -> int:
    match = re.fullmatch(r"([\d,.]+)\s*(万|场)?", desc.strip())
    if match is None:
        raise RuntimeError(f"猫眼总场次格式变化: {desc!r}")
    value = float(match.group(1).replace(",", ""))
    return int(value * 10000 if match.group(2) == "万" else value)
