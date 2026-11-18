from scripts.build.reader_fragment_links import repair_contents, restore_aside_ids


def test_missing_fragment_uses_the_published_chapter_or_heading():
    markup = (
        '<a href="#6-函数">6. 函数</a><a href="#附录-f">附录 F</a>'
        '<a href="#过期锚点">本节标题</a><h2 id="actual">本节标题</h2>'
    )
    result = repair_contents(markup, ["函数：参数与作用域", "附录 F：案例"])
    assert result == (
        '<a href="chapter-01.html">6. 函数</a><a href="chapter-02.html">附录 F</a>'
        '<a href="#actual">本节标题</a><h2 id="actual">本节标题</h2>'
    )


def test_keep_valid_ambiguous_and_illustrative_links():
    markup = (
        '<h2 id="existing">示例</h2><a href="#existing">函数</a><a href="#旧">函数</a>'
        "<script>const sample = '<a href=\"#旧\">示例</a>'</script>"
        '<pre><a href="#旧">示例</a></pre><!-- <a href="#旧">示例</a> -->'
    )
    assert repair_contents(markup, ["函数：参数", "函数：作用域"]) == markup


def test_restore_an_old_callout_without_duplicate_ids():
    markup = '<div class="aside aside-warn"><span class="aside-title">易错点</span></div><a href="#_6">易错点</a>'.encode()
    fixed = restore_aside_ids(markup)
    assert fixed.count(b'id="_6"') == 1
    assert restore_aside_ids(fixed) == fixed
