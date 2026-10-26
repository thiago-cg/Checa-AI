"""Bot do Telegram por webhook na API (Cloud Run): segredo, rota e trava do polling local."""
import asyncio
import hashlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from factcheck_mvp import api, config, telegram_bot as tb

TOKEN = "123:abc"


@pytest.fixture
def tg(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_TOKEN", TOKEN)
    falso = SimpleNamespace(update_queue=asyncio.Queue(), bot=None)
    monkeypatch.setattr(api, "_tg", falso)
    return falso


def test_segredo_igual_ao_do_deploy():
    # scripts/deploy_cloudrun.sh: printf 'webhook:%s' "$token" | sha256sum
    assert tb.segredo_webhook(TOKEN) == hashlib.sha256(b"webhook:123:abc").hexdigest()


def test_webhook_desligado_404(monkeypatch):
    monkeypatch.setattr(api, "_tg", None)
    r = TestClient(api.app).post("/telegram/webhook", json={"update_id": 1})
    assert r.status_code == 404


def test_webhook_sem_segredo_403(tg):
    c = TestClient(api.app)
    assert c.post("/telegram/webhook", json={"update_id": 1}).status_code == 403
    r = c.post("/telegram/webhook", json={"update_id": 1},
               headers={"X-Telegram-Bot-Api-Secret-Token": "errado"})
    assert r.status_code == 403
    assert tg.update_queue.qsize() == 0


def test_webhook_enfileira_update(tg):
    r = TestClient(api.app).post("/telegram/webhook", json={"update_id": 7},
                                 headers={"X-Telegram-Bot-Api-Secret-Token": tb.segredo_webhook(TOKEN)})
    assert r.status_code == 200
    assert tg.update_queue.get_nowait().update_id == 7


def test_registrar_webhook_usa_url_e_segredo(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_TOKEN", TOKEN)
    chamadas = []

    class Bot:
        async def set_webhook(self, **kw):
            chamadas.append(kw)

    asyncio.run(tb.registrar_webhook(Bot(), "https://checa-ai.onrender.com/"))
    assert chamadas == [{"url": "https://checa-ai.onrender.com/telegram/webhook",
                         "secret_token": tb.segredo_webhook(TOKEN),
                         "allowed_updates": ["message", "callback_query"]}]


def test_polling_recusa_com_webhook_ativo(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_TOKEN", TOKEN)
    monkeypatch.setattr(config, "TELEGRAM_FORCAR_POLLING", False)
    monkeypatch.setattr(tb, "_webhook_ativo", lambda: "https://exemplo.run.app/telegram/webhook")
    monkeypatch.setattr(tb, "_instancia_unica", lambda: pytest.fail("não deveria pegar o lock"))
    with pytest.raises(SystemExit, match="webhook"):
        tb.main()
