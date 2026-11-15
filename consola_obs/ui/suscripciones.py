"""Conecta la interfaz Tkinter con los avisos del núcleo.

El núcleo (obs/, nucleo/) ya no llama funciones de la interfaz: emite
avisos (ver nucleo/avisos.py) y acá se decide qué hace la ventana con
cada uno. Una interfaz nueva tendría su propio archivo como este.
"""
from consola_obs.nucleo import avisos


def registrar():
    from consola_obs.ui import aviso as mod_aviso
    from consola_obs.ui import cabecera as mod_ui_cabecera
    from consola_obs.ui import musica as mod_ui_musica
    from consola_obs.ui import soundboard as mod_ui_soundboard
    from consola_obs.ui import tarjeta_fuente as mod_ui_tarjeta
    from consola_obs.obs import cliente as mod_obs_cliente

    avisos.suscribir("fuente_cambiada", mod_ui_tarjeta.al_cambiar_fuente)
    avisos.suscribir("fuente_renombrada", mod_ui_tarjeta.al_renombrar_fuente)
    avisos.suscribir("filtros_cambiados", mod_ui_tarjeta.al_cambiar_filtros)
    avisos.suscribir("escena_cambiada", mod_ui_tarjeta.al_cambiar_escena)
    avisos.suscribir("coleccion_cambiada", mod_ui_tarjeta._refrescar_titulo_escena)
    avisos.suscribir("lista_fuentes_cambio", mod_ui_tarjeta.actualizar)
    avisos.suscribir("conectado", mod_ui_tarjeta.actualizar)

    def _aviso_conexion(tipo, texto, fijo):
        mod_aviso.mostrar(texto, tipo=tipo, canal="conexion",
                          duracion_ms=None if fijo else 5000,
                          al_clic=mod_obs_cliente._reconectar_con_lo_guardado if fijo else None)

    avisos.suscribir("aviso_conexion", _aviso_conexion)
    avisos.suscribir("aviso_conexion_cerrar", lambda: mod_aviso.cerrar("conexion"))
    avisos.suscribir("pedir_ajustes_conexion", lambda: mod_ui_cabecera.abrir_ajustes("Conexión"))
    avisos.suscribir("musica_estado_cambio", mod_ui_musica._refrescar_mini_player)
    avisos.suscribir("pad_terminado", mod_ui_soundboard._apagar_pad_si_token_vigente)
    avisos.suscribir("pad_activo", mod_ui_soundboard._fijar_pad_activo)
