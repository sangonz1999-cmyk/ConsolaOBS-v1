"""Avisos no bloqueantes (tipo "toast") en la esquina de la ventana.

A diferencia de messagebox, no frenan el programa ni piden un clic para
seguir: se muestran arriba de todo, a la derecha de la ventana principal,
y se van solos (o quedan fijos hasta que se los reemplace o se cierren).

Hay un solo aviso a la vez por 'canal' (ej. "conexion"): mostrar otro en
el mismo canal reemplaza el texto en vez de apilar ventanas.
"""
import tkinter as tk

from consola_obs import estado as E

COLORES = {
    "info": ("#1c2433", "#e8edf6", "#3d8bfd"),
    "ok": ("#16261f", "#e8f6ef", "#2fd693"),
    "aviso": ("#2a2416", "#f6efe0", "#ffb84d"),
    "error": ("#2a1719", "#f6e5e7", "#ff5d6c"),
}
ANCHO = 360
MARGEN = 18

_avisos = {}


def mostrar(texto, tipo="info", canal="general", duracion_ms=6000, al_clic=None):
    """Muestra (o reemplaza) el aviso del canal. duracion_ms=None lo deja
    fijo hasta cerrar() o hasta que llegue otro aviso al mismo canal.
    al_clic: función a llamar si se hace clic sobre el texto."""
    try:
        ventana = E.ventana
        if ventana is None or not ventana.winfo_exists():
            return
    except Exception:
        return
    fondo, frente, acento = COLORES.get(tipo, COLORES["info"])
    actual = _avisos.get(canal)
    if actual is None or not _existe(actual["top"]):
        actual = _crear(canal)
    top = actual["top"]
    try:
        top.configure(bg=acento)
        actual["cuerpo"].configure(bg=fondo)
        actual["texto"].configure(text=texto, bg=fondo, fg=frente,
                                  cursor="hand2" if al_clic else "")
        actual["cerrar"].configure(bg=fondo, fg=frente, activebackground=fondo)
        actual["texto"].unbind("<Button-1>")
        if al_clic:
            actual["texto"].bind("<Button-1>", lambda e: al_clic())
        if actual.get("id_fin"):
            ventana.after_cancel(actual["id_fin"])
            actual["id_fin"] = None
        if duracion_ms:
            actual["id_fin"] = ventana.after(duracion_ms, lambda: cerrar(canal))
        _ubicar(canal)
        top.deiconify()
        top.lift()
    except Exception:
        pass


def cerrar(canal="general"):
    actual = _avisos.pop(canal, None)
    if not actual:
        return
    try:
        if actual.get("id_fin"):
            E.ventana.after_cancel(actual["id_fin"])
    except Exception:
        pass
    try:
        actual["top"].destroy()
    except Exception:
        pass
    for otro in list(_avisos):
        _ubicar(otro)


def _existe(widget):
    try:
        return bool(widget.winfo_exists())
    except Exception:
        return False


def _crear(canal):
    top = tk.Toplevel(E.ventana)
    top.withdraw()
    top.overrideredirect(True)
    try:
        top.attributes("-topmost", True)
    except Exception:
        pass
    cuerpo = tk.Frame(top, padx=14, pady=10)
    cuerpo.pack(fill="both", expand=True, padx=(4, 0))
    texto = tk.Label(cuerpo, justify="left", anchor="w", wraplength=ANCHO - 60,
                     font=(getattr(E, "FUENTE_UI", "Segoe UI"), 10))
    texto.pack(side="left", fill="both", expand=True)
    boton = tk.Button(cuerpo, text="✕", relief="flat", bd=0, cursor="hand2",
                      font=(getattr(E, "FUENTE_UI", "Segoe UI"), 10),
                      command=lambda: cerrar(canal))
    boton.pack(side="right", anchor="n", padx=(10, 0))
    _avisos[canal] = {"top": top, "cuerpo": cuerpo, "texto": texto,
                      "cerrar": boton, "id_fin": None}
    return _avisos[canal]


def _ubicar(canal):
    """Apila los avisos abiertos desde abajo a la derecha de la ventana."""
    try:
        ventana = E.ventana
        ventana.update_idletasks()
        x_der = ventana.winfo_rootx() + ventana.winfo_width() - MARGEN
        y = ventana.winfo_rooty() + ventana.winfo_height() - MARGEN
        for nombre in list(_avisos):
            datos = _avisos[nombre]
            top = datos["top"]
            if not _existe(top):
                continue
            top.update_idletasks()
            alto = max(top.winfo_reqheight(), 40)
            y -= alto
            top.geometry(f"{ANCHO}x{alto}+{x_der - ANCHO}+{y}")
            y -= 8
    except Exception:
        pass
