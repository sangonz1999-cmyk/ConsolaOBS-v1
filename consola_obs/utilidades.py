from consola_obs import estado as E
from consola_obs import constantes as C


def medida_actual():
    """Medida del tamaño de ícono elegido (Chico/Mediano/Grande), FIJA
    sin importar el tamaño de la ventana (como el soundboard de Nico:
    pads de tamaño fijo que se reacomodan, nunca se destruyen ni
    re-escalan al redimensionar). Los pads siempre quedan cuadrados. Si
    la ventana es chica, aparecen las barras de desplazamiento."""
    base = C.TAMANOS_ICONO[E.tamano_icono_actual]
    return {
        "diametro_boton": max(24, base["diametro_boton"]),
        "fuente_boton": max(12, base["fuente_boton"]),
        "pad_ancho": max(70, base["pad_ancho"]),
        "pad_alto": max(70, base["pad_alto"]),
        "diametro_pad_chico": max(16, base["diametro_pad_chico"]),
        "fuente_pad_icono": max(12, base["fuente_pad_icono"]),
        "fuente_pad_texto": max(8, base["fuente_pad_texto"]),
        "fuente_ancho": max(86, base["fuente_ancho"]),
        "fuente_alto": max(270, base["fuente_alto"]),
        "fuente_alto_canal": max(72, base["fuente_alto_canal"]),
        "fuente_ancho_vu": max(8, base["fuente_ancho_vu"]),
        "fuente_nombre": max(10, base["fuente_nombre"]),
    }
