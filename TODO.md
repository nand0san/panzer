# TODO

## Bugs

- [x] BUG: `BinancePublicClient.__init__` sobreescribe el dataclass, `__post_init__` nunca se ejecuta
- [x] BUG: Doble `acquire` de peso (en `BinancePublicClient.get()` y en `binance_public_get()`)
- [x] BUG: Metodo `acquire` suelto en `public.py` con atributos inexistentes

## Integracion pendiente

- [x] Integrar `weights.py` en el cliente para calcular pesos automaticamente
- [x] `.gitignore`: anadir excepciones para `*.md` necesarios

## Publicacion GitHub (bloqueante antes del primer push)

- [x] Reescribir `README.md` para v2 - documentaba la API v1 que ya no existe
- [x] Actualizar `CHANGELOG.md` - documentar la transicion v1 -> v2
- [x] Revisar que no haya archivos sensibles - auditoria OK, nada encontrado

## Calidad de codigo

- [x] Migrar `setup.py` a `pyproject.toml` (PEP 621) - base para ruff/mypy/pytest
- [x] Anadir ruff (lint + format)
- [ ] Anadir mypy (type checking)
- [ ] Tests automatizados con pytest (mocks de requests)
- [ ] GitHub Actions CI (lint + tests) - ahora viable con remote `github`

## Documentacion

- [ ] Migrar docstrings a NumPy style (al tocar cada modulo)
- [ ] Directorio `examples/` con ejemplo basico de uso - cara publica del repo

## Funcionalidad futura

- [ ] Signed requests (CredentialManager + peticiones firmadas)
- [ ] Retry automatico en 429 (con backoff basado en Retry-After)
