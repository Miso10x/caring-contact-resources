"""The staff assistant: staff-only, edits only this site's records, every change undoable.

The Claude API is replaced by a scripted fake, so these tests make no network calls.
"""
import copy
from types import SimpleNamespace

from test_app import WRITE, client, login  # noqa: F401  (client is a fixture)

import chat
import store


def text(t):
    return SimpleNamespace(type="text", text=t, model_dump=lambda **k: {"type": "text", "text": t})


def use(i, name, args):
    return SimpleNamespace(type="tool_use", id=i, name=name, input=args,
                           model_dump=lambda **k: {"type": "tool_use", "id": i, "name": name, "input": args})


class FakeClaude:
    """Plays back a list of responses, one per model call, and records what it was sent."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.sent = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.sent.append(copy.deepcopy(kw))
        content = self.turns.pop(0)
        stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        return SimpleNamespace(content=content, stop_reason=stop)


def ask(c, message, fake, monkeypatch, chat_id=None):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(chat, "_client", lambda: fake)
    return c.post("/api/assistant", json={"message": message, "chat_id": chat_id}, headers=WRITE)


def test_volunteers_cannot_use_the_assistant(client, monkeypatch):
    login(client, "vol-pass")
    assert client.get("/api/assistant").status_code == 403
    assert ask(client, "hi", FakeClaude([text("x")]), monkeypatch).status_code == 403
    assert client.post("/api/assistant/undo", json={"batch": "x"}, headers=WRITE).status_code == 403


def test_signed_out_cannot_use_the_assistant(client):
    assert client.post("/api/assistant", json={"message": "hi"}, headers=WRITE).status_code == 401


def test_says_when_no_api_key_is_set(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    login(client, "staff-pass")
    assert client.get("/api/assistant").get_json() == {"enabled": False}
    r = client.post("/api/assistant", json={"message": "hi"}, headers=WRITE)
    assert r.status_code == 503 and "switched on" in r.get_json()["error"]


def test_needs_the_fetch_header(client, monkeypatch):
    login(client, "staff-pass")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert client.post("/api/assistant", json={"message": "hi"}).status_code == 400


def test_edit_then_undo(client, monkeypatch):
    login(client, "staff-pass")
    before = store.get("categories", "grief")
    edited = {**before, "description": "New words"}
    fake = FakeClaude(
        [use("t1", "get_item", {"collection": "categories", "id": "grief"})],
        [use("t2", "save_item", {"collection": "categories", "id": "grief", "data": edited})],
        [text("I changed the Grief description.")],
    )
    r = ask(client, "change the grief description", fake, monkeypatch).get_json()
    assert r["reply"] == "I changed the Grief description."
    assert r["changes"] == [{"action": "changed", "collection": "categories", "id": "grief", "name": before["name"]}]
    assert store.get("categories", "grief")["description"] == "New words"
    # The model was given the record it asked for.
    tool_result = fake.sent[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1" and before["name"] in tool_result["content"]

    assert client.post("/api/assistant/undo", json={"batch": r["batch"]}, headers=WRITE).get_json() == {"restored": 1}
    assert store.get("categories", "grief") == before
    # Undoing twice changes nothing more.
    assert client.post("/api/assistant/undo", json={"batch": r["batch"]}, headers=WRITE).get_json() == {"restored": 0}


def test_add_and_delete_are_undone_too(client, monkeypatch):
    login(client, "staff-pass")
    notice = store.get("notices", "eiss")
    fake = FakeClaude(
        [use("a", "save_item", {"collection": "resources", "id": "new-place", "data": {"name": "New Place", "suggestion": False}}),
         use("b", "delete_item", {"collection": "notices", "id": "eiss"})],
        [text("Done.")],
    )
    r = ask(client, "add new place and remove the eiss notice", fake, monkeypatch).get_json()
    assert [c["action"] for c in r["changes"]] == ["added", "deleted"]
    assert store.get("resources", "new-place") and store.get("notices", "eiss") is None
    client.post("/api/assistant/undo", json={"batch": r["batch"]}, headers=WRITE)
    assert store.get("resources", "new-place") is None and store.get("notices", "eiss") == notice


def test_tools_cannot_reach_outside_the_site_records(client, monkeypatch):
    login(client, "staff-pass")
    fake = FakeClaude(
        [use("a", "save_item", {"collection": "migrations", "id": "x", "data": {"a": 1}}),
         use("b", "get_item", {"collection": "resources", "id": "../../etc/passwd"}),
         use("c", "save_item", {"collection": "resources", "id": "no-name", "data": {"description": "x"}}),
         use("d", "run_shell", {"cmd": "ls"})],
        [text("I couldn't do that.")],
    )
    r = ask(client, "try odd things", fake, monkeypatch).get_json()
    assert r["changes"] == [] and r["batch"] is None
    results = fake.sent[1]["messages"][-1]["content"]
    assert all(x["is_error"] for x in results)
    assert store.get("resources", "no-name") is None


def test_only_this_sites_tools_are_offered(client, monkeypatch):
    login(client, "staff-pass")
    fake = FakeClaude([text("This box can only make changes to the Resource Finder.")])
    ask(client, "write me an email", fake, monkeypatch)
    sent = fake.sent[0]
    assert sorted(t["name"] for t in sent["tools"]) == ["delete_item", "get_item", "list_items", "save_item", "search_resources"]
    assert "ONLY JOB" in sent["system"]


def test_conversation_continues_with_its_history(client, monkeypatch):
    login(client, "staff-pass")
    fake = FakeClaude([text("Which one?")], [text("OK.")])
    first = ask(client, "change a resource", fake, monkeypatch).get_json()
    ask(client, "the grief one", fake, monkeypatch, chat_id=first["chat_id"])
    roles = [m["role"] for m in fake.sent[1]["messages"]]
    assert roles == ["user", "assistant", "user"]


def test_search_finds_resources(client):
    out, err = chat.run_tool("search_resources", {"query": "PerformCare"}, "b", [])
    assert not err and '"total"' in out and "performcare" in out.lower()


def test_api_failure_after_changes_keeps_them_undoable(client, monkeypatch):
    login(client, "staff-pass")
    calls = {"n": 0}
    fake = FakeClaude([use("a", "save_item", {"collection": "categories", "id": "grief", "data": {"name": "Grief!"}})])

    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("network")
        return FakeClaude.create(fake, **kw)

    fake.beta.messages.create = flaky
    r = ask(client, "rename grief", fake, monkeypatch).get_json()
    assert r["changes"] and r["batch"] and "lost my connection" in r["reply"]
