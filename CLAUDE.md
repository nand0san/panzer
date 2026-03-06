# Panzer

Libreria Python para gestionar conexiones REST a la API de Binance.

**Manual completo:** leer `AGENTS.md` antes de cualquier cambio (convenciones,
setup, git workflow, agent playbook).

Reglas minimas si no puedes leer AGENTS.md:
- Identificadores en ingles, docstrings/comentarios en espanol.
- Type hints obligatorios, sintaxis 3.10+.
- No hacer push sin aprobacion.
- **NUNCA** `git push github master` -- el remote `github` es solo para publicacion
  con squash en la rama `github`. El historial de `master` es privado.

## GitHub = escaparate

GitHub es un mero escaparate de codigo. **No se usa CI/CD** (ni GitHub Actions
ni ningun pipeline). La validacion (ruff, pytest) se ejecuta localmente.

## Sin retries automaticos

La libreria debe ser honesta: devuelve la respuesta o lanza la excepcion tal
cual. **No implementar retry automatico** (ni en 429 ni en ningun otro caso).
El usuario de la libreria decide su propia estrategia de reintentos.

## Commits: sin coautores

**NUNCA** incluir `Co-Authored-By` en ningun commit, ni en `master` ni en
`github`. Ningun agente, bot o herramienta debe figurar como colaborador.
El unico autor de los commits es el usuario. A nadie le importa que
herramientas se usan para programar.
