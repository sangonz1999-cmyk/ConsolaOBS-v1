"""Actualización automática desde GitHub Releases (módulo aislado).

El programa guarda su versión en version.py y GitHub es la fuente de
la versión más reciente (tags vX.Y.Z). Si hay una más nueva, se
descarga el ZIP completo a una carpeta temporal y un actualizador
separado (updater.py/updater.exe en la raíz, que corre con el programa
ya cerrado) reemplaza los archivos preservando config/ del usuario.
"""
