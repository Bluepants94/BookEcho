from app.services.parser import (
    analyze_text_quality,
    decode_text,
    format_parse_job_message,
    is_chapter_title,
    parse_book,
    parse_book_text,
    recover_bytes_from_text,
    reparse_stored_text,
)


def test_chinese_and_english_chapter_titles():
    positives = [
        "第一章 序章",
        "第一章 开始",
        "第一章",
        "第001章 黑夜降临",
        "第十二章 风起",
        "1、初遇",
        "2. 少年",
        "序章",
        "楔子",
        "终章：归途",
        "番外篇",
        "Chapter 12 The Fall",
        "CHAPTER XIV",
    ]
    for title in positives:
        assert is_chapter_title(title), title

    negatives = [
        "这只是普通段落。",
        "他说：第一章其实是谎言。",
        "x" * 81,
        "序章开始了",
        "前言部分",
        "后记写道",
        "1、首先准备材料。",
        "2. 其次检查工具。",
        "12.34 数字",
        "3.14 圆周率",
        "1.1 小节",
        "1、",
    ]
    for title in negatives:
        assert not is_chapter_title(title), title


def test_list_body_not_split_into_chapters():
    text = "准备工作\n1、首先准备材料。\n2. 其次检查工具。\n完成。\n"
    chapters = parse_book_text(text)
    assert len(chapters) == 1
    body = "\n".join(chapters[0].segments)
    assert "首先准备材料" in body
    assert "其次检查工具" in body


def test_parse_book_text_splits_chapters():
    text = "第一章 开始\n你好。世界！继续。\n第二章 结束\n最后一句。\n"
    chapters = parse_book_text(text)
    assert len(chapters) == 2
    assert chapters[0].title == "第一章 开始"
    assert chapters[1].title == "第二章 结束"


def test_mojibake_detection_replacement_and_markers():
    text = "正文开始\ufffd继续" + ("锟斤拷" * 2)
    issues = analyze_text_quality(text)
    codes = {i.code for i in issues}
    assert "replacement_char" in codes or "mojibake_marker" in codes
    assert "mojibake" in codes

    result = parse_book(text.encode("utf-8"))
    assert result.has_mojibake
    assert "乱码" in format_parse_job_message(result) or "编码" in format_parse_job_message(result)


def test_gbk_bytes_decode_clean_chinese():
    raw = "第一章 开始\n黑夜降临，少年启程。\n".encode("gbk")
    text, encoding = decode_text(raw)
    assert "黑夜降临" in text
    assert encoding in {"gbk", "gb18030"}
    result = parse_book(raw)
    assert result.encoding in {"gbk", "gb18030"}
    assert not result.has_mojibake
    assert any(ch.title.startswith("第一章") for ch in result.chapters)
    assert format_parse_job_message(result) == f"解析完成，共 {len(result.chapters)} 章"


def test_short_gbk_not_misread_as_big5():
    samples = ["你好", "我是谁", "第一章\n他来了。"]
    for sample in samples:
        raw = sample.encode("gbk")
        text, encoding = decode_text(raw)
        assert encoding in {"gbk", "gb18030"}, (sample, encoding, text)
        assert text == sample, (sample, encoding, text)
        result = parse_book(raw)
        assert result.encoding in {"gbk", "gb18030"}
        assert not result.has_mojibake
        assert sample.split("\n")[0] in (
            "".join(seg for ch in result.chapters for seg in ch.segments) + " " + " ".join(ch.title for ch in result.chapters)
        ) or sample in "\n".join(
            [ch.title] + ch.segments for ch in result.chapters
        )


def test_recover_latin1_misdecoded_gbk():
    """GBK bytes mis-decoded as latin-1 should recover into multi-chapter text."""
    novel = (
        "第一章 异界小道士\n"
        "夜色如墨，少年推开道观木门。\n"
        "第二章 山门夜话\n"
        "清风拂过廊檐，铜铃轻响。\n"
        "第三章 初入江湖\n"
        "他背起包袱，踏上尘土飞扬的官道。\n"
    )
    raw = novel.encode("gbk")
    # Simulate historical bug: decode as latin-1 and persist that Unicode text.
    mojibake = raw.decode("latin-1")
    assert "第一章" not in mojibake

    recovered = recover_bytes_from_text(mojibake, stored_encoding="latin-1")
    assert recovered is not None
    assert recovered == raw

    result = reparse_stored_text(mojibake, stored_encoding="latin-1")
    assert result.encoding in {"gbk", "gb18030"}
    assert not result.has_mojibake
    assert len(result.chapters) >= 3
    titles = [ch.title for ch in result.chapters]
    assert any("第一章" in t and "异界小道士" in t for t in titles)
    assert any("第二章" in t for t in titles)
    body = "".join(seg for ch in result.chapters for seg in ch.segments)
    assert "少年推开道观木门" in body
    assert "铜铃轻响" in body


def test_reparse_stored_text_keeps_good_utf8():
    text = "第一章 开始\n黑夜降临。\n第二章 继续\n黎明将至。\n"
    result = reparse_stored_text(text, stored_encoding="utf-8")
    assert len(result.chapters) == 2
    assert result.chapters[0].title.startswith("第一章")
    assert "黑夜降临" in "".join(result.chapters[0].segments)
