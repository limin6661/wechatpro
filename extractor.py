import asyncio
import os
import re
import html
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# 默认请求头，尽量模拟常见浏览器，提升微信、微博等站点的可访问性
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    # requests 支持 gzip/deflate，br 需额外依赖，这里去掉以避免误解码
    "Accept-Encoding": "gzip, deflate",
}

# 打开 DEBUG_EXTRACT=1 时在控制台打印抓取/解析的关键信息，便于排查乱码或正文为空
DEBUG_EXTRACT = os.getenv("DEBUG_EXTRACT") == "1"
# 若设置 DEBUG_DUMP_HTML=路径，则将原始 HTML 保存到该文件，便于离线查看
DEBUG_DUMP_HTML = os.getenv("DEBUG_DUMP_HTML")

# 在正文提取前需要移除的节点，避免脚本、样式等噪声
NOISE_TAGS = {"script", "style", "noscript", "header", "footer", "nav", "aside"}

# 可能含正文的关键词，用于给候选节点加权
CONTENT_KEYWORDS = [
    "article",
    "content",
    "main",
    "post",
    "rich_media",
    "weibo",
    "detail",
    "text",
    "entry",
    "page",
]


@dataclass
class ExtractResult:
    title: str
    content: str


class ExtractError(Exception):
    """提取过程中出现的问题。"""


def fetch_html(url: str, timeout: int = 15) -> str:
    """请求目标 URL，返回 HTML 文本。"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        content_bytes = resp.content
        # 先看 headers，再用 apparent_encoding 兜底
        enc = resp.encoding
        if not enc or enc.lower() == "iso-8859-1":
            enc = resp.apparent_encoding or "utf-8"
        try:
            text = content_bytes.decode(enc, errors="replace")
        except Exception:
            text = content_bytes.decode("utf-8", errors="replace")
        if DEBUG_EXTRACT:
            print(f"[DEBUG] fetched {len(content_bytes)} bytes, encoding={enc}")
            print(f"[DEBUG] html head preview: {text[:400].replace(chr(10),' ')}")
        if DEBUG_DUMP_HTML:
            try:
                Path(DEBUG_DUMP_HTML).write_text(text, encoding="utf-8", errors="ignore")
                if DEBUG_EXTRACT:
                    print(f"[DEBUG] html dumped to {DEBUG_DUMP_HTML}")
            except Exception as dump_exc:
                if DEBUG_EXTRACT:
                    print(f"[DEBUG] dump failed: {dump_exc}")
        return text
    except requests.RequestException as exc:
        raise ExtractError(f"请求失败: {exc}") from exc


def clean_noise(soup: BeautifulSoup) -> None:
    """移除常见噪声标签，降低干扰。"""
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()


def pick_title(soup: BeautifulSoup) -> str:
    """优先返回页面 title，其次常见内容标题节点。"""
    meta_og = soup.find("meta", property="og:title")
    if meta_og and meta_og.get("content"):
        t = meta_og["content"].strip()
        if t:
            return t
    meta_name = soup.find("meta", attrs={"name": "title"})
    if meta_name and meta_name.get("content"):
        t = meta_name["content"].strip()
        if t:
            return t
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        # 微信标题常被写成“正文标题 - 公众号名”，截掉后缀
        if " - " in t and "mp.weixin.qq.com" in soup.decode():
            t = t.split(" - ", 1)[0].strip()
        return t
    # 微信文章标题节点 id=activity-name
    node = soup.select_one("#activity-name")
    if node and node.get_text(strip=True):
        return node.get_text(strip=True)
    for tag in ("h1", "h2"):
        node = soup.find(tag)
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
    return ""


def normalized_text(node) -> str:
    """提取节点可见文本，合并多余空行。"""
    text = node.get_text(separator="\n", strip=True)
    return re.sub(r"\n{2,}", "\n", text)


def pick_main_block(soup: BeautifulSoup) -> str:
    """根据长度与关键词加权选择正文节点。"""
    html_str = str(soup)
    if DEBUG_EXTRACT:
        print(f"[DEBUG] js_content in html: {'js_content' in html_str}")

    # 微信正文节点优先
    wx = soup.select_one("#js_content")
    if wx:
        text = normalized_text(wx)
        if len(text) > 40:
            if DEBUG_EXTRACT:
                print(f"[DEBUG] js_content len={len(text)}")
            return text
    # 微信正文备选：content 引号包裹的脚本变量里常有 HTML
    if "mp.weixin.qq.com" in html_str:
        m_js = re.search(r"var\\s+content\\s*=\\s*'(.+?)';", html_str, re.S)
        if m_js:
            raw = m_js.group(1)
            # 微信脚本里的内容有转义，需反转义再解析
            raw = raw.encode("utf-8").decode("unicode_escape")
            raw = html.unescape(raw)
            inner_soup = BeautifulSoup(raw, "lxml")
            text = normalized_text(inner_soup)
            if len(text) > 40:
                if DEBUG_EXTRACT:
                    print(f"[DEBUG] content var len={len(text)}")
                return text
        # 另一个变量名 __APP_MSG_CONTENT__
        m_app = re.search(r"__APP_MSG_CONTENT__\\s*=\\s*\"(.+?)\";", html_str, re.S)
        if m_app:
            raw = m_app.group(1)
            raw = raw.encode("utf-8").decode("unicode_escape")
            raw = html.unescape(raw)
            inner_soup = BeautifulSoup(raw, "lxml")
            text = normalized_text(inner_soup)
            if len(text) > 40:
                if DEBUG_EXTRACT:
                    print(f"[DEBUG] __APP_MSG_CONTENT__ len={len(text)}")
                return text
    # 微信兜底：直接用正则截出 js_content 再解析
    if "mp.weixin.qq.com" in html_str:
        m = re.search(r'id=\"js_content\".*?>(.*?)</div>', html_str, re.S | re.I)
        if m:
            inner = m.group(1)
            inner_soup = BeautifulSoup(inner, "lxml")
            text = normalized_text(inner_soup)
            if len(text) > 40:
                if DEBUG_EXTRACT:
                    print(f"[DEBUG] js_content regex len={len(text)}")
                return text

    candidates = []
    for node in soup.find_all(["article", "section", "main", "div", "body"]):
        text = normalized_text(node)
        if not text:
            continue
        if len(text) < 80:
            # 太短的区域通常不是正文
            continue

        attrs = " ".join(node.get("class", [])) + " " + (node.get("id") or "")
        weight = 1.0
        lowered = attrs.lower()
        if any(key in lowered for key in CONTENT_KEYWORDS):
            weight += 0.8
        if node.name in {"article", "main", "section"}:
            weight += 0.3

        score = len(text) * weight
        candidates.append((score, text))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    # 兜底用 body
    body = soup.body or soup
    return normalized_text(body)


def post_process_content(text: str) -> str:
    """格式化正文：裁剪、留出自然段间距。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n\n".join(lines)


def extract_article(url: str) -> ExtractResult:
    """整体提取流程：请求 HTML → 清洗 → 选取标题/正文。"""
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")
    clean_noise(soup)
    title = pick_title(soup)
    main_text = pick_main_block(soup)
    content = post_process_content(main_text)
    if DEBUG_EXTRACT:
        print(f"[DEBUG] title='{title}' content_len={len(content)}")
    return ExtractResult(title=title, content=content)


async def extract_article_async(url: str) -> ExtractResult:
    """异步封装，便于在 FastAPI 中使用。"""
    return await asyncio.to_thread(extract_article, url)
