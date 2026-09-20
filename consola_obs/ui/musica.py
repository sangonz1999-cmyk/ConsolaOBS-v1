"""Mini player de música (Fase 3): barra compacta al pie del panel
de fuentes con transporte, título y progreso clickeable (seek exacto
vía SetMediaInputCursor). Se reconstruye con construir_cuerpo, como
el resto de la interfaz.

Elegir tema todavía es provisorio: abre un selector de archivo para
poder probar el transporte contra OBS real. En Fase 4 este botón
abre la ventana biblioteca y este camino desaparece.
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs.audio import musica as mod_musica
from consola_obs.audio import rutas_obs as mod_rutas_obs

ALTURA_MINI = 82
INTERVALO_REFRESCO_MS = 250
COLOR_PISTA = "#242d3d"
COLOR_TIEMPO = "#8fa0bd"

_w = {}
_loop = {"en_marcha": False}


def _vivos():
    try:
        return bool(_w.get("marco") and _w["marco"].winfo_exists())
    except Exception:
        return False


def _necesita_conexion():
    if E.conectado:
        return True
    try:
        messagebox.showinfo("Sin conexión", "Conectate a OBS para usar la música.")
    except Exception:
        pass
    return False


def _necesita_tema(snap):
    if snap.get("rel"):
        return True
    try:
        messagebox.showinfo("Sin música", "Elegí un tema con el botón\n🎵 Elegir tema…")
    except Exception:
        pass
    return False


def _boton_transporte(padre, texto, comando, ancho=3):
    boton = tk.Button(
        padre, text=texto, width=ancho, bg="#242d3d", fg="white",
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, font=(E.FUENTE_UI, 11), cursor="hand2",
        command=comando,
    )
    boton.pack(side="left", padx=1)
    return boton


def _alternar_playpausa():
    if not _necesita_conexion():
        return
    snap = mod_musica.estado_actual()
    if snap["estado"] == "SONANDO":
        mod_musica.pausar()
    elif snap["estado"] == "PAUSADA" or snap.get("rel"):
        mod_musica.reanudar()
    else:
        _necesita_tema(snap)


def _detener():
    if not _necesita_conexion():
        return
    if not _necesita_tema(mod_musica.estado_actual()):
        return
    mod_musica.detener()


def _reiniciar():
    if not _necesita_conexion():
        return
    if not _necesita_tema(mod_musica.estado_actual()):
        return
    mod_musica.reiniciar()


def _anterior():
    if not _necesita_conexion():
        return
    if not _necesita_tema(mod_musica.estado_actual()):
        return
    mod_musica.anterior()


def _siguiente():
    if not _necesita_conexion():
        return
    if not _necesita_tema(mod_musica.estado_actual()):
        return
    mod_musica.siguiente()


def _alternar_repetir():
    if not _necesita_conexion():
        return
    try:
        mod_musica.alternar_repetir()
    except Exception:
        pass
    _refrescar_mini_player()


def _elegir_tema_provisorio():
    """Selector de archivo PROVISORIO (Fase 3): permite probar el
    transporte sin la biblioteca (llega en Fase 4 y reemplaza esto)."""
    if not _necesita_conexion():
        return
    ruta = filedialog.askopenfilename(
        title="Elegí un tema para el stream",
        filetypes=[
            ("Archivos de audio", "*.mp3 *.wav *.ogg *.flac *.m4a"),
            ("Todos los archivos", "*.*"),
        ],
    )
    if not ruta:
        return
    if not mod_rutas_obs.es_audio(ruta):
        try:
            messagebox.showwarning("No es audio", "Elegí un archivo de audio.")
        except Exception:
            pass
        return
    mod_musica.reproducir_archivo(ruta)


def _clic_progreso(event):
    """Clic en la barra = salto al momento exacto (seek en ms)."""
    if not E.conectado:
        return
    try:
        snap = mod_musica.estado_actual()
        dur = float(snap.get("duracion_ms") or 0.0)
        if dur <= 0 or not snap.get("rel"):
            return
        ancho = _w["progreso"].winfo_width()
        if ancho <= 1:
            return
        frac = min(1.0, max(0.0, float(event.x) / float(ancho)))
        mod_musica.seek_ms(frac * dur)
    except Exception:
        pass


def _dibujar_progreso(frac):
    try:
        lienzo = _w["progreso"]
        ancho = lienzo.winfo_width()
        alto = lienzo.winfo_height()
        if ancho <= 1 or alto <= 1:
            return
        lienzo.delete("all")
        lienzo.create_rectangle(0, 0, ancho, alto, fill=COLOR_PISTA, outline="")
        hasta = int(ancho * min(1.0, max(0.0, frac)))
        if hasta > 0:
            lienzo.create_rectangle(0, 0, hasta, alto, fill=E.color_acento(), outline="")
    except Exception:
        pass


def _refrescar_mini_player():
    if not _vivos():
        _loop["en_marcha"] = False
        return
    try:
        snap = mod_musica.estado_actual()
        titulo = snap.get("titulo")
        if titulo:
            texto = ("♪ " + titulo)[:48]
            _w["titulo"].config(text=texto, fg="white")
        else:
            _w["titulo"].config(text="Sin música — 🎵 Elegí un tema…", fg="#828da6")
        _w["play"].config(text="⏸" if snap["estado"] == "SONANDO" else "▶")
        dur = float(snap.get("duracion_ms") or 0.0)
        cur = float(snap.get("cursor_ms") or 0.0)
        _w["tiempos"].config(
            text=f"{mod_musica.formatear_ms(cur)} / {mod_musica.formatear_ms(dur)}"
        )
        _dibujar_progreso(cur / dur if dur > 0 else 0.0)
        _w["repetir"].config(fg=(E.color_acento() if snap.get("repetir") else "#5b6478"))
    except Exception:
        pass
    try:
        E.ventana.after(INTERVALO_REFRESCO_MS, _refrescar_mini_player)
    except Exception:
        _loop["en_marcha"] = False


def construir_mini_player():
    """Crea la barra al pie del panel de fuentes (se llama al final de
    construir_cuerpo, así sobrevive a cambios de tema/diseño)."""
    try:
        viejo = _w.get("marco")
        if viejo is not None:
            try:
                viejo.destroy()
            except Exception:
                pass
        _w.clear()
        _loop["en_marcha"] = False
    except Exception:
        pass

    marco = tk.Frame(E.marco_fuentes, bg=E.color_barra_titulo(), height=ALTURA_MINI)
    marco.pack(side="bottom", fill="x")
    marco.pack_propagate(False)
    _w["marco"] = marco

    tk.Frame(marco, bg=E.color_acento(), height=2).pack(side="top", fill="x")

    fila = tk.Frame(marco, bg=E.color_barra_titulo())
    fila.pack(side="top", fill="x", padx=8, pady=(6, 2))

    _w["play"] = _boton_transporte(fila, "▶", _alternar_playpausa)
    _boton_transporte(fila, "⏹", _detener)
    _boton_transporte(fila, "↻", _reiniciar)
    _boton_transporte(fila, "⏮", _anterior)
    _boton_transporte(fila, "⏭", _siguiente)
    _w["repetir"] = _boton_transporte(fila, "🔁", _alternar_repetir)

    _w["titulo"] = tk.Label(
        fila, text="Sin música — 🎵 Elegí un tema…", bg=E.color_barra_titulo(),
        fg="#828da6", font=(E.FUENTE_UI, 10, "bold"), anchor="w",
    )
    _w["titulo"].pack(side="left", fill="x", expand=True, padx=(8, 4))

    _w["tiempos"] = tk.Label(
        fila, text="00:00 / 00:00", bg=E.color_barra_titulo(),
        fg=COLOR_TIEMPO, font=(E.FUENTE_UI, 8),
    )
    _w["tiempos"].pack(side="left", padx=(0, 6))

    tk.Button(
        fila, text="🎵 Elegir tema…", bg="#242d3d", fg="white",
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=_elegir_tema_provisorio,
    ).pack(side="left")

    _w["progreso"] = tk.Canvas(
        marco, height=12, bg=COLOR_PISTA, highlightthickness=0, cursor="hand2"
    )
    _w["progreso"].pack(side="top", fill="x", padx=10, pady=(2, 6))
    _w["progreso"].bind("<Button-1>", _clic_progreso)

    if not _loop["en_marcha"]:
        _loop["en_marcha"] = True
        try:
            E.ventana.after(INTERVALO_REFRESCO_MS, _refrescar_mini_player)
        except Exception:
            _loop["en_marcha"] = False
