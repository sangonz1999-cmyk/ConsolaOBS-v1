"""Sincronización bidireccional de assets entre las 2 PCs (Padre/Hijo).

Módulo aislado: no toca la lógica actual del programa. Sincroniza la
carpeta de assets (efectos, imágenes de pads y música) comparando por
nombre + tamaño + mtime + sha256, copia lo faltante en ambas
direcciones, propaga borrados y resuelve conflictos por fecha (gana el
más nuevo). La API key sólo autoriza a tus 2 PCs a pedir/subir/borrar.
"""
