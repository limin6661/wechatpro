import argparse
import os
import sys
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from extractor import ExtractError, extract_article, extract_article_async


class ExtractRequest(BaseModel):
    url: str


API_KEY = os.getenv("API_KEY")

class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="html2txt",
    version="0.1.0",
    description="输入 URL，返回标题与正文的简单提取服务。",
    default_response_class=Utf8JSONResponse,
)


def _ensure_api_key(header_key: Optional[str]) -> None:
    """若设置了 API_KEY 环境变量，则校验请求头。"""
    if API_KEY and header_key != API_KEY:
        raise HTTPException(status_code=401, detail="API Key 无效")


@app.post("/api/extract")
async def api_extract(
    payload: ExtractRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """HTTP 接口（POST）：输入 URL，返回标题与正文。"""
    _ensure_api_key(x_api_key)
    try:
        result = await extract_article_async(payload.url)
        return {"title": result.title, "content": result.content}
    except ExtractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
async def health_check():
    """健康检查，便于部署探活。"""
    return {"status": "ok"}


def cli_extract(url: str) -> int:
    """命令行模式：直接输出提取结果。"""
    try:
        result = extract_article(url)
    except ExtractError as exc:
        print(f"提取失败: {exc}", file=sys.stderr)
        return 1

    print("标题:")
    print(result.title or "(无标题)")
    print("\n正文:")
    print(result.content or "(无正文)")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="提取网页标题和正文（支持 HTTP API 与命令行）。"
    )
    parser.add_argument("--url", help="要提取的网页 URL")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="以 HTTP 服务方式运行（默认 0.0.0.0:8000）",
    )
    parser.add_argument("--host", default="0.0.0.0", help="服务监听地址")
    parser.add_argument("--port", type=int, default=8000, help="服务监听端口")
    args = parser.parse_args()

    if args.url:
        sys.exit(cli_extract(args.url))

    if args.serve or not args.url:
        uvicorn.run("main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
