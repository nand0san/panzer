# AGENTS.md — Manual de operacion del repositorio Panzer

## 1. Purpose

Panzer es una libreria Python para gestionar conexiones REST a la API de Binance.
Maneja rate-limiting dinamico, credenciales cifradas, firmas de peticiones y
sincronizacion de reloj con el servidor.

Este documento es el manual de referencia para agentes LLM y desarrolladores humanos.

---

## 2. Repo facts (auto-detected)

### Identidad del paquete

- **Distribution name (PyPI):** `panzer`
- **Import name:** `panzer`
- **Build system:** `pyproject.toml` (PEP 621, setuptools backend).
- **Version local (`pyproject.toml`):** `2.0.0`
- **Version publicada (PyPI):** `1.0.11`
- **Gestion de version:** manual en `pyproject.toml` campo `version`. No hay `version.py`, SCM ni tags.
- **Python requerido:** `>= 3.11`
- **Python del venv:** 3.12.3

### Layout

- **Tipo:** flat layout (paquete `panzer/` en raiz, no `src/`).
- **Paquete principal:** `panzer`
- **Subpaquetes:**
  - `panzer.exchanges` (namespace para exchanges)
  - `panzer.exchanges.binance` (adaptador Binance)
  - `panzer.http` (cliente HTTP bajo nivel)
  - `panzer.rate_limit` (rate limiters)
  - `panzer.utils` (vacio)
- **Tests:** `tests/` con notebooks `.ipynb` (no hay tests pytest aun).
- **Notebooks de test:** `tests/exceptions.ipynb`, `tests/limiter.ipynb`, `tests/rate_limits_empirical.ipynb`
- **Directorios vacios:** `panzer/utils/`, `examples/`
- **Entrypoints CLI:** ninguno.
- **Unica dependencia runtime:** `requests` (declarada en `pyproject.toml`).

### Tooling de desarrollo

- **Linter/formatter:** `ruff` — configurado en `pyproject.toml` (`[tool.ruff]`).
- **Type checker:** pendiente (mypy configurado en `pyproject.toml` pero no integrado aun).
- **Test runner:** pendiente (pytest configurado en `pyproject.toml` pero sin tests `.py` aun).
- **CI:** ninguno detectado (no hay `.github/`, `.gitlab-ci.yml`).
- **Documentacion (Sphinx/MkDocs):** ninguna configurada (no hay `docs/`, `conf.py`).
- **Pre-commit:** no hay `.pre-commit-config.yaml`.

### Archivos relevantes en raiz

| Archivo | Contenido |
|---|---|
| `pyproject.toml` | Metadata PEP 621, build, config de ruff/mypy/pytest |
| `requirements.txt` | `requests` (mantenido por compatibilidad) |
| `CHANGELOG.md` | Historial de versiones (v1.x y v2.0.0) |
| `LICENSE` | Presente (MIT) |
| `README.md` | Documentacion principal del paquete |
| `.gitignore` | Extenso; excluye `*.md` excepto README y CHANGELOG |

### Advertencia .gitignore

`.gitignore` excluye `*.md` con excepciones explicitas para `README.md`,
`CHANGELOG.md`, `AGENTS.md`, `CLAUDE.md` y `TODO.md` (ya configuradas).

---

## 3. Coding conventions

### 3.1 Idiomas (estricto)

| Elemento | Idioma | Ejemplo |
|---|---|---|
| Nombres de modulos | ingles | `log_manager`, `time_sync`, `rate_limit` |
| Nombres de clases | ingles PascalCase | `BinancePublicClient`, `TimeOffsetEstimator` |
| Nombres de funciones/metodos | ingles snake_case | `handle_response()`, `_drop_old()` |
| Nombres de variables | ingles snake_case | `max_per_minute`, `bucket_id`, `sleep_for` |
| Constantes | ingles UPPER_SNAKE | `BINANCE_SPOT_BASE_URL`, `REQUEST_WEIGHT` |
| Metodos privados | prefijo `_` | `_build_exception()`, `_rollover_if_needed()` |
| Docstrings | **espanol** | `"""Realiza una peticion GET publica..."""` |
| Comentarios inline | **espanol** | `# Intentamos interpretar el payload` |
| Mensajes de log | **espanol** | `"Limite de seguridad alcanzado..."` |
| Mensajes de excepcion | **espanol** | `"Mercado no soportado: ..."` |

### 3.2 Docstrings — NumPy style (napoleon), Sphinx-ready

**Formato obligatorio** para funciones y clases publicas.

```python
def acquire(self, weight: int = 1, now: float | None = None) -> None:
    """
    Reserva capacidad de peso en la ventana actual.

    Si el consumo local + weight supera el umbral de seguridad, duerme
    hasta el inicio del siguiente minuto.

    Parameters
    ----------
    weight : int
        Peso a consumir en esta operacion (REQUEST_WEIGHT).
    now : float | None
        Epoch actual en segundos. None usa time.time().

    Raises
    ------
    ValueError
        Si weight <= 0.
    """
```

Reglas:

- Primera linea: resumen conciso en espanol (una frase).
- Cuerpo: describir contrato (pre/post condiciones), no repetir el codigo.
- Secciones Napoleon: `Parameters`, `Returns`, `Raises`, `Examples` cuando aplique.
- Type hints en la firma, no duplicar tipos en la docstring.
- Para funciones privadas simples: docstring de una linea basta.

> **Nota:** El codigo existente usa estilo Sphinx reST (`:param:`, `:return:`,
> `:raises:`). Codigo nuevo debe usar NumPy style. Migrar el existente solo
> cuando se modifique un metodo por otra razon.

### 3.3 Type hints

- **Obligatorios** en todas las funciones: parametros y retorno.
- Sintaxis moderna 3.10+: `float | None`, `list[dict]`, `dict[str, Any]`.
- `from __future__ import annotations` al inicio de cada modulo (ya presente en todo el repo).
- Usar `Literal[...]` para valores fijos: `MarketType = Literal["spot", "um", "cm"]`.
- Cobertura objetivo: 100% de firmas publicas, 95%+ privadas.

### 3.4 Estilo y arquitectura

- **Separacion de capas:** config (parseo) -> http (transporte) -> rate_limit (control) -> exchanges (alto nivel).
- **Funciones puras cuando sea posible.** Separar I/O de logica.
- **Errores:** excepciones explicitas con mensajes utiles en espanol. Jerarquia: `BinanceAPIException` como base.
- **Dataclasses** para modelos de datos (`@dataclass`): `RateLimit`, `ExchangeRateLimits`, `BinanceAPIErrorPayload`.
- **Logging:** patron existente — un `LogManager` por modulo al inicio del fichero:
  ```python
  _log = LogManager(
      name="panzer.<modulo>",
      folder="logs",
      filename="<modulo>.log",
      level="INFO",
  )
  ```

### 3.5 Imports y organizacion

Orden estricto, separado por lineas en blanco:

```python
# 1. __future__
from __future__ import annotations

# 2. stdlib
import threading
import time
from typing import Any, Optional

# 3. terceros
import requests

# 4. locales (panzer)
from panzer.log_manager import LogManager
from panzer.errors import handle_response
```

**Evitar imports circulares:** `log_manager.py` no importa nada de panzer (por diseno).
Si un modulo necesita algo de otro en el mismo nivel, mover la dependencia comun a un
modulo inferior o usar import local dentro de una funcion.

### 3.6 Donde colocar nuevo codigo

| Tipo | Ubicacion |
|---|---|
| Nuevo exchange (ej. Bybit) | `panzer/exchanges/bybit/` con `__init__.py` y modulos |
| Nuevo rate limiter | `panzer/rate_limit/<nombre>.py` y exportar en `__init__.py` |
| Utilidad general | `panzer/utils/<nombre>.py` (actualmente vacio) |
| Nuevo endpoint Binance | Anadir en `_ENDPOINTS` y metodo wrapper en `BinancePublicClient` |
| HTTP con firma (signed) | Nuevo modulo en `panzer/http/` (ej. `signed_client.py`) |

---

## 4. Project layout

```
panzer/                         # raiz del repo
├── panzer/                     # paquete importable
│   ├── __init__.py             # exporta BinancePublicClient
│   ├── errors.py               # BinanceAPIException, handle_response
│   ├── log_manager.py          # LogManager (wrapper logging)
│   ├── time_sync.py            # TimeOffsetEstimator
│   ├── exchanges/
│   │   ├── __init__.py
│   │   └── binance/
│   │       ├── __init__.py
│   │       ├── config.py       # parseo de /exchangeInfo y rate limits
│   │       ├── public.py       # BinancePublicClient (alto nivel)
│   │       └── weights.py      # tablas de pesos por endpoint y mercado
│   ├── http/
│   │   ├── __init__.py         # exporta binance_public_get
│   │   └── client.py           # cliente HTTP bajo nivel
│   ├── rate_limit/
│   │   ├── __init__.py         # exporta BinanceFixedWindowLimiter
│   │   └── binance_fixed.py    # rate limiter ventana fija
│   └── utils/                  # vacio
├── tests/
│   ├── __init__.py
│   ├── exceptions.ipynb        # pruebas manuales de errores
│   └── limiter.ipynb           # pruebas manuales del rate limiter
├── examples/                   # vacio
├── logs/                       # generados en runtime (gitignored)
├── pyproject.toml
├── requirements.txt
├── AGENTS.md
├── CLAUDE.md
├── TODO.md
├── CHANGELOG.md
├── LICENSE
└── README.md
```

---

## 5. Setup & run

### Crear entorno virtual e instalar

```bash
cd /home/nando/PycharmProjects/panzer
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

La instalacion editable (`-e .`) resuelve dependencias de `pyproject.toml`
(solo `requests`) y permite importar `panzer` directamente.

### Uso basico

```python
from panzer import BinancePublicClient

client = BinancePublicClient(market="spot", safety_ratio=0.9)
client.ensure_time_offset_ready(min_samples=3)
klines = client.klines("BTCUSDT", "1m", limit=5)
```

### Pruebas manuales rapidas

Cada modulo principal tiene un bloque `if __name__ == "__main__"` para prueba rapida:

```bash
python -m panzer.http.client
python -m panzer.rate_limit.binance_fixed
python -m panzer.exchanges.binance.config
python -m panzer.exchanges.binance.public
```

### Variables de entorno

No se detectan variables de entorno relevantes para la API publica.
Para endpoints firmados (futuro), se espera que las credenciales se gestionen
via `CredentialManager` (mencionado en README, no implementado en v2).

---

## 6. Tests / lint / type-check

### Estado actual

- **Linter/formatter:** `ruff` configurado y limpio (`ruff check panzer/` pasa sin errores).
- **Type checker:** `mypy` configurado en `pyproject.toml` pero no integrado aun.
- **Test runner:** `pytest` configurado en `pyproject.toml` pero sin tests `.py` aun.
- **Tests manuales:** notebooks Jupyter en `tests/` (requieren red).
- **No hay CI/CD.**

### Lint y formato

```bash
ruff check panzer/          # lint
ruff format panzer/          # auto-format
ruff format --check panzer/  # verificar formato sin modificar
```

### Ejecucion de los notebooks existentes

```bash
pip install jupyter
jupyter nbconvert --to notebook --execute tests/exceptions.ipynb
jupyter nbconvert --to notebook --execute tests/limiter.ipynb
jupyter nbconvert --to notebook --execute tests/rate_limits_empirical.ipynb
```

### Definition of done

Antes de mergear cualquier cambio:

1. `ruff check panzer/` pasa sin errores.
2. `ruff format --check panzer/` pasa sin errores.
3. `python -m panzer.exchanges.binance.public` ejecuta sin error.
4. No hay warnings de import al hacer `from panzer import BinancePublicClient`.

---

## 7. Documentation

### Estado actual

- **No hay sistema de documentacion configurado** (ni Sphinx ni MkDocs).
- La documentacion vive en `README.md` y en los docstrings de cada modulo.

### Convenciones de docstrings para futura generacion automatica

- Formato: NumPy style (napoleon) — compatible con `sphinx.ext.napoleon`.
- `from __future__ import annotations` en todos los modulos.
- Los docstrings de modulo describen el proposito y las caracteristicas principales.
- Los docstrings de clase describen el contrato, no la implementacion.

---

## 8. Binance rate limiting — modelo de referencia

Fuente: documentacion oficial de Binance (developers.binance.com), marzo 2026.

### 8.1 Tipos de rate limit

Binance define tres tipos en el array `rateLimits` de `/exchangeInfo`:

| Tipo | Scope | Intervalo tipico | Header de seguimiento |
|---|---|---|---|
| `REQUEST_WEIGHT` | por IP | 1 minuto (1M) | `X-MBX-USED-WEIGHT-1M` |
| `RAW_REQUESTS` | por IP | 5 minutos (5M) | `X-MBX-USED-WEIGHT-5M` |
| `ORDERS` | por cuenta | 10s / 1d | `X-MBX-ORDER-COUNT-10S`, `X-MBX-ORDER-COUNT-1D` |

**Los limites son por IP, no por API key** (excepto ORDERS, que es por cuenta).

### 8.2 Ventanas fijas (fixed windows)

- Intervalos: `S` (segundo), `M` (minuto), `H` (hora), `D` (dia).
- `intervalNum`: multiplicador (ej. intervalNum=5 + M = ventana de 5 minutos).
- Los headers usan la notacion `(intervalNum)(intervalLetter)`: `X-MBX-USED-WEIGHT-1M`.
- La ventana se calcula como `epoch_seconds // (intervalNum * interval_seconds)`.
  Para REQUEST_WEIGHT con intervalo 1M: `bucket_id = epoch // 60`.
- Al cambiar de bucket, el contador se reinicia a 0.

### 8.3 Violaciones y baneos

| HTTP | Significado | Accion |
|---|---|---|
| 429 | Limite excedido | Parar y esperar `Retry-After` segundos |
| 418 | IP baneada por abuso (seguir tras 429) | Esperar `Retry-After` segundos |

- Ban escalado: de 2 minutos a 3 dias para reincidentes.
- Header `Retry-After` presente en ambos codigos.
- Error `-1003`: "Too much request weight used".
- Error `-1008`: Proteccion de sistema (ordenes reduce-only exentas).

### 8.4 Limites tipicos por mercado

Estos son los valores tipicos actuales. Se obtienen dinamicamente de `/exchangeInfo`
y pueden cambiar sin previo aviso.

| Mercado | REQUEST_WEIGHT/1M | RAW_REQUESTS/5M | ORDERS/10S | ORDERS/1D |
|---|---|---|---|---|
| Spot | 6000 | 61000 | 100 | 200000 |
| Futures UM | ~2400 | — | — | — |
| Futures CM | ~2400 | — | — | — |

> Los valores exactos de futures se obtienen de `/fapi/v1/exchangeInfo` y
> `/dapi/v1/exchangeInfo`. Panzer los carga dinamicamente.

### 8.5 Tabla de pesos por endpoint

Los pesos estan codificados en `panzer/exchanges/binance/weights.py`.
Consultar ese archivo para la referencia completa con funciones de peso variable.

**Spot (/api/v3/)**

| Endpoint | Peso | Notas |
|---|---|---|
| ping | 1 | |
| time | 1 | |
| exchangeInfo | 20 | |
| depth | 5 / 25 / 50 / 250 | segun limit: 1-100 / 101-500 / 501-1000 / 1001-5000 |
| trades | 25 | |
| historicalTrades | 25 | |
| aggTrades | 4 | |
| klines | 2 | |
| avgPrice | 2 | |
| ticker/24hr | 2 / 40 / 80 | 1 symbol=2, 1-20=2, 21-100=40, sin symbol=80 |
| ticker/price | 2 / 4 | con symbol=2, sin symbol=4 |
| ticker/bookTicker | 2 / 4 | con symbol=2, sin symbol=4 |
| order (POST/DELETE) | 1 | |
| account | 10 | |
| myTrades | 10 | |
| allOrders | 20 | |
| openOrders | 3 | |

**Futures UM (/fapi/v1/)**

| Endpoint | Peso | Notas |
|---|---|---|
| ping | 1 | |
| time | 1 | |
| exchangeInfo | 1 | (mucho menor que spot) |
| depth | 2 / 5 / 10 / 20 | segun limit: 5-50 / 100 / 500 / 1000 |
| trades | 5 | |
| aggTrades | 20 | |
| klines | 1 / 2 / 5 / 10 | segun limit: 1-99 / 100-499 / 500-1000 / >1000 |
| premiumIndex | 1 / 10 | con symbol=1, sin symbol=10 |
| ticker/24hr | 1 / 40 | con symbol=1, sin symbol=40 |
| ticker/price | 1 / 2 | con symbol=1, sin symbol=2 |
| ticker/bookTicker | 2 / 5 | con symbol=2, sin symbol=5 |
| openInterest | 1 | |

**Futures CM (/dapi/v1/)** — misma estructura que UM con paths `/dapi/`.

### 8.6 Arquitectura de rate limiting en Panzer

```
/exchangeInfo ──> config.py ──> ExchangeRateLimits (limites dinamicos)
                                        │
                                        ▼
                              BinanceFixedWindowLimiter
                              - bucket_id = epoch // 60
                              - used_local (contador)
                              - safety_ratio (0.9 = no superar 90%)
                                        │
                                        ▼
                              acquire(weight) ──> duerme si projected > effective_limit
                                        │
                                        ▼
                              update_from_headers() ──> sincroniza con X-MBX-USED-WEIGHT-1M
```

```
weights.py ──> get_weight(market, endpoint, params) ──> peso estimado
```

### 8.7 Mantenimiento de pesos

Los pesos pueden cambiar cuando Binance actualiza su API. Para actualizar:

1. Consultar la documentacion oficial de cada endpoint.
2. Editar `panzer/exchanges/binance/weights.py`.
3. Las funciones de peso variable estan claramente separadas al inicio del archivo.
4. Los diccionarios `SPOT_WEIGHTS`, `FUTURES_UM_WEIGHTS`, `FUTURES_CM_WEIGHTS`
   agrupan los pesos por mercado.
5. La funcion `get_weight(market, endpoint, params)` es el punto unico de consulta.

---

## 9. PyPI status


| Campo | Valor |
|---|---|
| Distribution name | `panzer` |
| Import name | `panzer` |
| Ultima version PyPI | 1.0.11 |
| Version local (pyproject.toml) | 2.0.0 |
| Summary | REST API manager for Binance API. Manages weights and credentials simply and securely. |
| Autor | nand0san |
| Licencia | MIT |
| Python requerido | >= 3.11 |
| Homepage | https://github.com/nand0san/panzer |
| PyPI URL | https://pypi.org/project/panzer/ |
| Versiones publicadas | 0.1.0, 1.0.0 - 1.0.11 (12 releases) |

### Flujo de publicacion

```bash
# Build
python -m build

# Verificar metadata
twine check dist/*

# Subir a PyPI
twine upload dist/*
```

No hay scripts de deploy automatizados. Hubo un `deploy.bat` (gitignored).

---

## 10. Git workflow

### Topologia

| Remote | URL | Uso |
|---|---|---|
| `origin` | `ssh://ffad@192.168.89.201/.../panzer` | Desarrollo privado (NAS). Push libre. |
| `github` | `git@github.com:nand0san/panzer.git` | Publicacion publica. Solo rama `github`, con squash. |

- **Rama principal de desarrollo:** `master` (en `origin`).
- **Rama publica:** `github` (en remote `github`). Solo para releases.
- **Tags:** ninguno.

### Convencion de ramas

No hay ramas feature ni dev. Desarrollo directo en `master`.

### Flujo de trabajo — desarrollo (origin)

```bash
# Sincronizar
git pull origin master

# Trabajar, commit
git add <archivos>
git commit -m "descripcion concisa en imperativo"

# Push al servidor privado
git push origin master
```

### Flujo de publicacion - GitHub (IMPORTANTE)

GitHub es **solo para publicacion**. El historial de `master` es privado y no
debe exponerse en GitHub. La rama `github` es **huerfana** (sin historial
compartido con `master`) para evitar fugas de metadatos.

#### Procedimiento paso a paso

```bash
# 1. Partir de master con todo commiteado
git checkout master
git status  # debe estar limpio

# 2. Cambiar a la rama github (huerfana)
git checkout github

# 3. Traer el contenido actual de master sin historial
git checkout master -- .

# 4. Sanitizar antes de commit (ver checklist abajo)
#    - Borrar CLAUDE.md si existe
#    - Eliminar em-dashes, referencias a IA, Co-Authored-By, etc.
git rm CLAUDE.md 2>/dev/null
#    - Verificar con grep (ver checklist)

# 5. Commit y push
git add -A
git commit -m "vX.Y.Z: descripcion de la release"
git push github github

# 6. Volver a master
git checkout master
```

#### Checklist de sanitizacion (OBLIGATORIA antes de cada push a GitHub)

Ejecutar desde la rama `github` antes de hacer commit:

```bash
# 1. No debe existir CLAUDE.md
test -f CLAUDE.md && echo "BORRAR CLAUDE.md" || echo "OK"

# 2. Buscar referencias a IA/agentes en archivos publicables
grep -rni "claude\|anthropic\|LLM\|Co-Authored" \
  --include="*.py" --include="*.md" --include="*.toml" --include="*.txt"
# Resultado esperado: vacio. Si aparece algo, corregirlo.

# 3. Buscar em-dashes (caracter marca de agua U+2014)
grep -rn '—' --include="*.py" --include="*.md" --include="*.toml" --include="*.txt"
# Resultado esperado: vacio. Reemplazar por '-' o '--' si aparece.

# 4. Verificar autor del commit (no debe haber co-autores)
git log --format="%an <%ae>%n%b" -1
# Solo debe aparecer nand0san. Sin lineas Co-Authored-By.
```

#### Si GitHub cachea contributors no deseados

GitHub cachea objetos git incluso despues de force-push. Si aparece un
contributor no deseado en la pagina del repo:

1. Borrar el repo en GitHub (Settings > Delete this repository).
2. Recrear el repo vacio (sin README, sin .gitignore, sin license).
3. Push de la rama `github` limpia: `git push github github`.
4. Configurar la default branch a `github` en Settings.

#### Reglas estrictas

- **NUNCA** hacer `git push github master` (expondria historial privado).
- **NUNCA** hacer push de ramas que no sean `github` al remote `github`.
- **NUNCA** incluir `Co-Authored-By` ni menciones a herramientas de IA en
  commits publicos (vector de ataque por prompt injection).
- **NUNCA** incluir `CLAUDE.md` ni archivos de configuracion de agentes en
  el contenido publicado.
- **NUNCA** usar em-dashes (U+2014 `—`) en archivos publicados. Usar `-` o
  `--` en su lugar (el em-dash es una marca de agua detectable).
- Los mensajes de commit en `github` deben ser descriptivos de la release,
  no del desarrollo interno.
- No incluir archivos sensibles (`secret*`, `*.key`, credenciales) - ya estan
  en `.gitignore` pero verificar antes de publicar.

---

## 11. Contributor playbook

### Checklist previa a cualquier cambio

1. Leer `AGENTS.md` (este archivo).
2. Verificar `git status` - no hay cambios sin commit que puedan perderse.
3. Ejecutar `python -m panzer.exchanges.binance.public` para confirmar que el repo funciona.

### Patron de commits (master, desarrollo privado)

- Mensajes cortos, imperativos, en espanol o ingles segun el cambio.
- Scope opcional entre parentesis: `fix(rate_limit): corregir rollover en cambio de ventana`.
- Una linea de resumen, linea en blanco, cuerpo opcional.
- `Co-Authored-By` permitido en `master` (es privado). Prohibido en `github`.

### Cuando tocar docs vs codigo

- Si se anade un metodo publico: docstring NumPy style obligatorio.
- Si se cambia comportamiento de un metodo existente: actualizar su docstring.
- Si se anade un modulo nuevo: docstring de modulo describiendo proposito.
- No crear archivos `.md` adicionales sin que se pida explicitamente.

### Cada cambio debe documentar

- Archivos creados o modificados (rutas).
- Si se modifico codigo: justificacion breve del cambio.
- Si hay riesgos o ambiguedades: mencionarlos explicitamente.

### Cosas que NO hacer

- No instalar dependencias nuevas sin aprobacion.
- No modificar `pyproject.toml` sin aprobacion.
- No crear archivos en `logs/`, `examples/`, o `panzer/utils/` sin justificacion.
- No hacer push sin aprobacion explicita.
- No ejecutar notebooks (requieren red para llamar a Binance).
- **NUNCA** hacer `git push github master` - expondria el historial privado.
- **NUNCA** hacer push al remote `github` de ramas que no sean `github`.
- **NUNCA** incluir referencias a herramientas de IA en contenido publicado
  (commits, archivos, metadata). Ver seccion 10 para checklist completa.

---

## 12. Quality gaps (pendientes)

Carencias detectadas que aun no se han implementado.

### Testing

- **Gap:** No hay tests automatizados (pytest/unittest).
- **Propuesta:** Anadir `pytest` + `pytest-mock`. Crear `tests/test_errors.py`,
  `tests/test_rate_limit.py`, `tests/test_time_sync.py` con mocks de `requests`.
- **Cobertura:** Anadir `pytest-cov` y objetivo minimo 80%.
- **Config:** ya preparada en `pyproject.toml` (`[tool.pytest.ini_options]`).

### Type checking

- **Gap:** `mypy` configurado en `pyproject.toml` pero no integrado aun.
- **Propuesta:** Instalar `mypy`, resolver errores y anadir al CI.

### CI

- **Gap:** No hay pipeline CI.
- **Propuesta:** GitHub Actions basico (ruff + pytest) en `.github/workflows/ci.yml`.

### Documentacion

- **Gap:** No hay Sphinx/MkDocs. Docstrings en proceso de migracion a NumPy style.
- **Propuesta:** Sphinx + napoleon + autodoc cuando la migracion de docstrings avance.
