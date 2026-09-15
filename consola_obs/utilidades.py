from consola_obs import estado as E
from consola_obs import constantes as C


def factor_escala_ui():
    """Cuánto hay que escalar la interfaz según el tamaño ACTUAL de la
    ventana, comparado con el tamaño de referencia. Si la ventana es más
    chica que la referencia, todo se achica para que entre en pantalla;
    si es más grande, todo crece para aprovechar el espacio. Se limita
    entre ESCALA_MINIMA y ESCALA_MAXIMA para que nunca quede ilegible ni
    absurdamente gigante."""
    try:
        ancho = E.ventana.winfo_width()
        alto = E.ventana.winfo_height()
    except Exception:
        return 1.0

    if ancho <= 1 or alto <= 1:
        return 1.0

    factor = min(ancho / C.ANCHO_VENTANA_REFERENCIA, alto / C.ALTO_VENTANA_REFERENCIA) * C.ESCALA_BASE
    return max(C.ESCALA_MINIMA, min(C.ESCALA_MAXIMA, factor))


def medida_actual():
    """Medida del tamaño de ícono elegido (Chico/Mediano/Grande), ya
    escalada según el tamaño actual de la ventana. Los pads del
    soundboard siempre quedan cuadrados: se escala el mismo valor base
    para ancho y alto, así nunca se desalinean entre sí."""
    base = C.TAMANOS_ICONO[E.tamano_icono_actual]
    f = factor_escala_ui()
    return {
                                                                     
                                                                    
                                                                  
                                                                      
                                                                    
                                                 
        "diametro_boton": max(24, round(base["diametro_boton"] * f)),
        "fuente_boton": max(12, round(base["fuente_boton"] * f)),
        "pad_ancho": max(70, round(base["pad_ancho"] * f)),
        "pad_alto": max(70, round(base["pad_alto"] * f)),
        "diametro_pad_chico": max(16, round(base["diametro_pad_chico"] * f)),
        "fuente_pad_icono": max(12, round(base["fuente_pad_icono"] * f)),
        "fuente_pad_texto": max(8, round(base["fuente_pad_texto"] * f)),
        "fuente_ancho": max(86, round(base["fuente_ancho"] * f)),
        "fuente_alto": max(270, round(base["fuente_alto"] * f)),
        "fuente_alto_canal": max(72, round(base["fuente_alto_canal"] * f)),
        "fuente_ancho_vu": max(8, round(base["fuente_ancho_vu"] * f)),
        "fuente_nombre": max(10, round(base["fuente_nombre"] * f)),
    }
