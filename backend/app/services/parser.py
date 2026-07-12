import re
from dataclasses import dataclass, field

from charset_normalizer import from_bytes


# 第N章 / 节 / 回 ...
CN_DI_CHAPTER_RE = re.compile(
    r"^\s*"
    r"第\s*[0-9零〇一二三四五六七八九十百千万两壹贰叁肆伍陆柒捌玖拾佰仟]+\s*[章节回节卷集部篇]"
    r"(?:\s*[：:、\-—]\s*|\s+)"
    r"(.+?)?"
    r"\s*$"
)
# Bare 第N章 without subtitle
CN_DI_CHAPTER_BARE_RE = re.compile(
    r"^\s*"
    r"第\s*[0-9零〇一二三四五六七八九十百千万两壹贰叁肆伍陆柒捌玖拾佰仟]+\s*[章节回节卷集部篇]"
    r"\s*$"
)

# Special chapter names: alone, or separator/space + short subtitle (not glued body text).
CN_SPECIAL_CHAPTER_RE = re.compile(
    r"^\s*"
    r"(?:序章|楔子|引子|前言|后记|终章|尾声|番外(?:篇)?)"
    r"(?:"
    r"\s*[：:、\-—]\s*.+"
    r"|"
    r"\s+.+"
    r")?"
    r"\s*$"
)

# Numbered chapters: "1、初遇" / "2. 少年" — require non-empty title, reject decimals.
CN_NUMBERED_DUN_RE = re.compile(
    r"^\s*"
    r"[0-9]{1,5}\s*、\s*"
    r"(.+)"
    r"\s*$"
)
CN_NUMBERED_DOT_RE = re.compile(
    r"^\s*"
    r"[0-9]{1,5}\s*[.．]\s*"
    r"(?!\d)"  # reject 1.1 / 12.34
    r"(.+)"
    r"\s*$"
)

EN_CHAPTER_RE = re.compile(r"^\s*Chapter\s+\d+\b.*$", re.IGNORECASE)
EN_ROMAN_CHAPTER_RE = re.compile(r"^\s*CHAPTER\s+[IVXLCDM]+\b.*$")

# Kept for callers/tests that inspect pattern list length/order.
CHAPTER_PATTERNS = [
    CN_DI_CHAPTER_BARE_RE,
    CN_DI_CHAPTER_RE,
    CN_SPECIAL_CHAPTER_RE,
    CN_NUMBERED_DUN_RE,
    CN_NUMBERED_DOT_RE,
    EN_CHAPTER_RE,
    EN_ROMAN_CHAPTER_RE,
]

SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;…])")
SENTENCE_END_RE = re.compile(r"[。！？!?…]")

# Mojibake / garbage markers commonly seen after wrong decoding.
MOJIBAKE_MARKERS = ("锟斤拷", "烫烫烫", "屯屯屯", "ï¿½")
MOJIBAKE_LATIN_RE = re.compile(r"[ÃÂåæç]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
CN_PUNCT_RE = re.compile(r"[，。！？；：、“”‘’（）《》【】…—·]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
HIGH_BYTE_GARBAGE_RE = re.compile(r"[\u0080-\u00ff]")
# Common traditional-only / traditional-leaning characters (heuristic).
TRADITIONAL_CHARS = set("國們來說為這過來時會與對現發學經體書長東門開關問題麼還應裡總點樣處")


@dataclass
class ParsedChapter:
    title: str
    segments: list[str]


@dataclass
class TextQualityIssue:
    code: str
    message: str
    severity: str  # info|warning|error
    sample: str | None = None
    count: int = 0


@dataclass
class ParseResult:
    chapters: list[ParsedChapter]
    encoding: str | None = None
    issues: list[TextQualityIssue] = field(default_factory=list)
    has_errors: bool = False
    has_mojibake: bool = False


def _normalize_encoding_name(encoding: str | None) -> str:
    if not encoding:
        return "utf-8"
    encoding = encoding.lower().replace("-", "_")
    if encoding in {"gb2312", "gbk", "gb18030", "hz_gb_2312"}:
        return "gbk"
    if encoding in {"utf_8", "utf8"}:
        return "utf-8"
    if encoding in {"utf_8_sig", "utf8_sig"}:
        return "utf-8-sig"
    if encoding in {"big5", "big5_hkscs", "cp950"}:
        return "big5"
    return encoding.replace("_", "-")


def detect_encoding(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    result = from_bytes(data).best()
    if result is None:
        return "utf-8"
    return _normalize_encoding_name(result.encoding)


def _traditional_ratio(text: str) -> float:
    if not text:
        return 0.0
    sample = text[:5000]
    cjk = CJK_RE.findall(sample)
    if not cjk:
        return 0.0
    trad = sum(1 for ch in cjk if ch in TRADITIONAL_CHARS)
    return trad / len(cjk)


def _score_decoded_text(text: str) -> float:
    """Higher is better. Penalize replacement chars and mojibake patterns."""
    if not text:
        return -100.0

    sample = text[:20000]
    n = len(sample)
    cjk = len(CJK_RE.findall(sample))
    punct = len(CN_PUNCT_RE.findall(sample))
    replacement = sample.count("\ufffd")
    marker_hits = sum(sample.count(m) for m in MOJIBAKE_MARKERS)
    latin_mojibake = len(MOJIBAKE_LATIN_RE.findall(sample))
    control = len(CONTROL_RE.findall(sample))
    high_garbage = len(HIGH_BYTE_GARBAGE_RE.findall(sample))
    question = sample.count("?")

    score = 0.0
    score += (cjk / n) * 120.0
    score += (punct / n) * 40.0
    score -= (replacement / n) * 400.0
    score -= marker_hits * 25.0
    score -= latin_mojibake * 2.0
    score -= (control / n) * 200.0

    # Mixed CJK with latin-1 mojibake is a strong negative signal.
    if cjk > 0 and (latin_mojibake >= 3 or high_garbage / max(cjk, 1) > 0.35):
        score -= 40.0
    if cjk > 20 and question / n > 0.08:
        score -= 30.0
    if cjk == 0 and high_garbage / n > 0.25:
        score -= 20.0
    return score


def _try_decode(data: bytes, encoding: str) -> str | None:
    try:
        return data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return None


def decode_text(data: bytes) -> tuple[str, str]:
    """Decode bytes with quality scoring.

    Prefer a valid UTF-8 decode when available so mojibake markers and
    replacement chars are preserved for quality analysis, instead of being
    reinterpreted as unrelated CJK via GBK/Big5.
    Product default is simplified Chinese novels: bias toward gbk/gb18030.
    """
    preferred = detect_encoding(data)

    # Probe simplified/traditional hints without committing to big5 yet.
    gbk_probe = _try_decode(data, "gbk") or _try_decode(data, "gb18030") or ""
    trad_ratio = _traditional_ratio(gbk_probe)
    allow_big5 = preferred == "big5" or trad_ratio >= 0.08

    candidates: list[str] = []
    base = [preferred, "utf-8-sig", "utf-8", "gbk", "gb18030"]
    if allow_big5:
        base.append("big5")
    base.append("latin-1")
    for enc in base:
        if enc and enc not in candidates:
            candidates.append(enc)

    scored: list[tuple[str, str, float]] = []
    for enc in candidates:
        text = _try_decode(data, enc)
        if text is None:
            continue
        score = _score_decoded_text(text)
        if enc == preferred:
            score += 3.0
        if enc in {"utf-8", "utf-8-sig"}:
            # Valid UTF-8 is usually intentional for modern novel uploads.
            score += 18.0
            if "\ufffd" not in text and not any(m in text for m in MOJIBAKE_MARKERS):
                score += 8.0
        if enc in {"gbk", "gb18030"}:
            # Simplified-Chinese prior for short/noisy samples.
            score += 12.0
        if enc == "big5":
            # Only competitive when traditional features are clear.
            score += 8.0 if trad_ratio >= 0.08 or preferred == "big5" else -25.0
            if trad_ratio < 0.03 and preferred != "big5":
                score -= 20.0
        scored.append((text, enc, score))

    if not scored:
        return data.decode("utf-8", errors="replace"), "utf-8"

    # Strict UTF-8 success means the bytes really are UTF-8 (including any
    # literal U+FFFD or mojibake markers already present in the file). Prefer it
    # over GBK/Big5 reinterpretations that can "clean" garbage into random CJK.
    utf8_candidates = [s for s in scored if s[1] in {"utf-8", "utf-8-sig"}]
    if utf8_candidates:
        utf8_best = max(utf8_candidates, key=lambda x: x[2])
        return utf8_best[0], utf8_best[1]

    # Close scores: prefer gbk/gb18030 over big5 for this product.
    best = max(scored, key=lambda x: x[2])
    close = [s for s in scored if abs(s[2] - best[2]) <= 8.0]
    if len(close) > 1:
        for preferred_enc in ("gbk", "gb18030"):
            for item in close:
                if item[1] == preferred_enc:
                    return item[0], item[1]
        # Avoid big5 ties when a CJK-capable simplified decode exists.
        non_big5 = [s for s in close if s[1] != "big5"]
        if non_big5:
            return max(non_big5, key=lambda x: x[2])[0:2]
    return best[0], best[1]


def _subtitle_ok(subtitle: str | None, *, max_len: int = 40, allow_empty: bool = True) -> bool:
    if subtitle is None:
        return allow_empty
    title = subtitle.strip()
    if not title:
        return allow_empty
    if len(title) > max_len:
        return False
    # Reject list-like / full sentence titles.
    if SENTENCE_END_RE.search(title):
        return False
    return True


def is_chapter_title(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False

    if EN_CHAPTER_RE.match(stripped) or EN_ROMAN_CHAPTER_RE.match(stripped):
        return True

    if CN_DI_CHAPTER_BARE_RE.match(stripped):
        return True

    m = CN_DI_CHAPTER_RE.match(stripped)
    if m:
        # Pattern allows optional trailing title after space/separator.
        # Reconstruct: if there is trailing content, validate as subtitle.
        # CN_DI_CHAPTER_RE always has group 1 for trailing title part.
        return _subtitle_ok(m.group(1), max_len=40, allow_empty=True)

    m = CN_SPECIAL_CHAPTER_RE.match(stripped)
    if m:
        # Reject glued body like "序章开始了" / "前言部分":
        # special name must be whole token; any tail needs space or separator.
        # Regex already enforces that; additionally cap subtitle length / sentence ends.
        # Extract tail after special head.
        head = re.match(
            r"^\s*(序章|楔子|引子|前言|后记|终章|尾声|番外(?:篇)?)\s*(.*)$",
            stripped,
        )
        if not head:
            return False
        tail = (head.group(2) or "").strip()
        if not tail:
            return True
        # Tail should start with separator or was space-separated (already stripped).
        # After strip, separator may remain as first char.
        if tail[0] in {"：", ":", "、", "-", "—"}:
            tail = tail[1:].strip()
        return _subtitle_ok(tail, max_len=40, allow_empty=False)

    m = CN_NUMBERED_DUN_RE.match(stripped)
    if m:
        return _subtitle_ok(m.group(1), max_len=40, allow_empty=False)

    m = CN_NUMBERED_DOT_RE.match(stripped)
    if m:
        return _subtitle_ok(m.group(1), max_len=40, allow_empty=False)

    return False


def split_segments(text: str, max_chars: int = 280, min_chars: int = 40) -> list[str]:
    text = text.strip()
    if not text:
        return []

    pieces = [p.strip() for p in SENTENCE_SPLIT.split(text) if p and p.strip()]
    if not pieces:
        pieces = [text]

    segments: list[str] = []
    buf = ""
    for piece in pieces:
        if not buf:
            buf = piece
            continue
        if len(buf) + len(piece) <= max_chars:
            buf += piece
        else:
            if len(buf) < min_chars and segments:
                segments[-1] = segments[-1] + buf
            else:
                segments.append(buf)
            buf = piece
    if buf:
        if len(buf) < min_chars and segments:
            segments[-1] = segments[-1] + buf
        else:
            segments.append(buf)

    final: list[str] = []
    for seg in segments:
        if len(seg) <= max_chars * 2:
            final.append(seg)
            continue
        for i in range(0, len(seg), max_chars):
            chunk = seg[i : i + max_chars].strip()
            if chunk:
                final.append(chunk)
    return final


def parse_book_text(raw: str) -> list[ParsedChapter]:
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chapters: list[ParsedChapter] = []
    current_title = "正文"
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_title
        body = "\n".join(current_lines).strip()
        if not body and not chapters:
            return
        segments = split_segments(body) if body else []
        if segments or not chapters:
            chapters.append(ParsedChapter(title=current_title, segments=segments or [""]))
        current_lines = []

    for line in lines:
        if is_chapter_title(line):
            flush()
            current_title = line.strip()
        else:
            current_lines.append(line)
    flush()

    if not chapters:
        segments = split_segments(raw)
        chapters = [ParsedChapter(title="正文", segments=segments or [raw.strip() or ""])]
    return chapters


def analyze_text_quality(text: str, encoding: str | None = None) -> list[TextQualityIssue]:
    issues: list[TextQualityIssue] = []
    if not text:
        issues.append(
            TextQualityIssue(
                code="empty_text",
                message="文本为空",
                severity="warning",
            )
        )
        return issues

    sample = text[:50000]
    n = max(len(sample), 1)
    cjk = len(CJK_RE.findall(sample))
    replacement = sample.count("\ufffd")
    marker_counts = {m: sample.count(m) for m in MOJIBAKE_MARKERS}
    marker_total = sum(marker_counts.values())
    latin_hits = len(MOJIBAKE_LATIN_RE.findall(sample))
    control = len(CONTROL_RE.findall(sample))
    questions = sample.count("?")
    high_garbage = len(HIGH_BYTE_GARBAGE_RE.findall(sample))

    if replacement > 0:
        severity = "error" if replacement / n >= 0.005 or replacement >= 5 else "warning"
        issues.append(
            TextQualityIssue(
                code="replacement_char",
                message=f"检测到解码替换字符（�）{replacement} 处",
                severity=severity,
                sample="�",
                count=replacement,
            )
        )

    if marker_total > 0:
        hit = next(m for m, c in marker_counts.items() if c > 0)
        issues.append(
            TextQualityIssue(
                code="mojibake_marker",
                message=f"检测到典型乱码标记（如 {hit}）",
                severity="error",
                sample=hit,
                count=marker_total,
            )
        )

    # Latin mojibake mixed into Chinese text (e.g. UTF-8 misread as latin-1).
    if cjk > 0 and latin_hits >= 4 and (latin_hits / max(cjk, 1) >= 0.05 or latin_hits >= 12):
        issues.append(
            TextQualityIssue(
                code="mojibake_latin_mix",
                message="中文与典型乱码拉丁字符混排，疑似编码错误",
                severity="warning",
                sample=sample[max(0, sample.find("Ã")) : max(0, sample.find("Ã")) + 24] or None,
                count=latin_hits,
            )
        )

    if cjk > 30 and questions / n >= 0.06:
        issues.append(
            TextQualityIssue(
                code="excess_question_marks",
                message="CJK 文本中问号比例异常偏高",
                severity="warning",
                sample="?",
                count=questions,
            )
        )

    if control > 0 and control / n >= 0.01:
        issues.append(
            TextQualityIssue(
                code="control_chars",
                message=f"检测到异常控制字符 {control} 处",
                severity="warning",
                count=control,
            )
        )

    # Nearly pure high-byte garbage with no chapter structure.
    chapter_like = any(is_chapter_title(line) for line in sample.splitlines()[:400])
    if cjk < max(8, n * 0.01) and high_garbage / n >= 0.2 and not chapter_like:
        issues.append(
            TextQualityIssue(
                code="decode_error",
                message="文本几乎无可读中文/章节结构，疑似编码错误",
                severity="error",
                count=high_garbage,
            )
        )

    # Aggregate mojibake flag for convenience callers.
    if any(i.code in {"replacement_char", "mojibake_marker", "mojibake_latin_mix", "decode_error"} for i in issues):
        if not any(i.code == "mojibake" for i in issues):
            severity = "error" if any(i.severity == "error" for i in issues) else "warning"
            issues.append(
                TextQualityIssue(
                    code="mojibake",
                    message="检测到乱码风险",
                    severity=severity,
                    count=sum(i.count for i in issues if i.code != "empty_text"),
                )
            )

    if encoding and encoding.lower() in {"latin-1", "iso-8859-1", "ascii"} and cjk == 0 and high_garbage / n > 0.15:
        issues.append(
            TextQualityIssue(
                code="suspect_encoding",
                message=f"当前编码 {encoding} 下文本可读性较差",
                severity="warning",
            )
        )

    return issues


def parse_book(data: bytes) -> ParseResult:
    text, encoding = decode_text(data)
    chapters = parse_book_text(text)
    issues = analyze_text_quality(text, encoding=encoding)
    has_errors = any(i.severity == "error" for i in issues)
    has_mojibake = any(
        i.code in {"mojibake", "mojibake_marker", "mojibake_latin_mix", "replacement_char", "decode_error"}
        for i in issues
    )
    return ParseResult(
        chapters=chapters,
        encoding=encoding,
        issues=issues,
        has_errors=has_errors,
        has_mojibake=has_mojibake,
    )


def format_parse_job_message(result: ParseResult) -> str:
    count = len(result.chapters)
    base = f"解析完成，共 {count} 章"
    if result.has_errors and result.has_mojibake:
        return f"{base}；疑似编码错误"
    if result.has_mojibake:
        return f"{base}；检测到乱码风险"
    if result.has_errors:
        return f"{base}；检测到解析错误"
    return base


SUSPECT_STORED_ENCODINGS = frozenset({
    "latin-1",
    "latin1",
    "iso-8859-1",
    "iso8859-1",
    "cp1252",
    "windows-1252",
    "ascii",
})


def _is_suspect_stored_encoding(encoding: str | None) -> bool:
    if not encoding:
        return False
    normalized = encoding.lower().replace("_", "-").replace(" ", "")
    compact = normalized.replace("-", "")
    return normalized in SUSPECT_STORED_ENCODINGS or compact in {
        "latin1",
        "iso88591",
        "cp1252",
        "windows1252",
        "ascii",
    }


def recover_bytes_from_text(text: str, stored_encoding: str | None = None) -> bytes | None:
    """Recover original bytes when text was mis-decoded as a single-byte encoding.

    Typical case: GBK/GB18030 bytes were decoded as latin-1/cp1252 and stored as
    Unicode code points U+0080..U+00FF. Re-encoding with latin-1 restores the
    original byte stream so decode_text/parse_book can re-detect encoding.
    """
    if not text:
        return None

    sample = text[:50000]
    high = len(HIGH_BYTE_GARBAGE_RE.findall(sample))
    cjk = len(CJK_RE.findall(sample))
    n = max(len(sample), 1)
    high_ratio = high / n

    # Prefer recovery for known bad stored encodings, or when high-byte mojibake
    # dominates over readable CJK.
    suspect = _is_suspect_stored_encoding(stored_encoding)
    if not suspect and not (high >= 32 and high_ratio >= 0.08 and high > cjk * 2):
        return None

    try:
        return text.encode("latin-1")
    except UnicodeEncodeError:
        # Text already contains multi-byte Unicode; cannot reverse a pure
        # latin-1 mis-decode. Try cp1252 as a best-effort for Windows paths.
        try:
            return text.encode("cp1252", errors="strict")
        except UnicodeEncodeError:
            return None


def reparse_bytes(data: bytes) -> ParseResult:
    """Parse book bytes with the standard decode + chapter split pipeline."""
    return parse_book(data)


def rebuild_book_text_from_parts(chapters: list[tuple[str, list[str]]]) -> str:
    """Rebuild a near-original text from ordered (title, segment_texts).

    Segments were produced by split_segments from continuous text, so they must be
    concatenated without inserting extra separators (which would break multi-byte
    encodings after latin-1 recovery). Real chapter titles are emitted as lines;
    the synthetic single-chapter title "正文" is omitted.
    """
    blocks: list[str] = []
    for title, segments in chapters:
        body = "".join("" if seg is None else str(seg) for seg in segments)
        title_s = (title or "").strip()
        if title_s and not (title_s == "正文" and len(chapters) == 1):
            blocks.append(f"{title_s}\n{body}" if body else title_s)
        elif body:
            blocks.append(body)
    return "\n".join(blocks)


def _parse_result_score(result: ParseResult) -> float:
    """Higher is better when choosing among reparse candidates."""
    chapters = result.chapters or []
    chapter_count = len(chapters)
    sample_parts: list[str] = []
    for ch in chapters[:20]:
        sample_parts.append(ch.title or "")
        sample_parts.extend(ch.segments[:3])
    sample = "\n".join(sample_parts)[:20000]
    score = float(chapter_count) * 10.0
    score += _score_decoded_text(sample)
    if result.has_mojibake:
        score -= 50.0
    if result.has_errors:
        score -= 20.0
    if chapter_count == 1 and (chapters[0].title or "").strip() == "正文":
        score -= 30.0
    if result.encoding and result.encoding.lower() in {"gbk", "gb18030", "utf-8", "utf-8-sig"}:
        score += 5.0
    return score


def _decode_recovered_bytes(data: bytes) -> tuple[str, str]:
    """Decode recovered original bytes, allowing replace for damaged GBK streams.

    Segment splits on mis-decoded text can leave rare illegal GBK sequences after
    latin-1 round-trip; prefer the best-scoring CJK decode even with a few U+FFFD.
    """
    strict = decode_text(data)
    # If strict path already found a healthy CJK encoding, keep it.
    if strict[1] in {"gbk", "gb18030", "big5", "utf-8", "utf-8-sig"} and "\ufffd" not in strict[0][:20000]:
        # Still verify chapter structure isn't a single mojibake dump.
        if _score_decoded_text(strict[0]) > 0:
            return strict

    candidates: list[tuple[str, str, float]] = []
    # Include strict result.
    candidates.append((strict[0], strict[1], _score_decoded_text(strict[0])))

    for enc in ("gb18030", "gbk", "big5", "utf-8", "utf-8-sig"):
        try:
            text = data.decode(enc)
            score = _score_decoded_text(text) + 5.0
        except (UnicodeDecodeError, LookupError):
            try:
                text = data.decode(enc, errors="replace")
            except LookupError:
                continue
            # Penalize replacements but still allow recovery of mostly-valid novels.
            repl = text.count("\ufffd")
            n = max(len(text), 1)
            score = _score_decoded_text(text) - min(repl * 0.5, 40.0) - (repl / n) * 80.0
            # Only accept replace path when CJK content is clearly dominant.
            if len(CJK_RE.findall(text[:20000])) < 50:
                continue
        else:
            # strict success already scored above
            pass
        if enc in {"gbk", "gb18030"}:
            score += 15.0
        candidates.append((text, enc if enc != "gb18030" else "gbk", score))

    best = max(candidates, key=lambda x: x[2])
    # Normalize gb18030 label toward gbk product default when both work.
    enc = best[1]
    if enc == "gb18030":
        enc = "gbk"
    return best[0], enc


def reparse_stored_text(text: str, stored_encoding: str | None = None) -> ParseResult:
    """Reparse text already stored in DB, recovering mis-decoded bytes when needed.

    Strategy:
    1. Parse the stored Unicode text as-is.
    2. Recover original bytes via latin-1/cp1252 round-trip when encoding is
       suspect or high-byte mojibake dominates.
    3. Decode recovered bytes (strict, then quality-scored replace) and parse.
    4. Return the higher-scoring ParseResult.
    """
    issues = analyze_text_quality(text, encoding=stored_encoding)
    direct_chapters = parse_book_text(text)
    direct = ParseResult(
        chapters=direct_chapters,
        encoding=stored_encoding or "utf-8",
        issues=issues,
        has_errors=any(i.severity == "error" for i in issues),
        has_mojibake=any(
            i.code
            in {
                "mojibake",
                "mojibake_marker",
                "mojibake_latin_mix",
                "replacement_char",
                "decode_error",
                "suspect_encoding",
            }
            for i in issues
        ),
    )
    utf8_direct = parse_book(text.encode("utf-8"))

    candidates = [direct, utf8_direct]
    recovered = recover_bytes_from_text(text, stored_encoding)
    if recovered is None and _is_suspect_stored_encoding(stored_encoding):
        try:
            recovered = text.encode("latin-1")
        except UnicodeEncodeError:
            recovered = None
    if recovered is None:
        # Last resort: high-byte heavy text even without stored encoding label.
        sample = text[:50000]
        high = len(HIGH_BYTE_GARBAGE_RE.findall(sample))
        cjk = len(CJK_RE.findall(sample))
        if high >= 32 and high > cjk * 2:
            try:
                recovered = text.encode("latin-1")
            except UnicodeEncodeError:
                recovered = None

    if recovered is not None:
        recovered_text, recovered_enc = _decode_recovered_bytes(recovered)
        chapters = parse_book_text(recovered_text)
        recovered_issues = analyze_text_quality(recovered_text, encoding=recovered_enc)
        recovered_result = ParseResult(
            chapters=chapters,
            encoding=recovered_enc,
            issues=recovered_issues,
            has_errors=any(i.severity == "error" for i in recovered_issues),
            has_mojibake=any(
                i.code
                in {
                    "mojibake",
                    "mojibake_marker",
                    "mojibake_latin_mix",
                    "replacement_char",
                    "decode_error",
                }
                for i in recovered_issues
            ),
        )
        candidates.append(recovered_result)
        # Also keep standard parse_book path for clean recovered bytes.
        candidates.append(reparse_bytes(recovered))

    return max(candidates, key=_parse_result_score)
