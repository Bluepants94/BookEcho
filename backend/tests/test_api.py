import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret"
os.environ.pop("BOOTSTRAP_ADMIN_USERNAME", None)
os.environ.pop("BOOTSTRAP_ADMIN_PASSWORD", None)

# Isolate uploaded book files under a temp data dir for tests.
_TEST_DATA_DIR = Path(__file__).resolve().parent / "_tmp_data"
_TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DATA_DIR"] = str(_TEST_DATA_DIR)

from app.config import get_settings

get_settings.cache_clear()

from app.db import Base, get_db
from app.main import app
from app.services.parser import is_chapter_title, parse_book, parse_book_text


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        c.get("/api/health")
        yield c
    app.dependency_overrides.clear()


def _register(client: TestClient, username: str, password: str = "password123", invite_code: str | None = None):
    payload = {"username": username, "password": password}
    if invite_code is not None:
        payload["invite_code"] = invite_code
    return client.post("/api/auth/register", json=payload)


def _login(client: TestClient, username: str, password: str = "password123") -> str:
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _promote(username: str):
    db = TestingSessionLocal()
    from app.models import User, UserRole

    u = db.query(User).filter(User.username == username).first()
    u.role = UserRole.admin.value
    db.commit()
    db.close()


def test_registration_matrix_disabled(client: TestClient):
    assert _register(client, "admin1").status_code == 201
    _promote("admin1")
    admin_token = _login(client, "admin1")
    resp = client.put(
        "/api/admin/settings",
        headers=_auth(admin_token),
        json={"registration_enabled": False, "invite_required": False},
    )
    assert resp.status_code == 200
    denied = _register(client, "user_x")
    assert denied.status_code == 403
    assert "未开放注册" in denied.json()["detail"]


def test_registration_matrix_invite(client: TestClient):
    assert _register(client, "admin2").status_code == 201
    _promote("admin2")
    admin_token = _login(client, "admin2")
    resp = client.put(
        "/api/admin/settings",
        headers=_auth(admin_token),
        json={"registration_enabled": True, "invite_required": True, "invite_code": "INVITE-OK"},
    )
    assert resp.status_code == 200
    bad = _register(client, "user_bad", invite_code="WRONG")
    assert bad.status_code == 403
    good = _register(client, "user_good", invite_code="INVITE-OK")
    assert good.status_code == 201


def test_book_private_only_and_delete(client: TestClient):
    assert _register(client, "alice").status_code == 201
    assert _register(client, "bob").status_code == 201
    alice = _login(client, "alice")
    bob = _login(client, "bob")

    content = "第一章 开端\n这是第一段。这是第二句！\n第二章 发展\n继续阅读。\n".encode("utf-8")
    up = client.post(
        "/api/books",
        headers=_auth(alice),
        files={"file": ("demo.txt", content, "text/plain")},
        data={"title": "Demo", "visibility": "public"},  # public ignored
    )
    assert up.status_code == 201, up.text
    book = up.json()
    book_id = book["id"]
    assert book.get("visibility") == "private" or book.get("is_public") is False

    assert client.get(f"/api/books/{book_id}", headers=_auth(alice)).status_code == 200
    assert client.get(f"/api/books/{book_id}", headers=_auth(bob)).status_code == 403

    # bookshelf only own books
    mine = client.get("/api/books?scope=mine", headers=_auth(alice)).json()
    assert any(b["id"] == book_id for b in mine)
    bob_list = client.get("/api/books", headers=_auth(bob)).json()
    assert all(b["id"] != book_id for b in bob_list)

    # bob cannot delete
    assert client.delete(f"/api/books/{book_id}", headers=_auth(bob)).status_code == 403
    # owner can delete
    assert client.delete(f"/api/books/{book_id}", headers=_auth(alice)).status_code == 200
    assert client.get(f"/api/books/{book_id}", headers=_auth(alice)).status_code == 404


def test_admin_cannot_be_demoted(client: TestClient):
    assert _register(client, "rootadmin").status_code == 201
    _promote("rootadmin")
    assert _register(client, "staff").status_code == 201
    _promote("staff")
    root = _login(client, "rootadmin")
    users = client.get("/api/admin/users", headers=_auth(root)).json()
    staff = next(u for u in users if u["username"] == "staff")
    # demote staff admin -> forbidden because admin cannot demote
    resp = client.patch(
        f"/api/admin/users/{staff['id']}",
        headers=_auth(root),
        json={"role": "user"},
    )
    assert resp.status_code == 400
    assert "不可降级" in resp.json()["detail"]


def test_change_password(client: TestClient):
    assert _register(client, "carol", password="password123").status_code == 201
    token = _login(client, "carol", "password123")
    bad = client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"old_password": "wrong", "new_password": "newpass1"},
    )
    assert bad.status_code == 400
    ok = client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"old_password": "password123", "new_password": "newpass1"},
    )
    assert ok.status_code == 200
    assert client.post(
        "/api/auth/login",
        data={"username": "carol", "password": "newpass1"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ).status_code == 200


def test_progress_endpoints(client: TestClient):
    assert _register(client, "dave").status_code == 201
    token = _login(client, "dave")
    content = "第一章\n内容一二三。\n".encode("utf-8")
    up = client.post(
        "/api/books",
        headers=_auth(token),
        files={"file": ("c.txt", content, "text/plain")},
        data={"title": "C"},
    )
    book_id = up.json()["id"]
    detail = client.get(f"/api/books/{book_id}", headers=_auth(token)).json()
    chapter_id = detail["chapters"][0]["id"]
    put = client.put(
        f"/api/progress/{book_id}",
        headers=_auth(token),
        json={"chapter_id": chapter_id, "segment_index": 0, "position_seconds": 12.5},
    )
    assert put.status_code == 200
    got = client.get(f"/api/progress/{book_id}", headers=_auth(token))
    assert got.status_code == 200
    assert got.json()["position_seconds"] == 12.5


def test_parser_unit():
    assert is_chapter_title("第一章 序章")
    assert is_chapter_title("Chapter 12 The Fall")
    assert not is_chapter_title("这只是普通段落。")
    for title in [
        "第001章 黑夜降临",
        "第十二章 风起",
        "1、初遇",
        "序章",
        "终章：归途",
        "番外篇",
        "2. 少年",
        "第一章",
    ]:
        assert is_chapter_title(title), title
    text = "第一章 开始\n你好。世界！继续。\n第二章 结束\n最后一句。\n"
    chapters = parse_book_text(text)
    assert len(chapters) == 2

    bad = "锟斤拷" * 3 + "\n这是正文\ufffd继续"
    result = parse_book(bad.encode("utf-8"))
    assert result.has_mojibake
    assert any(i.code in {"mojibake", "mojibake_marker", "replacement_char"} for i in result.issues)

    gbk_text = "第一章 开始\n你好世界。\n"
    gbk_bytes = gbk_text.encode("gbk")
    gbk_result = parse_book(gbk_bytes)
    assert "你好世界" in "".join(seg for ch in gbk_result.chapters for seg in ch.segments)
    assert not gbk_result.has_mojibake


def test_tts_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    assert _register(client, "erin").status_code == 201
    token = _login(client, "erin")
    content = "第一章\n朗读这一段文字。\n".encode("utf-8")
    up = client.post(
        "/api/books",
        headers=_auth(token),
        files={"file": ("t.txt", content, "text/plain")},
        data={"title": "T"},
    )
    book_id = up.json()["id"]
    detail = client.get(f"/api/books/{book_id}", headers=_auth(token)).json()
    chapter_id = detail["chapters"][0]["id"]

    async def fake_synth(**kwargs):
        assert "api_key" in kwargs
        return b"FAKEAUDIO", "audio/mpeg"

    monkeypatch.setattr("app.api.tts.synthesize_speech", fake_synth)
    resp = client.post(
        "/api/tts/synthesize",
        headers=_auth(token),
        json={
            "base_url": "https://api.example.com",
            "api_key": "sk-test-key-should-not-persist",
            "model": "tts-1",
            "voice": "alloy",
            "book_id": book_id,
            "chapter_id": chapter_id,
            "segment_index": 0,
        },
    )
    assert resp.status_code == 200
    assert resp.content == b"FAKEAUDIO"


def test_reparse_recovers_latin1_gbk_book(client: TestClient):
    """Upload path is fine; reparse recovers a book stored as latin-1 mojibake."""
    assert _register(client, "reparse_user").status_code == 201
    token = _login(client, "reparse_user")

    novel = (
        "第一章 异界小道士\n"
        "夜色如墨，少年推开道观木门。\n"
        "第二章 山门夜话\n"
        "清风拂过廊檐，铜铃轻响。\n"
        "第三章 初入江湖\n"
        "他背起包袱，踏上尘土飞扬的官道。\n"
    )
    raw = novel.encode("gbk")
    mojibake = raw.decode("latin-1")

    # Seed a broken book directly in DB (historical import state).
    db = TestingSessionLocal()
    from app.models import Book, BookVisibility, Chapter, Segment, User

    user = db.query(User).filter(User.username == "reparse_user").first()
    book = Book(
        title="异世界道门",
        author=None,
        visibility=BookVisibility.private.value,
        owner_id=user.id,
        source_filename="broken.txt",
        encoding="latin-1",
    )
    db.add(book)
    db.flush()
    chapter = Chapter(book_id=book.id, index=0, title="正文")
    db.add(chapter)
    db.flush()
    # Split mojibake into a few segments like a naive single-chapter store.
    chunk = 200
    for i in range(0, len(mojibake), chunk):
        piece = mojibake[i : i + chunk]
        db.add(
            Segment(
                chapter_id=chapter.id,
                index=i // chunk,
                text=piece,
                char_count=len(piece),
            )
        )
    book_id = book.id
    db.commit()
    db.close()

    before = client.get(f"/api/books/{book_id}", headers=_auth(token)).json()
    assert len(before["chapters"]) == 1
    assert before["chapters"][0]["title"] == "正文"

    resp = client.post(f"/api/books/{book_id}/reparse", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["encoding"] in {"gbk", "gb18030"}
    assert len(detail["chapters"]) >= 3
    titles = [c["title"] for c in detail["chapters"]]
    assert any("第一章" in t and "异界小道士" in t for t in titles)

    # Non-owner cannot reparse.
    assert _register(client, "reparse_other").status_code == 201
    other = _login(client, "reparse_other")
    denied = client.post(f"/api/books/{book_id}/reparse", headers=_auth(other))
    assert denied.status_code == 403



def test_upload_persists_source_and_delete_cleans_files(client: TestClient):
    assert _register(client, "file_user").status_code == 201
    token = _login(client, "file_user")
    content = "第一章 开始\n你好世界。\n".encode("utf-8")
    up = client.post(
        "/api/books",
        headers=_auth(token),
        files={"file": ("demo.txt", content, "text/plain")},
        data={"title": "Demo"},
    )
    assert up.status_code == 201, up.text
    body = up.json()
    book_id = body["id"]
    assert "source_path" not in body

    settings = get_settings()
    me = client.get("/api/auth/me", headers=_auth(token)).json()
    expected_dir = settings.book_dir(me["id"], book_id)
    assert expected_dir.exists()
    abs_path = expected_dir / "demo.txt"
    assert abs_path.is_file()
    assert abs_path.read_bytes() == content

    deleted = client.delete(f"/api/books/{book_id}", headers=_auth(token))
    assert deleted.status_code == 200, deleted.text
    assert not abs_path.exists()
    assert not expected_dir.exists()




def test_admin_delete_book_cleans_files(client: TestClient):
    assert _register(client, "owner_user").status_code == 201
    assert _register(client, "admin_user").status_code == 201
    _promote("admin_user")
    owner = _login(client, "owner_user")
    admin = _login(client, "admin_user")

    content = "第一章 开始\n管理员删除应清理文件。\n".encode("utf-8")
    up = client.post(
        "/api/books",
        headers=_auth(owner),
        files={"file": ("admin-del.txt", content, "text/plain")},
        data={"title": "AdminDel"},
    )
    assert up.status_code == 201, up.text
    body = up.json()
    book_id = body["id"]
    assert "source_path" not in body
    settings = get_settings()
    me = client.get("/api/auth/me", headers=_auth(owner)).json()
    expected_dir = settings.book_dir(me["id"], book_id)
    abs_path = expected_dir / "admin-del.txt"
    assert abs_path.is_file()

    deleted = client.delete(f"/api/admin/books/{book_id}", headers=_auth(admin))
    assert deleted.status_code == 200, deleted.text
    assert not abs_path.exists()
    assert not expected_dir.exists()


def test_bootstrap_admin_id_is_one(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "rootadmin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "rootpass123")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import User
    from app.services.auth import bootstrap_admin

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        bootstrap_admin(db)
        admin = db.query(User).filter(User.username == "rootadmin").first()
        assert admin is not None
        assert admin.id == 1
        assert admin.role == "admin"

        # idempotent: no duplicate
        bootstrap_admin(db)
        count = db.query(User).filter(User.username == "rootadmin").count()
        assert count == 1
    finally:
        db.close()
        get_settings.cache_clear()


def test_progress_rejects_foreign_chapter(client: TestClient):
    assert _register(client, "prog_owner").status_code == 201
    assert _register(client, "prog_other").status_code == 201
    owner = _login(client, "prog_owner")
    other = _login(client, "prog_other")

    content = "第一章\n内容。\n".encode("utf-8")
    up_owner = client.post(
        "/api/books",
        headers=_auth(owner),
        files={"file": ("a.txt", content, "text/plain")},
        data={"title": "A"},
    )
    assert up_owner.status_code == 201, up_owner.text
    owner_book = up_owner.json()["id"]

    up_other = client.post(
        "/api/books",
        headers=_auth(other),
        files={"file": ("b.txt", content, "text/plain")},
        data={"title": "B"},
    )
    assert up_other.status_code == 201, up_other.text
    other_detail = client.get(f"/api/books/{up_other.json()['id']}", headers=_auth(other)).json()
    foreign_chapter_id = other_detail["chapters"][0]["id"]

    bad = client.put(
        f"/api/progress/{owner_book}",
        headers=_auth(owner),
        json={"chapter_id": foreign_chapter_id, "segment_index": 0, "position_seconds": 1.0},
    )
    assert bad.status_code == 404

    missing = client.put(
        f"/api/progress/{owner_book}",
        headers=_auth(owner),
        json={"chapter_id": 999999, "segment_index": 0, "position_seconds": 1.0},
    )
    assert missing.status_code == 404

    neg = client.put(
        f"/api/progress/{owner_book}",
        headers=_auth(owner),
        json={"chapter_id": None, "segment_index": -1, "position_seconds": 1.0},
    )
    assert neg.status_code == 400

    # playback path should enforce the same checks
    play_bad = client.put(
        "/api/playback/progress",
        headers=_auth(owner),
        json={
            "book_id": owner_book,
            "chapter_id": foreign_chapter_id,
            "segment_index": 0,
            "position_seconds": 1.0,
        },
    )
    assert play_bad.status_code == 404


def test_admin_cannot_make_book_public_for_others(client: TestClient):
    assert _register(client, "pub_owner").status_code == 201
    assert _register(client, "pub_admin").status_code == 201
    assert _register(client, "pub_reader").status_code == 201
    _promote("pub_admin")
    owner = _login(client, "pub_owner")
    admin = _login(client, "pub_admin")
    reader = _login(client, "pub_reader")

    content = "第一章\n公开？\n".encode("utf-8")
    up = client.post(
        "/api/books",
        headers=_auth(owner),
        files={"file": ("p.txt", content, "text/plain")},
        data={"title": "P"},
    )
    assert up.status_code == 201, up.text
    book_id = up.json()["id"]

    patched = client.patch(
        f"/api/admin/books/{book_id}",
        headers=_auth(admin),
        json={"is_public": True},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body.get("visibility") == "private"
    assert body.get("is_public") is False
    assert "source_path" not in body

    # Non-owner still cannot read
    assert client.get(f"/api/books/{book_id}", headers=_auth(reader)).status_code == 403
    reader_list = client.get("/api/books?scope=public", headers=_auth(reader)).json()
    assert all(b["id"] != book_id for b in reader_list)


def test_book_response_hides_source_path(client: TestClient):
    assert _register(client, "hide_src").status_code == 201
    token = _login(client, "hide_src")
    content = "第一章\n隐藏路径。\n".encode("utf-8")
    up = client.post(
        "/api/books",
        headers=_auth(token),
        files={"file": ("h.txt", content, "text/plain")},
        data={"title": "H"},
    )
    assert up.status_code == 201, up.text
    assert "source_path" not in up.json()
    detail = client.get(f"/api/books/{up.json()['id']}", headers=_auth(token)).json()
    assert "source_path" not in detail




def test_user_tts_settings_persist(client: TestClient):
    _register(client, "ttsuser")
    token = _login(client, "ttsuser")
    headers = _auth(token)

    empty = client.get("/api/auth/tts-settings", headers=headers)
    assert empty.status_code == 200, empty.text
    body = empty.json()
    assert body["base_url"] == ""
    assert body["cache_chapters"] == 3

    payload = {
        "base_url": "https://tts.example.test/v1",
        "api_key": "secret-key",
        "model": "voice-1",
        "voice": "alloy",
        "provider": "openai",
        "style": "",
        "audio_format": "mp3",
        "cache_chapters": 5,
    }
    saved = client.put("/api/auth/tts-settings", headers=headers, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["api_key"] == "secret-key"
    assert saved.json()["cache_chapters"] == 5

    again = client.get("/api/auth/tts-settings", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json() == saved.json()
