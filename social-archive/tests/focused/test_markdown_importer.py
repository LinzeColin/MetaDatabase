from social_archive.connectors.markdown_watch import MarkdownWatchImporter

def test_markdown_watch_parses_frontmatter(settings):
    p=settings.watch_root/'item.md';p.write_text('---\nurl: https://www.wikipedia.org/a\nplatform: reddit\ntitle: 标题\n---\n正文',encoding='utf-8')
    items=MarkdownWatchImporter(settings.watch_root).scan(requested_root=None,platform_hint='import',relation_type='saved',limit=10)
    assert len(items)==1 and items[0].platform=='reddit' and items[0].title=='标题'

def test_markdown_watch_rejects_escape(settings,tmp_path):
    importer=MarkdownWatchImporter(settings.watch_root)
    try:importer.scan(requested_root=str(tmp_path/'elsewhere'),platform_hint='x',relation_type='saved',limit=1)
    except ValueError:pass
    else:raise AssertionError('path escape was accepted')
