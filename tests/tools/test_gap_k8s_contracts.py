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
    "OPENAI_API_KEY",
    "RFID_DEVICE_TOKEN",
    "DATA_SOURCE_API_BASE_URL",
    "DATA_SOURCE_API_BASE_URL2",
    "DATA_SOURCE_API_BASE_URL3",
    "DATA_SOURCE_API_KEY",
    "DATA_SOURCE_API_CLIENT",
    "DATA_SOURCE_API_KEY_HEADER",
    "DATA_SOURCE_API_CLIENT_HEADER",
    "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE",
    "DATA_SOURCE_API_FETCH_ENABLED",
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


# --------------------------------------------------------------------------- #
# (d) probe-kontrakt: startupProbe är startgrinden                             #
# --------------------------------------------------------------------------- #
# Före startupProbe var den EFFEKTIVA startbudgeten livenessProbens:
# initialDelay 30 + periodSeconds 30 × failureThreshold 3 (default) = ca 120 s.
# En startupProbe tar över den rollen helt (kubelet håller tillbaka liveness
# OCH readiness tills den passerat), så dess budget får ALDRIG vara snålare —
# då blir kall Azure SQL / förstagångs-create_all / tung alembic-migration
# CrashLoopBackOff och havererad release i stället för en långsam start.
MIN_STARTUP_BUDGET_SECONDS = 180

# readinessProbe före ändringen: periodSeconds 10 × failureThreshold 6 = 60 s
# innan en levande-men-CFS-strypt podd tas ur Service-endpointen. Med
# replicas: 1 betyder NotReady noll endpoints = 503 för ALLA användare. När
# periodSeconds sänks för snabbare deploy MÅSTE failureThreshold höjas i takt.
MIN_READINESS_FAILURE_TOLERANCE_SECONDS = 60

# CFS-strypning vid cpu-limit 300m (ffmpeg i meta-analysen) gör default 1 s för
# snålt — härdningen från 2026-07 får inte rullas tillbaka av en probe-tweak.
REQUIRED_PROBE_TIMEOUT_SECONDS = 5

# HELA deploy-vinsten i #31 kommer från probe-GRANULARITETEN (periodSeconds: 2),
# inte bara från produkten period × failureThreshold. En rutinstädning som
# "normaliserar" cyklerna till k8s-default (10 s) håller budget-/toleranstesterna
# gröna (de kollar bara produkten) men återinför exakt det gamla långsamma
# beteendet: podden blir Ready först i 10-sekunders-steg vid varje deploy.
# Därför låser vi periodSeconds direkt. 3 s ger minimal marginal men utesluter
# klart 10 s-defaulten. Höjer du detta: mät om och motivera i commit-texten.
MAX_READINESS_PERIOD_SECONDS = 3
MAX_STARTUP_PERIOD_SECONDS = 3

PROBE_MANIFESTS = [FLOW_MANIFEST, DEPLOYMENT]
PROBE_IDS = [p.name for p in PROBE_MANIFESTS]


def _probed_container(path: Path) -> dict:
    return _main_container(_pod_spec(_first_kind(_load_all(path), "Deployment")))


def _container_port_numbers(container: dict) -> list[int]:
    """containerPort-numren (ints) i containerns ports-lista."""
    numbers = []
    for p in container.get("ports", []) or []:
        if isinstance(p, dict) and isinstance(p.get("containerPort"), int):
            numbers.append(p["containerPort"])
    return numbers


def _container_port_names(container: dict) -> set[str]:
    """Namngivna portar (för named targetPort i en Service)."""
    names = set()
    for p in container.get("ports", []) or []:
        if isinstance(p, dict) and p.get("name"):
            names.add(p["name"])
    return names


@pytest.mark.parametrize("manifest", PROBE_MANIFESTS, ids=PROBE_IDS)
def test_startup_probe_exists_and_is_patient(manifest):
    """startupProbe måste finnas och vara MER tålmodig än den gamla
    liveness-baserade startbudgeten (ca 120 s), annars byter vi några sekunders
    deploy-tid mot CrashLoopBackOff vid en långsam start."""
    container = _probed_container(manifest)
    startup = container.get("startupProbe")
    assert isinstance(startup, dict), (
        f"{manifest.name}: startupProbe saknas — utan den är readinessProbens "
        "initialDelaySeconds enda startgrinden och liveness kan döda en podd "
        "som fortfarande importerar/migrerar."
    )
    assert startup.get("httpGet", {}).get("path") == "/api/health", (
        f"{manifest.name}: startupProbe måste proba /api/health (DB-fri, svarar "
        "först när uvicorn bundit socketen efter prestart + alembic)."
    )
    # Kubernetes-defaults om fälten utelämnas.
    period = startup.get("periodSeconds", 10)
    failures = startup.get("failureThreshold", 3)
    budget = period * failures
    assert budget >= MIN_STARTUP_BUDGET_SECONDS, (
        f"{manifest.name}: startupProbe-budget {period}s × {failures} = "
        f"{budget}s < {MIN_STARTUP_BUDGET_SECONDS}s. Budgeten får aldrig "
        "understiga den gamla effektiva startbudgeten (ca 120 s) — höj "
        "failureThreshold, sänk inte tålamodet."
    )


@pytest.mark.parametrize("manifest", PROBE_MANIFESTS, ids=PROBE_IDS)
def test_all_probes_keep_generous_timeout(manifest):
    """timeoutSeconds: 5 på alla tre probar. Default (1 s) är för snålt när
    ffmpeg CFS-stryper hela cgroupen vid cpu-limit 300m."""
    container = _probed_container(manifest)
    for name in ("startupProbe", "livenessProbe", "readinessProbe"):
        probe = container.get(name)
        assert isinstance(probe, dict), f"{manifest.name}: {name} saknas"
        assert probe.get("timeoutSeconds") == REQUIRED_PROBE_TIMEOUT_SECONDS, (
            f"{manifest.name}: {name}.timeoutSeconds="
            f"{probe.get('timeoutSeconds')!r}, väntade "
            f"{REQUIRED_PROBE_TIMEOUT_SECONDS}. Default 1 s räcker inte vid "
            "CFS-strypning — kubelet dödar då podden på en tillfälligt långsam "
            "proba."
        )


@pytest.mark.parametrize("manifest", PROBE_MANIFESTS, ids=PROBE_IDS)
def test_readiness_has_no_initial_delay_floor(manifest):
    """När startupProbe finns är den startgrinden. Ett initialDelaySeconds-golv
    på readiness är då ren extra nedtid vid varje deploy (strategy: Recreate,
    replicas: 1 → varje sekund innan Ready är nedtid för alla användare)."""
    container = _probed_container(manifest)
    readiness = container.get("readinessProbe")
    assert isinstance(readiness, dict), f"{manifest.name}: readinessProbe saknas"
    assert readiness.get("initialDelaySeconds", 0) == 0, (
        f"{manifest.name}: readinessProbe.initialDelaySeconds="
        f"{readiness.get('initialDelaySeconds')!r} är ett rent nedtidsgolv när "
        "startupProbe redan håller tillbaka readiness under starten."
    )


@pytest.mark.parametrize("manifest", PROBE_MANIFESTS, ids=PROBE_IDS)
def test_readiness_unready_tolerance_is_not_reduced(manifest):
    """En snabbare readiness-cykel får inte köpas genom att podden tas ur
    Service-endpointen snabbare. Med replicas: 1 är NotReady = 503 för alla."""
    container = _probed_container(manifest)
    readiness = container.get("readinessProbe") or {}
    period = readiness.get("periodSeconds", 10)
    failures = readiness.get("failureThreshold", 3)
    tolerance = period * failures
    assert tolerance >= MIN_READINESS_FAILURE_TOLERANCE_SECONDS, (
        f"{manifest.name}: readiness-tolerans {period}s × {failures} = "
        f"{tolerance}s < {MIN_READINESS_FAILURE_TOLERANCE_SECONDS}s. Sänkt "
        "periodSeconds kräver höjd failureThreshold — annars slår en kort "
        "ffmpeg-strypning ut hela appen (replicas: 1, inga andra endpoints)."
    )


@pytest.mark.parametrize("manifest", PROBE_MANIFESTS, ids=PROBE_IDS)
def test_readiness_period_stays_granular(manifest):
    """Låser SJÄLVA vinsten i #31: readinessProbe.periodSeconds. Produkttestet
    ovan (period × failureThreshold) är grönt även vid k8s-default 10 s × 6, men
    då blir podden Ready först i 10-sekunders-steg vid deploy — exakt det gamla
    långsamma beteendet. Utan den här assertionen kunde en normalisering till
    default återställa nedtiden med helt grön svit."""
    container = _probed_container(manifest)
    readiness = container.get("readinessProbe") or {}
    period = readiness.get("periodSeconds", 10)
    assert period <= MAX_READINESS_PERIOD_SECONDS, (
        f"{manifest.name}: readinessProbe.periodSeconds={period}s > "
        f"{MAX_READINESS_PERIOD_SECONDS}s. En grov cykel gör podden Ready först i "
        f"{period}-sekunders-steg vid varje deploy och äter upp deploy-vinsten i "
        "#31. Höj bara efter ny mätning — och höj failureThreshold i takt så "
        "unready-toleransen hålls."
    )


@pytest.mark.parametrize("manifest", PROBE_MANIFESTS, ids=PROBE_IDS)
def test_startup_period_stays_granular(manifest):
    """Samma granularitetsvinst för startupProbe. test_startup_probe_exists...
    kollar bara att period × failureThreshold ≥ 180 s, vilket är grönt även vid
    10 s × 18. Men med 10 s-cykel blir podden Ready i 10-sekunders-steg efter att
    den börjat lyssna i stället för 2 — så granulariteten måste låsas här."""
    container = _probed_container(manifest)
    startup = container.get("startupProbe") or {}
    period = startup.get("periodSeconds", 10)
    assert period <= MAX_STARTUP_PERIOD_SECONDS, (
        f"{manifest.name}: startupProbe.periodSeconds={period}s > "
        f"{MAX_STARTUP_PERIOD_SECONDS}s. Grov startcykel fördröjer Ready i "
        f"{period}-sekunders-steg. Behåll fin cykel och höj failureThreshold för "
        "budgeten, sänk inte granulariteten."
    )


@pytest.mark.parametrize("manifest", PROBE_MANIFESTS, ids=PROBE_IDS)
def test_startup_probe_has_no_initial_delay_floor(manifest):
    """startupProbe.initialDelaySeconds är ett rent nedtidsgolv: kubelet väntar
    så många sekunder innan FÖRSTA startup-proben, vilket fördröjer Ready lika
    mycket vid VARJE deploy (strategy: Recreate, replicas: 1). Fältet var
    oassertat — golvet kunde återinföras med grön svit. Låser det till 0."""
    container = _probed_container(manifest)
    startup = container.get("startupProbe") or {}
    assert startup.get("initialDelaySeconds", 0) == 0, (
        f"{manifest.name}: startupProbe.initialDelaySeconds="
        f"{startup.get('initialDelaySeconds')!r} lägger tillbaka ett fast "
        "nedtidsgolv före första proben vid varje deploy. Snabb periodSeconds ska "
        "göra podden Ready så fort den lyssnar, utan golv."
    )


@pytest.mark.parametrize("manifest", PROBE_MANIFESTS, ids=PROBE_IDS)
def test_startup_probe_targets_the_container_port(manifest):
    """startupProbe blockerar BÅDE liveness och readiness tills den passerat — en
    felriktad probe-port är därför ett TOTALSTOPP (podden blir aldrig Ready,
    CrashLoop), inte en degradering. Porten var oassertad (bara path == /api/health).
    Låser httpGet.port mot containerns containerPort."""
    container = _probed_container(manifest)
    startup = container.get("startupProbe") or {}
    probe_port = startup.get("httpGet", {}).get("port")
    assert probe_port is not None, (
        f"{manifest.name}: startupProbe saknar httpGet.port"
    )
    container_ports = _container_port_numbers(container)
    if not container_ports:
        pytest.skip(f"{manifest.name}: containern saknar ports[].containerPort")
    assert probe_port in container_ports, (
        f"{manifest.name}: startupProbe httpGet.port={probe_port!r} finns inte "
        f"bland containerPort {container_ports}. Proben träffar en port som "
        "uvicorn inte lyssnar på → podden blir aldrig Ready (totalstopp)."
    )


@pytest.mark.parametrize("manifest", PROBE_MANIFESTS, ids=PROBE_IDS)
def test_service_target_port_matches_container_and_startup_port(manifest):
    """Service.targetPort, containerPort och startupProbe-porten måste vara samma
    port. Glider de isär går antingen trafik (Service) eller startgrinden (probe)
    till fel port. Servicen ligger i samma multidoc-fil för flow.yml; saknas en
    Service i filen hoppas testet mjukt över (t.ex. deployment.yaml)."""
    docs = _load_all(manifest)
    services = _by_kind(docs, "Service")
    if not services:
        pytest.skip(f"{manifest.name}: ingen Service i samma fil")
    container = _main_container(_pod_spec(_first_kind(docs, "Deployment")))
    container_ports = _container_port_numbers(container)
    container_names = _container_port_names(container)
    if not container_ports:
        pytest.skip(f"{manifest.name}: containern saknar ports[].containerPort")

    target_ports = []
    for svc in services:
        for p in svc.get("spec", {}).get("ports", []) or []:
            if isinstance(p, dict) and p.get("targetPort") is not None:
                target_ports.append(p["targetPort"])
    if not target_ports:
        pytest.skip(f"{manifest.name}: Service saknar targetPort")

    for target in target_ports:
        # targetPort kan vara int (portnummer) eller str (portnamn).
        matches = target in container_ports or target in container_names
        assert matches, (
            f"{manifest.name}: Service targetPort={target!r} matchar varken "
            f"containerPort {container_ports} eller portnamn {sorted(container_names)} "
            "— trafiken routas till en port podden inte lyssnar på."
        )

    startup_port = container.get("startupProbe", {}).get("httpGet", {}).get("port")
    if startup_port is not None:
        assert startup_port in container_ports, (
            f"{manifest.name}: startupProbe-port {startup_port!r} matchar inte "
            f"containerPort {container_ports} — probe och trafik pekar på olika portar."
        )
