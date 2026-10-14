import os
import sys
from pathlib import Path

# Suite hermética: um .env local com FAKE_MODEL_PATH não carrega o BERTimbau
# (400 MB, torch) nos testes. load_dotenv não sobrescreve variável já definida.
os.environ["FAKE_MODEL_PATH"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

# Missão G: as flags da Missão F/G passaram a vir LIGADAS por padrão. Os testes da mecânica base do agente e da
# camada SerpAPI (motor orgânico, uma onda extra, consulta sem limpeza) pedem este fixture para rodar com o
# comportamento de antes; cada flag tem testes próprios que a ligam explicitamente.
FLAGS_BASE = {"SERP_ENGINE": "google", "BUSCA_PLANEJADOR": False, "BUSCA_SITE_NO_ORGANICO": False,
              "EXTRATOR_LIMPEZA": False, "INDICE_TRAVA_SIMILARIDADE": False, "JUIZ_AUTOCONSISTENCIA": False,
              "SINTETIZADOR": False}


@pytest.fixture
def base_sem_flags(monkeypatch):
    from factcheck_mvp import config
    for k, v in FLAGS_BASE.items():
        monkeypatch.setattr(config, k, v)
