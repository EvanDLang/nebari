import enum
import json
import sys
import time
from typing import Any, Dict, List, Optional, Type, Union
from urllib.parse import urlencode

from pydantic import ConfigDict, Field, field_validator, model_validator

from _nebari import constants
from _nebari.stages.base import NebariTerraformStage
from _nebari.stages.tf_objects import (
    NebariHelmProvider,
    NebariKubernetesProvider,
    NebariTerraformState,
)
from _nebari.utils import set_docker_image_tag, set_nebari_dask_version
from _nebari.version import __version__
from nebari import schema
from nebari.hookspecs import NebariStage, hookimpl

# check and retry settings
NUM_ATTEMPTS = 10
TIMEOUT = 10  # seconds


_forwardauth_middleware_name = "traefik-forward-auth"


@schema.yaml_object(schema.yaml)
class AccessEnum(str, enum.Enum):
    all = "all"
    yaml = "yaml"
    keycloak = "keycloak"

    @classmethod
    def to_yaml(cls, representer, node):
        return representer.represent_str(node.value)


class DefaultImages(schema.Base):
    jupyterhub: str = f"quay.io/nebari/nebari-jupyterhub:{set_docker_image_tag()}"
    jupyterlab: str = f"quay.io/nebari/nebari-jupyterlab:{set_docker_image_tag()}"
    dask_worker: str = f"quay.io/nebari/nebari-dask-worker:{set_docker_image_tag()}"


class Storage(schema.Base):
    conda_store: str = "200Gi"
    shared_filesystem: str = "200Gi"


class JupyterHubTheme(schema.Base):
    hub_title: str = "Nebari"
    hub_subtitle: str = "Your open source data science platform"
    welcome: str = (
        """Welcome! Learn about Nebari's features and configurations in <a href="https://www.nebari.dev/docs">the documentation</a>. If you have any questions or feedback, reach the team on <a href="https://www.nebari.dev/docs/community#getting-support">Nebari's support forums</a>."""
    )
    logo: str = (
        "https://raw.githubusercontent.com/nebari-dev/nebari-design/main/logo-mark/horizontal/Nebari-Logo-Horizontal-Lockup-White-text.svg"
    )
    favicon: str = (
        "https://raw.githubusercontent.com/nebari-dev/nebari-design/main/symbol/favicon.ico"
    )
    primary_color: str = "#4f4173"
    primary_color_dark: str = "#4f4173"
    secondary_color: str = "#957da6"
    secondary_color_dark: str = "#957da6"
    accent_color: str = "#32C574"
    accent_color_dark: str = "#32C574"
    text_color: str = "#111111"
    h1_color: str = "#652e8e"
    h2_color: str = "#652e8e"
    version: str = f"v{__version__}"
    navbar_color: str = "#1c1d26"
    navbar_text_color: str = "#f1f1f6"
    navbar_hover_color: str = "#db96f3"
    danger_color: str = "#e03830"
    display_version: str = "True"  # limitation of theme everything is a str


class Theme(schema.Base):
    jupyterhub: JupyterHubTheme = JupyterHubTheme()


class KubeSpawner(schema.Base):
    cpu_limit: float
    cpu_guarantee: float
    mem_limit: str
    mem_guarantee: str
    model_config = ConfigDict(extra="allow")


class JupyterLabProfile(schema.Base):
    access: AccessEnum = AccessEnum.all
    display_name: str
    description: str
    default: bool = False
    users: Optional[List[str]] = None
    groups: Optional[List[str]] = None
    kubespawner_override: Optional[KubeSpawner] = None

    @model_validator(mode="after")
    def only_yaml_can_have_groups_and_users(self):
        if self.access != AccessEnum.yaml:
            if self.users is not None or self.groups is not None:
                raise ValueError(
                    "Profile must not contain groups or users fields unless access = yaml"
                )
        return self


class DaskWorkerProfile(schema.Base):
    worker_cores_limit: float
    worker_cores: float
    worker_memory_limit: str
    worker_memory: str
    worker_threads: int = 1
    model_config = ConfigDict(extra="allow")


class Profiles(schema.Base):
    jupyterlab: List[JupyterLabProfile] = [
        JupyterLabProfile(
            display_name="Small Instance",
            description="Stable environment with 2 cpu / 8 GB ram",
            default=True,
            kubespawner_override=KubeSpawner(
                cpu_limit=2,
                cpu_guarantee=1.5,
                mem_limit="8G",
                mem_guarantee="5G",
            ),
        ),
        JupyterLabProfile(
            display_name="Medium Instance",
            description="Stable environment with 4 cpu / 16 GB ram",
            kubespawner_override=KubeSpawner(
                cpu_limit=4,
                cpu_guarantee=3,
                mem_limit="16G",
                mem_guarantee="10G",
            ),
        ),
    ]
    dask_worker: Dict[str, DaskWorkerProfile] = {
        "Small Worker": DaskWorkerProfile(
            worker_cores_limit=2,
            worker_cores=1.5,
            worker_memory_limit="8G",
            worker_memory="5G",
            worker_threads=2,
        ),
        "Medium Worker": DaskWorkerProfile(
            worker_cores_limit=4,
            worker_cores=3,
            worker_memory_limit="16G",
            worker_memory="10G",
            worker_threads=4,
        ),
    }

    @field_validator("jupyterlab")
    @classmethod
    def check_default(cls, value):
        """Check if only one default value is present."""
        default = [attrs["default"] for attrs in value if "default" in attrs]
        if default.count(True) > 1:
            raise TypeError(
                "Multiple default Jupyterlab profiles may cause unexpected problems."
            )
        return value


class CondaEnvironment(schema.Base):
    name: str
    channels: Optional[List[str]] = None
    dependencies: List[Union[str, Dict[str, List[str]]]]


class CondaStore(schema.Base):
    extra_settings: Dict[str, Any] = {}
    extra_config: str = ""
    image: str = "quansight/conda-store-server"
    image_tag: str = constants.DEFAULT_CONDA_STORE_IMAGE_TAG
    default_namespace: str = "bioscape"
    object_storage: str = "200Gi"


class NebariWorkflowController(schema.Base):
    enabled: bool = True
    image_tag: str = constants.DEFAULT_NEBARI_WORKFLOW_CONTROLLER_IMAGE_TAG


class ArgoWorkflows(schema.Base):
    enabled: bool = True
    overrides: Dict = {}
    nebari_workflow_controller: NebariWorkflowController = NebariWorkflowController()


class JHubApps(schema.Base):
    enabled: bool = False


class MonitoringOverrides(schema.Base):
    loki: Dict = {}
    promtail: Dict = {}
    minio: Dict = {}


class Monitoring(schema.Base):
    enabled: bool = True
    overrides: MonitoringOverrides = MonitoringOverrides()
    minio_enabled: bool = True


class JupyterLabPioneer(schema.Base):
    enabled: bool = False
    log_format: Optional[str] = None


class Telemetry(schema.Base):
    jupyterlab_pioneer: JupyterLabPioneer = JupyterLabPioneer()


class JupyterHub(schema.Base):
    overrides: Dict = {}


class IdleCuller(schema.Base):
    terminal_cull_inactive_timeout: int = 15
    terminal_cull_interval: int = 5
    kernel_cull_idle_timeout: int = 15
    kernel_cull_interval: int = 5
    kernel_cull_connected: bool = True
    kernel_cull_busy: bool = False
    server_shutdown_no_activity_timeout: int = 15


class JupyterLab(schema.Base):
    default_settings: Dict[str, Any] = {}
    idle_culler: IdleCuller = IdleCuller()
    initial_repositories: List[Dict[str, str]] = []
    preferred_dir: Optional[str] = None


class InputSchema(schema.Base):
    default_images: DefaultImages = DefaultImages()
    storage: Storage = Storage()
    theme: Theme = Theme()
    profiles: Profiles = Profiles()
    environments: Dict[str, CondaEnvironment] = {
        # "environment-dask.yaml": CondaEnvironment(
        #     name="dask",
        #     channels=["conda-forge"],
        #     dependencies=[
        #         "python==3.11.6",
        #         "ipykernel==6.26.0",
        #         "ipywidgets==8.1.1",
        #         f"nebari-dask=={set_nebari_dask_version()}",
        #         "python-graphviz==0.20.1",
        #         "pyarrow==14.0.1",
        #         "s3fs==2023.10.0",
        #         "gcsfs==2023.10.0",
        #         "numpy=1.26.0",
        #         "numba=0.58.1",
        #         "pandas=2.1.3",
        #         "xarray==2023.10.1",
        #     ],
        # ),
        # "environment-dashboard.yaml": CondaEnvironment(
        #     name="dashboard",
        #     channels=["conda-forge"],
        #     dependencies=[
        #         "python==3.11.6",
        #         "cufflinks-py==0.17.3",
        #         "dash==2.14.1",
        #         "geopandas==0.14.1",
        #         "geopy==2.4.0",
        #         "geoviews==1.11.0",
        #         "gunicorn==21.2.0",
        #         "holoviews==1.18.1",
        #         "ipykernel==6.26.0",
        #         "ipywidgets==8.1.1",
        #         "jupyter==1.0.0",
        #         "jupyter_bokeh==3.0.7",
        #         "matplotlib==3.8.1",
        #         f"nebari-dask=={set_nebari_dask_version()}",
        #         "nodejs=20.8.1",
        #         "numpy==1.26.0",
        #         "openpyxl==3.1.2",
        #         "pandas==2.1.3",
        #         "panel==1.3.1",
        #         "param==2.0.1",
        #         "plotly==5.18.0",
        #         "python-graphviz==0.20.1",
        #         "rich==13.6.0",
        #         "streamlit==1.28.1",
        #         "sympy==1.12",
        #         "voila==0.5.5",
        #         "xarray==2023.10.1",
        #         "pip==23.3.1",
        #         {
        #             "pip": [
        #                 "streamlit-image-comparison==0.0.4",
        #                 "noaa-coops==0.1.9",
        #                 "dash_core_components==2.0.0",
        #                 "dash_html_components==2.0.0",
        #             ],
        #         },
        #     ],
        # ),
        "environment-bioscape.yaml": CondaEnvironment(
            name="BioSCape",
            channels=["conda-forge", "anaconda"],
            dependencies=[
                "accessible-pygments==0.0.4",
                "affine==2.4.0",
                "aiobotocore==2.12.2",
                "aiohttp==3.9.3",
                "aioitertools==0.11.0",
                "aiosignal==1.3.1",
                "alabaster==0.7.16",
                "alembic==1.13.1",
                "annotated-types==0.6.0",
                "anyio==4.3.0",
                "appdirs==1.4.4",
                "argon2-cffi==23.1.0",
                "argon2-cffi-bindings==21.2.0",
                "arrow==1.3.0",
                "asciitree==0.3.3",
                "asttokens==2.4.1",
                "async-lru==2.0.4",
                "async-timeout==4.0.3",
                "attrs==23.2.0",
                "awscliv2==2.1.1",
                "Babel==2.14.0",
                "backoff==2.2.1",
                "bcrypt==4.1.2",
                "beautifulsoup4==4.12.3",
                "bleach==6.1.0",
                "blinker==1.7.0",
                "bokeh==3.4.0",
                "boto3==1.34.51",
                "botocore==1.34.51",
                "bounded-pool-executor==0.0.3",
                "bqplot==0.12.43",
                "branca==0.7.1",
                "Brotli==1.1.0",
                "CacheControl==0.14.0",
                "cached-property==1.5.2",
                "cachey==0.2.1",
                "cachy==0.3.0",
                "Cartopy==0.22.0",
                "certifi==2024.2.2",
                "certipy==0.1.3",
                "cffi==1.16.0",
                "cftime==1.6.3",
                "charset-normalizer==3.3.2",
                "click==8.1.7",
                "click-default-group==1.2.4",
                "click-plugins==1.1.1",
                "cligj==0.7.2",
                "clikit==0.6.2",
                "cloudpickle==3.0.0",
                "coiled==1.16.0",
                "colorama==0.4.6",
                "colorcet==3.1.0",
                "coloredlogs==15.0.1",
                "comm==0.2.2",
                "configobj==5.0.8",
                "contextily==1.4.0",
                "contourpy==1.2.1",
                "crashtest==0.4.1",
                "cryptography==42.0.5",
                "curlify==2.2.1",
                "cycler==0.12.1",
                "cytoolz==0.12.3",
                "dask==2024.4.1",
                "dask-expr==1.0.11",
                "dask-gateway==2024.1.0",
                "dask-geopandas==0.3.1",
                "dask_labextension==7.0.0",
                "dataclasses==0.8",
                "datashader==0.16.0",
                "debugpy==1.8.1",
                "decorator==5.1.1",
                "defusedxml==0.7.1",
                "Deprecated==1.2.14",
                "distlib==0.3.8",
                "distributed==2024.4.1",
                "docopt==0.6.2",
                "docutils==0.20.1",
                "donfig==0.8.1.post0",
                "earthaccess==0.9.0",
                "ensureconda==1.4.4",
                "entrypoints==0.4",
                "exceptiongroup==1.2.0",
                "executing==2.0.1",
                "executor==23.2",
                "fabric==3.2.2",
                "fasteners==0.17.3",
                "filelock==3.13.4",
                "fiona==1.9.6",
                "flox==0.9.6",
                "folium==0.16.0",
                "fonttools==4.51.0",
                "fqdn==1.5.1",
                "frozenlist==1.4.1",
                "fsspec==2024.3.1",
                "GDAL==3.8.4",
                "geographiclib==1.52",
                "geopandas==0.14.3",
                "geopy==2.4.0",
                "geoviews==1.12.0",
                "gh-scoped-creds==4.1",
                "gilknocker==0.4.1",
                "gitdb==4.0.11",
                "GitPython==3.1.43",
                "greenlet==3.0.3",
                "h11==0.14.0",
                "h2==4.1.0",
                "h5coro==0.0.6",
                "h5grove==2.0.0",
                "h5netcdf==1.3.0",
                "h5py==3.10.0",
                "harmony-py==0.4.12",
                "hdf5plugin==4.4.0",
                "HeapDict==1.0.1",
                "holoviews==1.18.3",
                "hpack==4.0.0",
                "html5lib==1.1",
                "httpcore==1.0.5",
                "httpx==0.27.0",
                "humanfriendly==10.0",
                "hvplot==0.9.2",
                "hyperframe==6.0.1",
                "icepyx==1.0.0",
                "idna==3.6",
                "imagecodecs==2024.1.1",
                "imageio==2.34.0",
                "imagesize==1.4.1",
                "importlib_metadata==7.1.0",
                "importlib_resources==6.4.0",
                "intake==2.0.4",
                "invoke==2.2.0",
                "ipykernel==6.29.3",
                "ipyleaflet==0.18.2",
                "ipympl==0.9.3",
                "ipython==8.22.2",
                "ipython_genutils==0.2.0",
                "ipywidgets==8.1.2",
                "isoduration==20.11.0",
                "itslive==0.3.2",
                "jaraco.classes==3.4.0",
                "jaraco.context==4.3.0",
                "jaraco.functools==4.0.0",
                "jedi==0.19.1",
                "jeepney==0.8.0",
                "Jinja2==3.1.3",
                "jmespath==1.0.1",
                "joblib==1.4.0",
                "json5==0.9.24",
                "jsondiff==2.0.0",
                "jsonpointer==2.4",
                "jsonschema==4.21.1",
                "jsonschema-specifications==2023.12.1",
                "jupytext==1.16.1",
                "kerchunk==0.2.4",
                "keyring==25.1.0",
                "kiwisolver==1.4.5",
                "latexcodec==2.0.1",
                "lazy_loader==0.4",
                "linkify-it-py==2.0.3",
                "llvmlite==0.42.0",
                "locket==1.0.0",
                "lxml==5.1.0",
                "lz4==4.3.3",
                "Mako==1.3.2",
                "mapclassify==2.6.1",
                "Markdown==3.6",
                "markdown-it-py==3.0.0",
                "MarkupSafe==2.1.5",
                "matplotlib==3.8.4",
                "matplotlib-inline==0.1.6",
                "mdit-py-plugins==0.4.0",
                "mdurl==0.1.2",
                "mercantile==1.2.1",
                "mistune==3.0.2",
                "more-itertools==10.2.0",
                "msgpack-python==1.0.7",
                "multidict==6.0.5",
                "multimethod==1.11",
                "multipledispatch==0.6.0",
                "munkres==1.1.4",
                "mypy_extensions==1.0.0",
                "myst-nb==1.0.0",
                "myst-parser==2.0.0",
                "nbclient==0.10.0",
                "nbconvert==7.16.3",
                "nbdime==4.0.1",
                "nbformat==5.10.4",
                "nbgitpuller==1.2.1",
                "nest-asyncio==1.6.0",
                "netCDF4==1.6.5",
                "networkx==3.3",
                "notebook==7.1.2",
                "notebook-shim==0.2.4",
                "numba==0.59.1",
                "numcodecs==0.12.1",
                "numpy==1.26.4",
                "numpy_groupies==0.10.2",
                "oauthlib==3.2.2",
                "orjson==3.9.15",
                "overrides==7.7.0",
                "packaging==24.0",
                "pamela==1.1.0",
                "pandas==2.2.1",
                "pandocfilters==1.5.0",
                "panel==1.4.1",
                "param==2.1.0",
                "paramiko==3.4.0",
                "parso==0.8.4",
                "partd==1.4.1",
                "pastel==0.2.1",
                "patsy==0.5.6",
                "pexpect==4.9.0",
                "pickleshare==0.7.5",
                "pillow==10.3.0",
                "pip==24.0",
                "pip-requirements-parser==32.0.1",
                "pkginfo==1.10.0",
                "pkgutil-resolve-name==1.3.10",
                "platformdirs==4.2.0",
                "plotext==5.2.8",
                "pockets==0.9.1",
                "pooch==1.8.1",
                "pqdm==0.2.0",
                "progressbar2==4.2.0",
                "prometheus_client==0.20.0",
                "prompt-toolkit==3.0.42",
                "property-manager==3.0",
                "psutil==5.9.8",
                "ptyprocess==0.7.0",
                "pyarrow==15.0.2",
                "pyarrow-hotfix==0.6",
                "pybtex==0.24.0",
                "pybtex-docutils==1.0.3",
                "pycparser==2.22",
                "pyct==0.5.0",
                "pydantic==2.6.4",
                "pydantic-core==2.16.3",
                "pydap==3.3.0",
                "pydata-sphinx-theme==0.15.2",
                "Pygments==2.17.2",
                "PyJWT==2.8.0",
                "pykdtree==1.3.11",
                "pylev==1.4.0",
                "PyNaCl==1.5.0",
                "pyOpenSSL==24.0.0",
                "pyparsing==3.1.2",
                "pyproj==3.6.1",
                "pyresample==1.28.2",
                "pyshp==2.3.1",
                "PySocks==1.7.1",
                "pystac==1.10.0",
                "pystac-client==0.7.6",
                "python-cmr==0.9.0",
                "python-dateutil==2.8.2",
                "python-dotenv==0.20.0",
                "python-json-logger==2.0.7",
                "python-utils==3.8.2",
                "pytz==2024.1",
                "pyviz_comms==3.0.1",
                "PyWavelets==1.4.1",
                "PyYAML==6.0.1",
                "pyzmq==25.1.2",
                "rasterio==1.3.9",
                "rasterstats==0.19.0",
                "rechunker==0.5.2",
                "referencing==0.34.0",
                "requests==2.31.0",
                "rfc3339-validator==0.1.4",
                "rfc3986-validator==0.1.1",
                "rich==13.7.1",
                "rich-click==1.7.4",
                "rioxarray==0.15.3",
                "rpds-py==0.18.0",
                "Rtree==1.2.0",
                "ruamel.yaml==0.18.6",
                "ruamel.yaml.clib==0.2.8",
                "s3fs==2024.3.1",
                "s3transfer==0.10.1",
                "scikit-image==0.22.0",
                "scikit-learn==1.4.1.post1",
                "scipy==1.13.0",
                "seaborn==0.13.2",
                "SecretStorage==3.3.3",
                "Send2Trash==1.8.3",
                "setuptools==69.2.0",
                "setuptools-scm==8.0.4",
                "shapely==2.0.3",
                "simpervisor==1.0.0",
                "simplejson==3.19.2",
                "six==1.16.0",
                "sliderule==4.3.2",
                "smmap==5.0.0",
                "sniffio==1.3.1",
                "snowballstemmer==2.2.0",
                "snuggs==1.4.7",
                "sortedcontainers==2.4.0",
                "soupsieve==2.5",
                "spectral==0.23.1",
                "Sphinx==7.2.6",
                "sphinx-book-theme==1.1.2",
                "sphinx-comments==0.0.3",
                "sphinx-copybutton==0.5.2",
                "sphinx-jupyterbook-latex==1.0.0",
                "sphinx-multitoc-numbering==0.1.3",
                "sphinx-thebe==0.3.1",
                "sphinx-togglebutton==0.3.2",
                "sphinxcontrib-applehelp==1.0.8",
                "sphinxcontrib-bibtex==2.6.2",
                "sphinxcontrib-devhelp==1.0.6",
                "sphinxcontrib-htmlhelp==2.0.5",
                "sphinxcontrib-jsmath==1.0.1",
                "sphinxcontrib-napoleon==0.7",
                "sphinxcontrib-qthelp==1.0.7",
                "sphinxcontrib-serializinghtml==1.1.10",
                "SQLAlchemy==2.0.29",
                "statsmodels==0.14.1",
                "streamz==0.6.4",
                "tabulate==0.9.0",
                "tblib==3.0.0",
                "terminado==0.18.1",
                "threadpoolctl==3.4.0",
                "tifffile==2024.2.12",
                "tinycss2==1.2.1",
                "tinynetrc==1.3.1",
                "toml==0.10.2",
                "tomli==2.0.1",
                "tomlkit==0.12.4",
                "toolz==0.12.1",
                "tornado==6.4",
                "tqdm==4.66.2",
                "traitlets==5.14.2",
                "traittypes==0.2.1",
                "types-python-dateutil==2.9.0.20240316",
                "typing_extensions==4.11.0",
                "typing_utils==0.1.0",
                "uc-micro-py==1.0.3",
                "ujson==5.9.0",
                "unicodedata2==15.1.0",
                "uri-template==1.3.0",
                "urllib3==1.26.18",
                "verboselogs==1.7",
                "virtualenv==20.25.1",
                "wcwidth==0.2.13",
                "webcolors==1.13",
                "webencodings==0.5.1",
                "WebOb==1.8.7",
                "websocket-client==1.7.0",
                "wheel==0.43.0",
                "widgetsnbextension==4.0.10",
                "wrapt==1.16.0",
                "xarray==2024.3.0",
                "xyzservices==2024.4.0",
                "yarl==1.9.4",
                "zarr==2.17.2",
                "zict==3.0.0",
                "zipp==3.17.0",
                {
                    "pip": [
                        "async-generator==1.10",
                        "conda_lock==2.5.6",
                        "fastjsonschema==2.19.1",
                        "sphinx_design==0.5.0",
                        "sphinx_external_toc==1.0.1",
                        "nco==1.1.0",
                        "pure-eval==0.2.2",
                        "stack_data==0.6.2",
                        "xq==0.0.4",
                        "tzdata==2024.1"
                    ],
                },
            ]
        )
    }
    conda_store: CondaStore = CondaStore()
    argo_workflows: ArgoWorkflows = ArgoWorkflows()
    monitoring: Monitoring = Monitoring()
    telemetry: Telemetry = Telemetry()
    jupyterhub: JupyterHub = JupyterHub()
    jupyterlab: JupyterLab = JupyterLab()
    jhub_apps: JHubApps = JHubApps()


class OutputSchema(schema.Base):
    pass


# variables shared by multiple services
class KubernetesServicesInputVars(schema.Base):
    name: str
    environment: str
    endpoint: str
    realm_id: str
    node_groups: Dict[str, Dict[str, str]]
    jupyterhub_logout_redirect_url: str = Field(alias="jupyterhub-logout-redirect-url")
    forwardauth_middleware_name: str = _forwardauth_middleware_name
    cert_secret_name: Optional[str] = None


def _split_docker_image_name(image_name):
    name, tag = image_name.split(":")
    return {"name": name, "tag": tag}


class ImageNameTag(schema.Base):
    name: str
    tag: str


class CondaStoreInputVars(schema.Base):
    conda_store_environments: Dict[str, CondaEnvironment] = Field(
        alias="conda-store-environments"
    )
    conda_store_default_namespace: str = Field(alias="conda-store-default-namespace")
    conda_store_filesystem_storage: str = Field(alias="conda-store-filesystem-storage")
    conda_store_object_storage: str = Field(alias="conda-store-object-storage")
    conda_store_extra_settings: Dict[str, Any] = Field(
        alias="conda-store-extra-settings"
    )
    conda_store_extra_config: str = Field(alias="conda-store-extra-config")
    conda_store_image: str = Field(alias="conda-store-image")
    conda_store_image_tag: str = Field(alias="conda-store-image-tag")
    conda_store_service_token_scopes: Dict[str, Dict[str, Any]] = Field(
        alias="conda-store-service-token-scopes"
    )


class JupyterhubInputVars(schema.Base):
    jupyterhub_theme: Dict[str, Any] = Field(alias="jupyterhub-theme")
    jupyterlab_image: ImageNameTag = Field(alias="jupyterlab-image")
    jupyterlab_default_settings: Dict[str, Any] = Field(
        alias="jupyterlab-default-settings"
    )
    initial_repositories: str = Field(alias="initial-repositories")
    jupyterhub_overrides: List[str] = Field(alias="jupyterhub-overrides")
    jupyterhub_stared_storage: str = Field(alias="jupyterhub-shared-storage")
    jupyterhub_shared_endpoint: Optional[str] = Field(
        alias="jupyterhub-shared-endpoint", default=None
    )
    jupyterhub_profiles: List[JupyterLabProfile] = Field(alias="jupyterlab-profiles")
    jupyterhub_image: ImageNameTag = Field(alias="jupyterhub-image")
    jupyterhub_hub_extraEnv: str = Field(alias="jupyterhub-hub-extraEnv")
    idle_culler_settings: Dict[str, Any] = Field(alias="idle-culler-settings")
    argo_workflows_enabled: bool = Field(alias="argo-workflows-enabled")
    jhub_apps_enabled: bool = Field(alias="jhub-apps-enabled")
    cloud_provider: str = Field(alias="cloud-provider")
    jupyterlab_preferred_dir: Optional[str] = Field(alias="jupyterlab-preferred-dir")


class DaskGatewayInputVars(schema.Base):
    dask_worker_image: ImageNameTag = Field(alias="dask-worker-image")
    dask_gateway_profiles: Dict[str, Any] = Field(alias="dask-gateway-profiles")
    cloud_provider: str = Field(alias="cloud-provider")
    forwardauth_middleware_name: str = _forwardauth_middleware_name


class MonitoringInputVars(schema.Base):
    monitoring_enabled: bool = Field(alias="monitoring-enabled")
    minio_enabled: bool = Field(alias="minio-enabled")
    grafana_loki_overrides: List[str] = Field(alias="grafana-loki-overrides")
    grafana_promtail_overrides: List[str] = Field(alias="grafana-promtail-overrides")
    grafana_loki_minio_overrides: List[str] = Field(
        alias="grafana-loki-minio-overrides"
    )


class TelemetryInputVars(schema.Base):
    jupyterlab_pioneer_enabled: bool = Field(alias="jupyterlab-pioneer-enabled")
    jupyterlab_pioneer_log_format: Optional[str] = Field(
        alias="jupyterlab-pioneer-log-format"
    )


class ArgoWorkflowsInputVars(schema.Base):
    argo_workflows_enabled: bool = Field(alias="argo-workflows-enabled")
    argo_workflows_overrides: List[str] = Field(alias="argo-workflows-overrides")
    nebari_workflow_controller: bool = Field(alias="nebari-workflow-controller")
    workflow_controller_image_tag: str = Field(alias="workflow-controller-image-tag")
    keycloak_read_only_user_credentials: Dict[str, Any] = Field(
        alias="keycloak-read-only-user-credentials"
    )


class KubernetesServicesStage(NebariTerraformStage):
    name = "07-kubernetes-services"
    priority = 70

    input_schema = InputSchema
    output_schema = OutputSchema

    def tf_objects(self) -> List[Dict]:
        return [
            NebariTerraformState(self.name, self.config),
            NebariKubernetesProvider(self.config),
            NebariHelmProvider(self.config),
        ]

    def input_vars(self, stage_outputs: Dict[str, Dict[str, Any]]):
        domain = stage_outputs["stages/04-kubernetes-ingress"]["domain"]
        final_logout_uri = f"https://{domain}/hub/login"

        realm_id = stage_outputs["stages/06-kubernetes-keycloak-configuration"][
            "realm_id"
        ]["value"]
        cloud_provider = self.config.provider.value
        jupyterhub_shared_endpoint = (
            stage_outputs["stages/02-infrastructure"]
            .get("nfs_endpoint", {})
            .get("value")
        )
        keycloak_read_only_user_credentials = stage_outputs[
            "stages/06-kubernetes-keycloak-configuration"
        ]["keycloak-read-only-user-credentials"]["value"]

        conda_store_token_scopes = {
            "dask-gateway": {
                "primary_namespace": "",
                "role_bindings": {
                    "*/*": ["viewer"],
                },
            },
            "argo-workflows-jupyter-scheduler": {
                "primary_namespace": "",
                "role_bindings": {
                    "*/*": ["viewer"],
                },
            },
            "jhub-apps": {
                "primary_namespace": "",
                "role_bindings": {
                    "*/*": ["viewer"],
                },
            },
        }

        # Compound any logout URLs from extensions so they are are logged out in succession
        # when Keycloak and JupyterHub are logged out
        for ext in self.config.tf_extensions:
            if ext.logout != "":
                final_logout_uri = "{}?{}".format(
                    f"https://{domain}/{ext.urlslug}{ext.logout}",
                    urlencode({"redirect_uri": final_logout_uri}),
                )

        jupyterhub_theme = self.config.theme.jupyterhub
        if self.config.theme.jupyterhub.display_version and (
            not self.config.theme.jupyterhub.version
        ):
            jupyterhub_theme.update({"version": f"v{self.config.nebari_version}"})

        kubernetes_services_vars = KubernetesServicesInputVars(
            name=self.config.project_name,
            environment=self.config.namespace,
            endpoint=domain,
            realm_id=realm_id,
            node_groups=stage_outputs["stages/02-infrastructure"]["node_selectors"],
            jupyterhub_logout_redirect_url=final_logout_uri,
            cert_secret_name=(
                self.config.certificate.secret_name
                if self.config.certificate.type == "existing"
                else None
            ),
        )

        conda_store_vars = CondaStoreInputVars(
            conda_store_environments={
                k: v.model_dump() for k, v in self.config.environments.items()
            },
            conda_store_default_namespace=self.config.conda_store.default_namespace,
            conda_store_filesystem_storage=self.config.storage.conda_store,
            conda_store_object_storage=self.config.storage.conda_store,
            conda_store_service_token_scopes=conda_store_token_scopes,
            conda_store_extra_settings=self.config.conda_store.extra_settings,
            conda_store_extra_config=self.config.conda_store.extra_config,
            conda_store_image=self.config.conda_store.image,
            conda_store_image_tag=self.config.conda_store.image_tag,
        )

        jupyterhub_vars = JupyterhubInputVars(
            jupyterhub_theme=jupyterhub_theme.model_dump(),
            jupyterlab_image=_split_docker_image_name(
                self.config.default_images.jupyterlab
            ),
            jupyterhub_stared_storage=self.config.storage.shared_filesystem,
            jupyterhub_shared_endpoint=jupyterhub_shared_endpoint,
            cloud_provider=cloud_provider,
            jupyterhub_profiles=self.config.profiles.model_dump()["jupyterlab"],
            jupyterhub_image=_split_docker_image_name(
                self.config.default_images.jupyterhub
            ),
            jupyterhub_overrides=[json.dumps(self.config.jupyterhub.overrides)],
            jupyterhub_hub_extraEnv=json.dumps(
                self.config.jupyterhub.overrides.get("hub", {}).get("extraEnv", [])
            ),
            idle_culler_settings=self.config.jupyterlab.idle_culler.model_dump(),
            argo_workflows_enabled=self.config.argo_workflows.enabled,
            jhub_apps_enabled=self.config.jhub_apps.enabled,
            initial_repositories=str(self.config.jupyterlab.initial_repositories),
            jupyterlab_default_settings=self.config.jupyterlab.default_settings,
            jupyterlab_preferred_dir=self.config.jupyterlab.preferred_dir,
        )

        dask_gateway_vars = DaskGatewayInputVars(
            dask_worker_image=_split_docker_image_name(
                self.config.default_images.dask_worker
            ),
            dask_gateway_profiles=self.config.profiles.model_dump()["dask_worker"],
            cloud_provider=cloud_provider,
        )

        monitoring_vars = MonitoringInputVars(
            monitoring_enabled=self.config.monitoring.enabled,
            minio_enabled=self.config.monitoring.minio_enabled,
            grafana_loki_overrides=[json.dumps(self.config.monitoring.overrides.loki)],
            grafana_promtail_overrides=[
                json.dumps(self.config.monitoring.overrides.promtail)
            ],
            grafana_loki_minio_overrides=[
                json.dumps(self.config.monitoring.overrides.minio)
            ],
        )

        telemetry_vars = TelemetryInputVars(
            jupyterlab_pioneer_enabled=self.config.telemetry.jupyterlab_pioneer.enabled,
            jupyterlab_pioneer_log_format=self.config.telemetry.jupyterlab_pioneer.log_format,
        )

        argo_workflows_vars = ArgoWorkflowsInputVars(
            argo_workflows_enabled=self.config.argo_workflows.enabled,
            argo_workflows_overrides=[json.dumps(self.config.argo_workflows.overrides)],
            nebari_workflow_controller=self.config.argo_workflows.nebari_workflow_controller.enabled,
            workflow_controller_image_tag=self.config.argo_workflows.nebari_workflow_controller.image_tag,
            keycloak_read_only_user_credentials=keycloak_read_only_user_credentials,
        )

        return {
            **kubernetes_services_vars.model_dump(by_alias=True),
            **conda_store_vars.model_dump(by_alias=True),
            **jupyterhub_vars.model_dump(by_alias=True),
            **dask_gateway_vars.model_dump(by_alias=True),
            **monitoring_vars.model_dump(by_alias=True),
            **argo_workflows_vars.model_dump(by_alias=True),
            **telemetry_vars.model_dump(by_alias=True),
        }

    def check(
        self, stage_outputs: Dict[str, Dict[str, Any]], disable_prompt: bool = False
    ):
        directory = "stages/07-kubernetes-services"
        import requests

        # suppress insecure warnings
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        def _attempt_connect_url(
            url, verify=False, num_attempts=NUM_ATTEMPTS, timeout=TIMEOUT
        ):
            for i in range(num_attempts):
                response = requests.get(url, verify=verify, timeout=timeout)
                if response.status_code < 400:
                    print(f"Attempt {i+1} health check succeeded for url={url}")
                    return True
                else:
                    print(f"Attempt {i+1} health check failed for url={url}")
                time.sleep(timeout)
            return False

        services = stage_outputs[directory]["service_urls"]["value"]
        for service_name, service in services.items():
            service_url = service["health_url"]
            if service_url and not _attempt_connect_url(service_url):
                print(
                    f"ERROR: Service {service_name} DOWN when checking url={service_url}"
                )
                sys.exit(1)


@hookimpl
def nebari_stage() -> List[Type[NebariStage]]:
    return [KubernetesServicesStage]
