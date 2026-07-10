"""Kontrakt för Kubernetes-manifesten i k8s/.

Fångar tyst-driva-isär-buggar mellan configmap, deployment och pvc: om
MEDIA_STORE_ROOT och media-volymens mountPath glider isär skriver appen media
till en icke-persistent sökväg (försvinner vid omstart); om init-containerns
kopieringsmål inte längre är där flow-data-volymen är monterad seedas aldrig
referensdatan; om en volym pekar på fel PVC startar podden inte alls.

Verifierar också de två invarianterna som RWO-volymerna kräver:
replicas==1 och strategy.type==Recreate (två poddar kan inte mounta samma
ReadWriteOnce-volym samtidigt).

Läser de faktiska filerna med pyyaml (safe_load_all för multidoc). Hoppar
graciöst över om en fil/nyckel saknas, men assertar allt som faktiskt finns.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
K8S_DIR = ROOT / "k8s"

CONFIGMAP = K8S_DIR / "configmap.yaml"
DEPLOYMENT = K8S_DIR / "deployment.yaml"
FLOW_MANIFEST = K8S_DIR / "flow.yml"
PVC = K8S_DIR / "pvc.yaml"

# Octopus ersätter #{VAR} bara om variabeln finns definierad i Octopus-projektet
# Flow; okända platshållare lämnas ordagrant kvar i manifestet och blir "riktiga"
# miljövärden i podden. 2026-07-09 saknades GEMINI_API_BASE_URL i Octopus och
# varje meta-videoanalys kraschade med ValueError på platshållartexten. Nya
# platshållare i flow.yml kräver därför ett medvetet beslut: skapa variabeln i
# Octopus FÖRST, lägg sedan till namnet här.
OCTOPUS_PROJECT_VARIABLES = {
    "DATABASE_URL",
    "SECRET_KEY",
    "SUPER_USER_USERNAMES",
    "EXCEL_API_TOKEN",
    "MINIMAX_API_KEY",
    "GEMINI_API_KEY",
    "RFID_DEVICE_TOKEN",
    "DATA_SOURCE_API_BASE_URL",
    "DATA_SOURCE_API_BASE_URL2",
    "DATA_SOURCE_API_BASE_URL3",
    "DATA_SOURCE_API_KEY",
    "DATA_SOURCE_API_CLIENT",
    "DATA_SOURCE_API_KEY_HEADER",
    "DATA_SOURCE_API_CLIENT_HEADER",
    "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE",
    "OPENTELEMETRY_URL",
    "OPENTELEMETRY_TOKEN",
    "JOB_CPU",
    "JOB_MEMORY",
    "JOB_MEMORY_MAX",
}

MEDIA_VOLUME = "flow-media"
DATA_VOLUME = "flow-data"


# --------------------------------------------------------------------------- #
# Hjälpare                                                                     #
# --------------------------------------------------------------------------- #
def _load_all(path: Path) -> list[dict]:
    """Alla YAML-dokument i en fil (multidoc), None-dokument bortfiltrerade."""
    if not path.exists():
        pytest.skip(f"saknar {path.relative_to(ROOT)}")
    docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    return [d for d in docs if isinstance(d, dict)]


def _by_kind(docs: list[dict], kind: str) -> list[dict]:
    return [d for d in docs if d.get("kind") == kind]


def _first_kind(docs: list[dict], kind: str) -> dict:
    hits = _by_kind(docs, kind)
    if not hits:
        pytest.skip(f"inget {kind}-dokument")
    return hits[0]


def _pod_spec(deployment: dict) -> dict:
    spec = deployment.get("spec", {}).get("template", {}).get("spec")
    if not isinstance(spec, dict):
        pytest.skip("deployment saknar spec.template.spec")
    return spec


def _find_container(containers, name: str) -> dict:
    for c in containers or []:
        if isinstance(c, dict) and c.get("name") == name:
            return c
    return {}


def _mount_path(container: dict, volume_name: str):
    for m in container.get("volumeMounts", []) or []:
        if isinstance(m, dict) and m.get("name") == volume_name:
            return m.get("mountPath")
    return None


def _main_container(pod_spec: dict) -> dict:
    containers = pod_spec.get("containers") or []
    if not containers:
        pytest.skip("deployment saknar containers")
    # Föredra namngiven flow-web, annars första containern.
    return _find_container(containers, "flow-web") or containers[0]


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def configmap() -> dict:
    return _first_kind(_load_all(CONFIGMAP), "ConfigMap")


@pytest.fixture(scope="module")
def deployment() -> dict:
    return _first_kind(_load_all(DEPLOYMENT), "Deployment")


@pytest.fixture(scope="module")
def pvc_names() -> set[str]:
    claims = _by_kind(_load_all(PVC), "PersistentVolumeClaim")
    if not claims:
        pytest.skip("inga PVC-dokument")
    return {c.get("metadata", {}).get("name") for c in claims}


# --------------------------------------------------------------------------- #
# (a) sökvägs-/volymkontrakt                                                   #
# --------------------------------------------------------------------------- #
def test_media_store_root_matches_media_mountpath(configmap, deployment):
    """MEDIA_STORE_ROOT måste peka på där flow-media-volymen är monterad,
    annars skrivs media utanför PVC:n och tappas vid omstart."""
    data = configmap.get("data", {})
    if "MEDIA_STORE_ROOT" not in data:
        pytest.skip("configmap saknar MEDIA_STORE_ROOT")
    root = data["MEDIA_STORE_ROOT"]

    main = _main_container(_pod_spec(deployment))
    mount = _mount_path(main, MEDIA_VOLUME)
    if mount is None:
        pytest.skip(f"deployment saknar volumeMount {MEDIA_VOLUME}")

    assert root == mount, (
        f"MEDIA_STORE_ROOT={root!r} != {MEDIA_VOLUME} mountPath={mount!r}"
    )


def test_flow_data_mount_matches_init_copy_target(deployment):
    """Init-containern kopierar bundlad referensdata till flow-data-volymen.
    Kopieringsmålet i kommandot måste vara där flow-data faktiskt monteras i
    init-containern, annars hamnar seed-datan på ett tomt overlay-lager."""
    pod = _pod_spec(deployment)
    inits = pod.get("initContainers") or []
    if not inits:
        pytest.skip("deployment saknar initContainers")

    # Hitta init-containern som monterar flow-data.
    init = next(
        (c for c in inits if _mount_path(c, DATA_VOLUME) is not None),
        None,
    )
    if init is None:
        pytest.skip(f"ingen initContainer monterar {DATA_VOLUME}")

    mount = _mount_path(init, DATA_VOLUME)
    command = init.get("command") or []
    cmd_text = " ".join(str(x) for x in command)
    if not cmd_text.strip():
        pytest.skip("initContainer saknar command")

    # Målsökvägen (ev. med trailing slash) ska förekomma i kopieringskommandot.
    m = mount.rstrip("/")
    assert (m in cmd_text) or (m + "/" in cmd_text), (
        f"init flow-data mountPath {mount!r} saknas som kopieringsmål i "
        f"kommandot: {cmd_text!r}"
    )


def test_volumes_reference_existing_pvcs(deployment, pvc_names):
    """Varje PVC-volym i deployment måste referera en claim som finns i
    pvc.yaml, och de förväntade flow-volymerna ska vara PVC-backade."""
    pod = _pod_spec(deployment)
    volumes = pod.get("volumes") or []
    if not volumes:
        pytest.skip("deployment saknar volumes")

    claim_by_volume: dict[str, str] = {}
    for v in volumes:
        if not isinstance(v, dict):
            continue
        pvc_ref = v.get("persistentVolumeClaim")
        if isinstance(pvc_ref, dict) and pvc_ref.get("claimName"):
            claim_by_volume[v.get("name")] = pvc_ref["claimName"]

    if not claim_by_volume:
        pytest.skip("inga PVC-backade volymer i deployment")

    # (i) alla claim-referenser existerar som PVC:er.
    for vol_name, claim in claim_by_volume.items():
        assert claim in pvc_names, (
            f"volym {vol_name!r} refererar PVC {claim!r} som saknas i "
            f"pvc.yaml ({sorted(pvc_names)})"
        )

    # (ii) de kända flow-volymerna ska vara PVC-backade (om de finns).
    pod_volume_names = {
        v.get("name") for v in volumes if isinstance(v, dict)
    }
    for expected in (DATA_VOLUME, MEDIA_VOLUME):
        if expected in pod_volume_names:
            assert expected in claim_by_volume, (
                f"volym {expected!r} borde vara PVC-backad men är det inte"
            )


# --------------------------------------------------------------------------- #
# (b) RWO-invarianter                                                          #
# --------------------------------------------------------------------------- #
def test_replicas_is_one(deployment):
    """RWO-volymer kan bara mountas av en podd → exakt 1 replika."""
    spec = deployment.get("spec", {})
    if "replicas" not in spec:
        pytest.skip("deployment saknar spec.replicas")
    assert spec["replicas"] == 1, f"replicas={spec['replicas']!r}, väntade 1"


def test_strategy_is_recreate(deployment):
    """Recreate krävs så gamla podden släpper RWO-volymen innan nya startar."""
    strategy = deployment.get("spec", {}).get("strategy")
    if not isinstance(strategy, dict) or "type" not in strategy:
        pytest.skip("deployment saknar spec.strategy.type")
    assert strategy["type"] == "Recreate", (
        f"strategy.type={strategy['type']!r}, väntade 'Recreate'"
    )


# --------------------------------------------------------------------------- #
# (c) Octopus-platshållare i flow.yml                                          #
# --------------------------------------------------------------------------- #
def test_flow_manifest_placeholders_are_declared_octopus_variables():
    """Varje #{VAR}-platshållare i k8s/flow.yml måste finnas i allowlisten
    OCTOPUS_PROJECT_VARIABLES (= variabler som är skapade i Octopus-projektet).
    En platshållare utan Octopus-variabel deployas ordagrant som miljövärde —
    det var rotorsaken till att meta-videoanalysen kraschade 2026-07-09."""
    if not FLOW_MANIFEST.exists():
        pytest.skip("saknar k8s/flow.yml")
    text = FLOW_MANIFEST.read_text(encoding="utf-8")
    # Endast env-liknande VERSALNAMN — Octopus-uttryck som #{if ...},
    # #{/if} och #{Octopus.Release...} är substitutioner Octopus alltid kan.
    found = set(re.findall(r"#\{([A-Z][A-Z0-9_]*)\}", text))
    assert found, "hittade inga #{VAR}-platshållare — har manifestformatet ändrats?"
    unknown = sorted(found - OCTOPUS_PROJECT_VARIABLES)
    assert not unknown, (
        f"Platshållare utan deklarerad Octopus-variabel: {unknown}. "
        "Skapa variabeln i Octopus-projektet Flow först och lägg sedan till "
        "namnet i OCTOPUS_PROJECT_VARIABLES, eller hårdkoda värdet om det "
        "inte är hemligt."
    )
