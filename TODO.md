# TODO

## Calidad de codigo

- [ ] Anadir mypy (type checking) -- configurado en `pyproject.toml`, falta integrar
- [ ] Reemplazar `assert` por `raise` en `public.py:163` (`limiter` property) --
      `assert` se elimina con `-O`

## Documentacion

- [ ] Migrar docstrings de Sphinx reST a NumPy style (gradual, al tocar cada modulo)
