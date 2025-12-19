import extractor


def test_extract_article_with_sample(monkeypatch):
    html = """
    <html>
      <head>
        <title>示例标题</title>
      </head>
      <body>
        <div class="header">导航</div>
        <article class="rich_media">
          <h1>备用标题</h1>
          <p>正文第一段。</p>
          <p>正文第二段，包含更多内容用于评估长度。</p>
        </article>
        <div class="footer">尾部</div>
      </body>
    </html>
    """

    monkeypatch.setattr(extractor, "fetch_html", lambda url, timeout=15: html)
    result = extractor.extract_article("http://example.com")

    assert result.title == "示例标题"
    assert "正文第一段" in result.content
    assert "正文第二段" in result.content


def test_pick_title_without_head_title():
    html = """
    <html>
      <body>
        <h1>文章主标题</h1>
        <div>段落</div>
      </body>
    </html>
    """
    soup = extractor.BeautifulSoup(html, "lxml")
    assert extractor.pick_title(soup) == "文章主标题"
