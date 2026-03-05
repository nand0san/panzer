# Panzer

Libreria Python para gestionar conexiones REST a la API de Binance.

**Manual completo:** leer `AGENTS.md` antes de cualquier cambio (convenciones,
setup, git workflow, agent playbook).

Reglas minimas si no puedes leer AGENTS.md:
- Identificadores en ingles, docstrings/comentarios en espanol.
- Type hints obligatorios, sintaxis 3.10+.
- No hacer push sin aprobacion.
- **NUNCA** `git push github master` — el remote `github` es solo para publicacion
  con squash en la rama `github`. El historial de `master` es privado.
