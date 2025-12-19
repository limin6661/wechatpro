# html2txt

小型提取服务：输入网页 URL，返回标题和正文。
支持命令行与 HTTP API，便于 Win11 本地测试与 Zeabur 部署。

## 功能特点

- 模拟浏览器 UA，请求主流站点（含微信公众号、头条、微博等资讯页）。
- HTTP 接口 `/api/extract`（POST，JSON 传 url，可选 X-API-Key）与命令行模式，标题/正文分块输出。
- BeautifulSoup + 加权策略选正文，自动清洗脚本/导航噪声。
- 健康检查 `/health`，方便部署探活。

## 本地运行（Win11）

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# HTTP 服务
python main.py --serve --port 8000
# 访问（POST）
curl -X POST "http://127.0.0.1:8000/api/extract" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: <你的key，可选>" ^
  -d "{\"url\":\"https://example.com\"}"

# 直接命令行提取
python main.py --url "https://example.com"
```

## Zeabur 部署步骤

1. 新建项目选择 Python 模板或通用容器。
2. 代码推送到仓库后在 Zeabur 连接该仓库。
3. 构建命令：`pip install -r requirements.txt`  
   启动命令：`uvicorn main:app --host 0.0.0.0 --port $PORT`
4. 部署后通过 `${ZEABUR_DOMAIN}/api/extract` POST 调用。

## API 示例

```bash
curl -X POST "http://127.0.0.1:8000/api/extract" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <你的key，可选>" \
  -d '{"url":"https://mp.weixin.qq.com/s/xxxx"}'

# 返回
# {
#   "title": "文章标题",
#   "content": "正文内容……"
# }
```

## 目录说明

- main.py：FastAPI 入口，提供 HTTP 接口与 CLI。
- extractor.py：核心提取逻辑（请求、解析、正文选择）。
- tests/：样例测试，确保提取逻辑可用。
- requirements.txt：依赖列表。

## 质量与边界

- 针对微信、微博等可能的反爬限制已添加常见 UA/Accept-Language，但若需登录或验证码的页面仍可能失败，需在上游获取可直接访问的公开链接。
- 提取算法为轻量加权（正文长度 + 关键词），适合大多数资讯类文章；若需更高精度可替换为 Readability 等更重算法。
- 网络异常、超时会返回 400；可在 extractor.py 中调整超时时间或补充代理配置。
