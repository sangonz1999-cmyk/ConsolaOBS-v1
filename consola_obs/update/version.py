"""Única fuente de la versión del programa (Fase 1 del auto-update).

REGLA: cada Release en GitHub se taguea vX.Y.Z (ej: v1.1.3) y esta
constante se sube al mismo número ANTES de compilar el .exe de esa
release. version_info.txt (metadatos del .exe) se mantiene igual a
mano en el mismo commit.
"""
VERSION = "1.2.0"
