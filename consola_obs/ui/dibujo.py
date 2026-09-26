import math
import tkinter as tk

from consola_obs.compat import HAY_PILLOW, Image, ImageChops, ImageDraw, ImageFilter, ImageTk
from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import rutas as R


def _ajustar_color(color_hex, cantidad):
    """Aclara (cantidad > 0) u oscurece (cantidad < 0) un color #rrggbb."""
    color_hex = color_hex.lstrip("#")
    r = int(color_hex[0:2], 16)
    g = int(color_hex[2:4], 16)
    b = int(color_hex[4:6], 16)
    r = max(0, min(255, r + cantidad))
    g = max(0, min(255, g + cantidad))
    b = max(0, min(255, b + cantidad))
    return f"#{r:02x}{g:02x}{b:02x}"


def _aclarar_color(color_hex, cantidad=50):
    return _ajustar_color(color_hex, cantidad)


def _oscurecer_color(color_hex, cantidad=50):
    return _ajustar_color(color_hex, -cantidad)


def _oscurecer_color_pct(color_hex, factor=0.4):
    """Oscurece un color #rrggbb multiplicando cada canal por 'factor'
    (0-1), conservando el matiz. A diferencia de _oscurecer_color (que
    resta un valor fijo y termina 'lavando' los colores oscuros hacia
    negro puro), esto sirve para teñir paneles enteros manteniendo el
    tono reconocible."""
    color_hex = color_hex.lstrip("#")
    r = int(int(color_hex[0:2], 16) * factor)
    g = int(int(color_hex[2:4], 16) * factor)
    b = int(int(color_hex[4:6], 16) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def _puntos_rect_redondeado(x0, y0, x1, y1, radio):
    """Devuelve los puntos de un rectángulo de esquinas redondeadas de
    verdad, listos para dibujar con create_polygon(..., smooth=True) (el
    suavizado de Tk hace que las esquinas se vean como curvas reales en
    vez de ángulos rectos)."""
    r = max(0, min(radio, (x1 - x0) / 2, (y1 - y0) / 2))
    return [
        x0 + r, y0,  x1 - r, y0,  x1, y0,  x1, y0 + r,
        x1, y1 - r,  x1, y1,  x1 - r, y1,  x0 + r, y1,
        x0, y1,  x0, y1 - r,  x0, y0 + r,  x0, y0,
    ]


def _mezclar_color(color_a, color_b, t):
    """Interpola linealmente entre dos colores #rrggbb (t=0 -> color_a,
    t=1 -> color_b). Base de los degradados de cabecera/franjas de acento."""
    a = color_a.lstrip("#")
    b = color_b.lstrip("#")
    r = int(int(a[0:2], 16) * (1 - t) + int(b[0:2], 16) * t)
    g = int(int(a[2:4], 16) * (1 - t) + int(b[2:4], 16) * t)
    bch = int(int(a[4:6], 16) * (1 - t) + int(b[4:6], 16) * t)
    return f"#{r:02x}{g:02x}{bch:02x}"


def _gradiente_vertical(canvas, x0, y0, x1, y1, color_arriba, color_abajo, pasos=48):
    """Dibuja un degradado vertical suave (franja por franja) entre dos
    colores, usado para dar profundidad a la cabecera y a los paneles en
    vez de un color plano único."""
    alto = max(1, y1 - y0)
    ids = []
    for i in range(pasos):
        t = i / max(1, pasos - 1)
        ya = y0 + alto * i / pasos
        yb = y0 + alto * (i + 1) / pasos
        color = _mezclar_color(color_arriba, color_abajo, t)
        ids.append(canvas.create_rectangle(x0, ya, x1, yb + 1, fill=color, outline=""))
    return ids


def _gradiente_horizontal(canvas, x0, y0, x1, y1, color_izq, color_der, pasos=60):
    """Ídem, pero de izquierda a derecha (se usa para la franja de acento
    fina debajo de la cabecera y las barras de título de los paneles)."""
    ancho = max(1, x1 - x0)
    ids = []
    for i in range(pasos):
        t = i / max(1, pasos - 1)
        xa = x0 + ancho * i / pasos
        xb = x0 + ancho * (i + 1) / pasos
        color = _mezclar_color(color_izq, color_der, t)
        ids.append(canvas.create_rectangle(xa, y0, xb + 1, y1, fill=color, outline=""))
    return ids


def _gradiente_vertical_redondeado(canvas, x0, y0, x1, y1, radio, color_arriba, color_abajo, pasos=48):
    """Igual que _gradiente_vertical (franja por franja, de arriba
    hacia abajo), pero cada franja se recorta en X según la curva de un
    rectángulo de esquinas redondeadas con el radio indicado. Antes el
    marco se dibujaba con rectángulos rectos de punta a punta, así que
    sus esquinas cuadradas sobresalían por fuera del contorno redondeado
    del pad (el 'fondo que se sale por los bordes'); con esto la franja
    se angosta cerca de cada esquina, igual que lo hace el propio
    contorno curvo, y ya no se nota nada por fuera de él."""
    alto = max(1, y1 - y0)
    ancho = max(1, x1 - x0)
    radio = max(0.0, min(radio, ancho / 2, alto / 2))
    ids = []

    def _inset_en(y):
        if radio <= 0:
            return 0.0
        dist_arriba = (y0 + radio) - y
        dist_abajo = y - (y1 - radio)
        dist = max(dist_arriba, dist_abajo, 0.0)
        if dist <= 0:
            return 0.0
        dist = min(dist, radio)
        return radio - math.sqrt(max(0.0, radio * radio - dist * dist))

    for i in range(pasos):
        t = i / max(1, pasos - 1)
        ya = y0 + alto * i / pasos
        yb = y0 + alto * (i + 1) / pasos
        color = _mezclar_color(color_arriba, color_abajo, t)
        inset = max(_inset_en(ya), _inset_en(yb))
        ids.append(canvas.create_rectangle(
            x0 + inset, ya, x1 - inset, yb + 1, fill=color, outline=""
        ))
    return ids


def _dibujar_icono_ecualizador(canvas, cx, cy, alto, color="#2fd693"):
    """Ícono de marca dibujado a mano (barras tipo ecualizador), usado en
    la cabecera cuando no hay un logo propio en assets/iconos/. Así la
    interfaz tiene un ícono desde el primer momento, sin depender de que
    el usuario agregue un archivo."""
    alturas = [0.55, 1.0, 0.7, 0.85]
    ancho_barra = max(3, alto * 0.14)
    espacio = ancho_barra * 1.6
    x0 = cx - (espacio * (len(alturas) - 1)) / 2
    for i, factor in enumerate(alturas):
        h = alto * factor
        x = x0 + i * espacio
        color_barra = _aclarar_color(color, int(20 * (i % 2)))
        _dibujar_rect_redondeado(
            canvas, x - ancho_barra / 2, cy - h / 2, x + ancho_barra / 2, cy + h / 2,
            radio=ancho_barra * 0.5, fill=color_barra, outline=""
        )


def _dibujar_rect_redondeado(canvas, x0, y0, x1, y1, radio=10, **kwargs):
    """Rectángulo de esquinas redondeadas reales (estética de software de
    audio profesional, en vez del borde 100% recto de antes). Se
    mantiene el nombre y la firma originales para no tener que tocar
    cada lugar donde se usaba."""
    return canvas.create_polygon(_puntos_rect_redondeado(x0, y0, x1, y1, radio), smooth=True, **kwargs)


def _dibujar_bisel_pixel(canvas, x0, y0, x1, y1, color_fondo, grosor=2):
    """Dibuja el relleno de un botón/pad con look de "tecla de consola
    profesional": esquinas redondeadas reales, sombra de profundidad
    detrás, borde definido y un degradado simulado (franja de brillo
    arriba, franja de sombra abajo) en vez del bisel de líneas duras de
    antes. Devuelve el id del relleno y las listas de ids de brillo/
    sombra (para poder recolorear el botón después, ej. al mutear o
    cambiar el modo de escucha), igual que la versión anterior."""
    ancho = max(1, x1 - x0)
    alto = max(1, y1 - y0)
    radio = max(4, min(16, min(ancho, alto) * 0.22))

    canvas.create_polygon(
        _puntos_rect_redondeado(x0 + 3, y0 + 4, x1 + 2, y1 + 4, radio),
        smooth=True, fill=C.COLOR_SOMBRA, outline=""
    )

    id_relleno = canvas.create_polygon(
        _puntos_rect_redondeado(x0, y0, x1, y1, radio),
        smooth=True, fill=color_fondo, outline=_oscurecer_color(color_fondo, 60), width=grosor
    )

    m = grosor + 1
    alto_brillo = max(3, alto * 0.42)
    ids_claro = [
        canvas.create_polygon(
            _puntos_rect_redondeado(x0 + m, y0 + m, x1 - m, y0 + m + alto_brillo, max(2, radio * 0.6)),
            smooth=True, fill=_aclarar_color(color_fondo, 55), outline=""
        )
    ]
    alto_sombra = max(3, alto * 0.24)
    ids_oscuro = [
        canvas.create_polygon(
            _puntos_rect_redondeado(x0 + m, y1 - m - alto_sombra, x1 - m, y1 - m, max(2, radio * 0.6)),
            smooth=True, fill=_oscurecer_color(color_fondo, 35), outline=""
        )
    ]
    return id_relleno, ids_claro, ids_oscuro


def _dibujar_sombra_difusa(canvas, x0, y0, x1, y1, radio=14, capas=5, color_fondo_panel="#131825", tag="sombra_difusa"):
    ids = []
    for i in range(capas):
        t = i / max(1, capas - 1)
        color = _mezclar_color(color_fondo_panel, C.COLOR_SOMBRA, t)
        expansion = (capas - i) * 2
        ids.append(canvas.create_polygon(
            _puntos_rect_redondeado(
                x0 - expansion + 3, y0 - expansion + 4,
                x1 + expansion + 3, y1 + expansion + 4,
                radio + expansion
            ),
            smooth=True, fill=color, outline="", tags=(tag,)
        ))
    return ids


def _dibujar_boton_vidrio(canvas, x0, y0, x1, y1, color_fondo, grosor=3):
    ancho = max(1, x1 - x0)
    alto = max(1, y1 - y0)
    radio = max(6, min(24, min(ancho, alto) * 0.22))
    sombra = max(2, min(5, round(min(ancho, alto) * 0.02)))
    canvas.create_polygon(
        _puntos_rect_redondeado(x0 + sombra, y0 + sombra + 2, x1 + sombra, y1 + sombra + 2, radio),
        smooth=True, fill=C.COLOR_SOMBRA, outline=""
    )
    id_relleno = canvas.create_polygon(
        _puntos_rect_redondeado(x0, y0, x1, y1, radio),
        smooth=True, fill=color_fondo, outline=_oscurecer_color(color_fondo, 55), width=grosor
    )
    inset = max(3, round(min(ancho, alto) * 0.045))
    brillo = _aclarar_color(color_fondo, 24)
    canvas.create_polygon(
        _puntos_rect_redondeado(x0 + inset, y0 + inset, x1 - inset, y0 + alto * 0.22, max(2, radio * 0.55)),
        smooth=True, fill=brillo, outline=""
    )
    return id_relleno, [id_relleno], []


def _mezclar_rgb(color_a, color_b, t):
    ra, rb = _hex_a_rgb(color_a), _hex_a_rgb(color_b)
    return tuple(round(ra[i] + (rb[i] - ra[i]) * t) for i in range(3))


def _mezclar_hex(color_a, color_b, t):
    return "#%02x%02x%02x" % _mezclar_rgb(color_a, color_b, t)


def _desaturar_color(color_hex, cantidad=0.45):
    """Baja la saturación mezclando con gris (para etiquetas en Moderna)."""
    try:
        return _mezclar_hex(color_hex, "#808080", cantidad)
    except Exception:
        return color_hex


def _gris_apagado_de(color_hex):
    """Gris calculado desde la etiqueta (Fase 4): la fuente muteada o
    fuera de escena se pinta con SU MISMO tono desaturado, no con un
    gris fijo. Sin etiqueta (None) se usa el gris fijo de siempre.
    Pura y testeable (no toca Tk). Nunca lanza."""
    try:
        fijo = C.COLOR_GRIS_ATENUADO
    except Exception:
        fijo = "#8e98ad"
    try:
        if not color_hex or not isinstance(color_hex, str):
            return fijo
        _hex_a_rgb(color_hex)
        return _desaturar_color(color_hex, 0.82)
    except Exception:
        return fijo


def _gradiente_imagen(tam, color_arriba, color_abajo):
    """Franja vertical de color continuo (sin escalones), hecha con una
    tira de 1 pixel de ancho que después se estira: es la forma barata
    de tener un degradado real en vez de los 14/48 rectángulos apilados
    que usa el canvas de Tk."""
    ancho, alto = tam
    tira = Image.new("RGB", (1, max(2, alto)))
    px = tira.load()
    for y in range(tira.height):
        px[0, y] = _mezclar_rgb(color_arriba, color_abajo, y / (tira.height - 1))
    return tira.resize((max(1, ancho), max(1, alto)), Image.BILINEAR)


def _mascara_redondeada(tam, caja, radio):
    mascara = Image.new("L", tam, 0)
    ImageDraw.Draw(mascara).rounded_rectangle(caja, radius=max(1, radio), fill=255)
    return mascara


def _imagen_placa(ancho, alto, acento=None, encendido=False, hover=False, presionado=False, color_marco=None,
                   reproduciendo=False):
    """Devuelve la imagen PIL de una placa de vidrio del tamaño pedido.
    - acento: color del pad (etiqueta del usuario o verde si tiene sonido)
    - encendido: el pad tiene un sonido cargado (cara teñida + halo)
    - hover / presionado: estados visuales del mouse.
    - color_marco: si el usuario le puso una etiqueta de color al pad,
      el marco metálico (lo que antes era un cuadrado de color pegado
      POR FUERA de la placa, vía el borde del widget) ahora se tiñe con
      ese color directamente en el propio marco, así queda integrado a
      la placa en vez de verse como un recuadro aparte.
    - reproduciendo: el pad está sonando DE VERDAD en este momento,
      según el estado real que reporta OBS (no una suposición nuestra).
      Se dibuja bien fuerte -marco y halo se tiñen con el color del
      pad a máxima intensidad- para que quede claro que el efecto
      sigue activo aunque ya no se lo llegue a escuchar."""
    ancho = max(24, int(ancho))
    alto = max(24, int(alto))

    color_resplandor = None
    if reproduciendo:
        base_resplandor = acento or color_marco or "#2fd693"
        # Aclarado con blanco: un acento oscuro o poco saturado (que
        # casi no se nota sólo teñido) igual queda bien luminoso.
        color_resplandor = _mezclar_hex(base_resplandor, "#ffffff", 0.3)

    S = C.FACTOR_SUPERSAMPLING_PLACAS
    while S > 1 and max(ancho, alto) * S > C.LADO_MAXIMO_RENDER_PLACA:
        S -= 1

    W, H = ancho * S, alto * S
    lado = min(W, H)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    margen = max(1, round(lado * 0.035))
    # Bordes finos: el marco claro y el foso negro son apenas una
    # línea cada uno, así la cara del pad se come casi todo el cuadro
    # en vez de quedar encerrada en un aro grueso.
    grosor_marco = max(1, round(lado * 0.018))
    grosor_foso = max(1, round(lado * 0.009))
    radio = max(2, round(lado * 0.235))

    caja_ext = [margen, margen, W - 1 - margen, H - 1 - margen]
    caja_foso = [caja_ext[0] + grosor_marco, caja_ext[1] + grosor_marco,
                 caja_ext[2] - grosor_marco, caja_ext[3] - grosor_marco]
    caja_cara = [caja_foso[0] + grosor_foso, caja_foso[1] + grosor_foso,
                 caja_foso[2] - grosor_foso, caja_foso[3] - grosor_foso]
    radio_foso = max(2, radio - grosor_marco)
    radio_cara = max(2, radio_foso - grosor_foso)

    # Sombra proyectada (difusa de verdad, con desenfoque gaussiano).
    sombra = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sombra).rounded_rectangle(
        [caja_ext[0], caja_ext[1] + margen * 0.5, caja_ext[2], caja_ext[3] + margen * 0.9],
        radius=radio, fill=210
    )
    sombra = sombra.filter(ImageFilter.GaussianBlur(margen * 0.85))
    img.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0), sombra)

    if color_resplandor:
        # Resplandor que se escapa por fuera del marco, sobre el
        # margen que separa la placa del fondo oscuro del panel: así
        # el borde se ve realmente "iluminado" contra el fondo, en vez
        # de depender sólo de que el color contraste con el propio
        # marco metálico.
        fuga = Image.new("L", (W, H), 0)
        ImageDraw.Draw(fuga).rounded_rectangle(caja_ext, radius=radio, fill=255)
        fuga = fuga.filter(ImageFilter.GaussianBlur(margen * 2.4))
        img.paste(Image.new("RGBA", (W, H), _hex_a_rgb(color_resplandor) + (255,)), (0, 0),
                  fuga.point(lambda v: int(v * 0.9)))

    # Marco claro con degradado (arriba brilla, abajo se apaga). Si el
    # pad tiene una etiqueta de color, el marco se tiñe con ese color
    # (en vez de quedar siempre gris metálico y depender de un cuadrado
    # de color aparte alrededor de la placa).
    mascara_ext = _mascara_redondeada((W, H), caja_ext, radio)
    color_marco_arriba, color_marco_abajo = C.COLOR_PLACA_MARCO_ARRIBA, C.COLOR_PLACA_MARCO_ABAJO
    if color_marco:
        color_marco_arriba = _mezclar_hex(C.COLOR_PLACA_MARCO_ARRIBA, color_marco, 0.65)
        color_marco_abajo = _mezclar_hex(C.COLOR_PLACA_MARCO_ABAJO, color_marco, 0.65)
    if color_resplandor:
        color_marco_arriba = color_resplandor
        color_marco_abajo = color_resplandor
    marco = _gradiente_imagen((W, H), color_marco_arriba, color_marco_abajo).convert("RGBA")
    img.paste(marco, (0, 0), mascara_ext)

    # Foso negro: la ranura que separa el marco de la cara y da la
    # sensación de que la tecla está encastrada.
    mascara_foso = _mascara_redondeada((W, H), caja_foso, radio_foso)
    img.paste(Image.new("RGBA", (W, H), _hex_a_rgb(C.COLOR_PLACA_FOSO) + (255,)), (0, 0), mascara_foso)

    # Cara del pad.
    color_arriba, color_abajo = C.COLOR_PLACA_CARA_ARRIBA, C.COLOR_PLACA_CARA_ABAJO
    if acento and encendido:
        color_arriba = _mezclar_hex(C.COLOR_PLACA_CARA_ARRIBA, acento, 0.55)
        color_abajo = _mezclar_hex(C.COLOR_PLACA_CARA_ABAJO, acento, 0.35)
    elif acento:
        color_arriba = _mezclar_hex(C.COLOR_PLACA_CARA_ARRIBA, acento, 0.22)
        color_abajo = _mezclar_hex(C.COLOR_PLACA_CARA_ABAJO, acento, 0.14)
    mascara_cara = _mascara_redondeada((W, H), caja_cara, radio_cara)
    cara = _gradiente_imagen((W, H), color_arriba, color_abajo).convert("RGBA")
    img.paste(cara, (0, 0), mascara_cara)

    # Sin reflejo de vidrio: la cara queda lisa (sólo el degradado), así
    # no compite con la miniatura del sonido que va encima ocupando casi
    # toda la cara del pad.

    # Halo interior de color: tenue cuando el pad sólo tiene sonido
    # cargado, y mucho más fuerte -con el color del resplandor- cuando
    # está sonando de verdad en este momento.
    color_halo = None
    intensidad_halo = 0.55
    if color_resplandor:
        color_halo = color_resplandor
        intensidad_halo = 0.9
    elif acento and encendido:
        color_halo = acento

    if color_halo:
        adentro = _mascara_redondeada(
            (W, H),
            [caja_cara[0] + grosor_foso * 1.6, caja_cara[1] + grosor_foso * 1.6,
             caja_cara[2] - grosor_foso * 1.6, caja_cara[3] - grosor_foso * 1.6],
            radio_cara
        )
        halo = ImageChops.subtract(mascara_cara, adentro)
        halo = halo.filter(ImageFilter.GaussianBlur(max(1, grosor_foso * (1.6 if color_resplandor else 1.2))))
        halo = halo.point(lambda v: int(v * intensidad_halo))
        img.paste(Image.new("RGBA", (W, H), _hex_a_rgb(color_halo) + (255,)), (0, 0), halo)

    if hover:
        img.paste(Image.new("RGBA", (W, H), (255, 255, 255, 255)), (0, 0),
                  mascara_ext.point(lambda v: int(v * 0.10)))
    if presionado:
        img.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0),
                  mascara_ext.point(lambda v: int(v * 0.28)))

    if color_resplandor:
        # Trazo nítido justo sobre el borde del marco, encima de todo
        # lo demás: le da al brillo un límite definido y bien marcado,
        # en vez de quedar sólo como un degradado difuso.
        ancho_trazo = max(2, round(grosor_marco * 1.4))
        ImageDraw.Draw(img).rounded_rectangle(
            caja_ext, radius=radio,
            outline=_hex_a_rgb(color_resplandor) + (255,), width=ancho_trazo
        )

    return img.resize((ancho, alto), Image.LANCZOS)


def _placa_tk(ancho, alto, acento=None, encendido=False, hover=False, presionado=False, color_marco=None,
              reproduciendo=False):
    """Versión cacheada y ya convertida a PhotoImage (lista para
    create_image). Si no hay Pillow devuelve None y quien la llama cae
    al dibujo viejo con primitivas de Tk."""
    if not HAY_PILLOW:
        return None
    clave = (int(ancho), int(alto), acento, bool(encendido), bool(hover), bool(presionado), color_marco,
              bool(reproduciendo))
    foto = E._cache_placas.get(clave)
    if foto is not None:
        return foto
    try:
        foto = ImageTk.PhotoImage(
            _imagen_placa(ancho, alto, acento, encendido, hover, presionado, color_marco, reproduciendo)
        )
    except Exception:
        return None
    if len(E._cache_placas) > C.LIMITE_CACHE_PLACAS:
        E._cache_placas.clear()
    E._cache_placas[clave] = foto
    return foto


_cache_placas_modernas = {}


def _placa_moderna_tk(ancho, alto, acento=None, encendido=False, hover=False, presionado=False,
                      color_marco=None, reproduciendo=False):
    """Pad plano estilo OBS (tema Moderna): cuadrado con esquinas apenas
    redondeadas, relleno liso sin degradado y borde fino de acento. Misma
    firma que _placa_tk para intercambiarlas sin tocar quien llama."""
    if not HAY_PILLOW:
        return None
    ancho, alto = max(24, int(ancho)), max(24, int(alto))
    clave = (ancho, alto, acento, bool(encendido), bool(hover), bool(presionado), color_marco,
             bool(reproduciendo))
    foto = _cache_placas_modernas.get(clave)
    if foto is not None:
        return foto
    try:
        S = 4
        W, H = ancho * S, alto * S
        lado = min(W, H)
        radio = max(3 * S, round(lado * 0.07))
        grosor = max(2 * S, round(lado * 0.016))
        if reproduciendo:
            borde = _mezclar_hex(acento or color_marco or "#2f7cf6", "#ffffff", 0.3)
            cuerpo = _mezclar_hex("#2c3646", acento or color_marco or "#2f7cf6", 0.30)
        elif encendido:
            borde = color_marco or acento or "#2f7cf6"
            base = "#2c3646"
            cuerpo = _mezclar_hex(base, acento, 0.22) if acento else base
        else:
            borde = color_marco or "#4d5b78"
            cuerpo = "#232c3b"
        if hover:
            cuerpo = _mezclar_hex(cuerpo, "#ffffff", 0.08)
        if presionado:
            cuerpo = _mezclar_hex(cuerpo, "#000000", 0.25)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([S, S, W - S - 1, H - S - 1], radius=radio,
                            fill=_hex_a_rgb(cuerpo) + (255,),
                            outline=_hex_a_rgb(borde) + (255,), width=grosor)
        foto = ImageTk.PhotoImage(img.resize((ancho, alto), Image.LANCZOS))
    except Exception:
        return None
    if len(_cache_placas_modernas) > C.LIMITE_CACHE_PLACAS:
        _cache_placas_modernas.clear()
    _cache_placas_modernas[clave] = foto
    return foto
# Mismo truco que el '_S' de tu otro programa: Tk dibuja un
# create_oval tal cual, sin suavizar el borde (se nota como
# "escalones" sobre todo en botones chicos). Acá en cambio el círculo
# se dibuja con Pillow a esta cantidad de veces más resolución de la
# que se va a mostrar, y se achica con un filtro de buena calidad
# (LANCZOS): al promediar varios "sub-píxeles" en cada píxel final, el
# borde curvo queda liso. Más alto = más suave y más caro de generar;
# 4 ya se ve bien y sigue siendo instantáneo para un botón de este
# tamaño.


def _hex_a_rgb(color_hex):
    color_hex = color_hex.lstrip("#")
    return tuple(int(color_hex[i:i + 2], 16) for i in (0, 2, 4))


def _renderizar_circulo_boton(lado, color_fondo):
    """Dibuja con Pillow, ya suavizadas, todas las capas del círculo de
    un botón (sombra proyectada, relleno con borde, brillo superior
    tipo vidrio y sombra interior inferior) y devuelve un
    ImageTk.PhotoImage del tamaño final ('lado' x 'lado'), lista para
    poner en el canvas con create_image. El ícono/texto de encima se
    sigue dibujando aparte con create_text -ese ya sale nítido con Tk,
    el problema era sólo el borde curvo del círculo."""
    S = C.FACTOR_SUPERSAMPLING_CIRCULOS
    grande = lado * S
    img = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = grande / 2
    r = (lado - 8) / 2 * S

    draw.ellipse(
        [cx - r + 2 * S, cy - r + 3 * S, cx + r + 2 * S, cy + r + 3 * S],
        fill=_hex_a_rgb(C.COLOR_SOMBRA) + (255,)
    )
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=_hex_a_rgb(color_fondo) + (255,),
        outline=_hex_a_rgb(_oscurecer_color(color_fondo, 70)) + (255,),
        width=max(1, round(2 * S)),
    )
    draw.ellipse(
        [cx - r * 0.55, cy - r * 0.78, cx + r * 0.55, cy - r * 0.05],
        fill=_hex_a_rgb(_aclarar_color(color_fondo, 60)) + (255,)
    )
    # Pillow mide el ángulo del arco al revés que el create_arc de Tk
    # (sentido y punto de arranque distintos); (20, 160) es la
    # conversión que deja este pedazo de sombra en el mismo lugar
    # -pegado abajo del círculo- que el start=200/extent=140 original.
    draw.pieslice(
        [cx - r + 2 * S, cy - r * 0.1, cx + r - 2 * S, cy + r - 2 * S],
        start=20, end=160,
        fill=_hex_a_rgb(_oscurecer_color(color_fondo, 35)) + (255,)
    )

    img = img.resize((lado, lado), Image.LANCZOS)
    return ImageTk.PhotoImage(img)


def _crear_boton_circular(parent, texto, diametro, fuente_tam, color_fondo, comando):
    lado = max(28, diametro + 8)
    canvas = tk.Canvas(parent, width=lado, height=lado, bg=parent["bg"], highlightthickness=0, cursor="hand2")
    cx = cy = lado / 2
    r = (lado - 8) / 2

    if HAY_PILLOW:
        imagen_tk = _renderizar_circulo_boton(lado, color_fondo)
        id_circulo = canvas.create_image(cx, cy, image=imagen_tk)
        canvas.imagen_circulo_actual = imagen_tk  # referencia viva: sin
        # esto Python recolecta la imagen apenas termina la función y
        # el botón se queda en blanco.
        ids_bisel_extra = []
        bisel_claro, bisel_oscuro = [], []
    else:
        # Sin Pillow disponible: se cae al dibujo nativo del canvas de
        # siempre (con los escalones de toda la vida, pero funcionando
        # igual en todo lo demás).
        canvas.create_oval(cx - r + 2, cy - r + 3, cx + r + 2, cy + r + 3, fill=C.COLOR_SOMBRA, outline="")
        id_circulo = canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=color_fondo, outline=_oscurecer_color(color_fondo, 70), width=2
        )
        id_gloss = canvas.create_oval(
            cx - r * 0.55, cy - r * 0.78, cx + r * 0.55, cy - r * 0.05,
            fill=_aclarar_color(color_fondo, 60), outline=""
        )
        id_sombra_int = canvas.create_arc(
            cx - r + 2, cy - r * 0.1, cx + r - 2, cy + r - 2,
            start=200, extent=140, fill=_oscurecer_color(color_fondo, 35), outline="", style="chord"
        )
        ids_bisel_extra = [id_gloss, id_sombra_int]
        bisel_claro, bisel_oscuro = [id_gloss], [id_sombra_int]

    # Íconos de mute (altavoz) y monitoreo (auriculares) como emoji de
    # texto, igual que en la versión original de la consola: más simple
    # y liviano que dibujarlos a mano vector por vector.
    tipo_icono = "texto"
    texto_id = canvas.create_text(
        cx, cy, text=texto,
        font=(E.FUENTE_ICONOS, max(9, min(fuente_tam, int(r * 0.80))), "bold"),
        fill="white"
    )
    ids_icono = [texto_id]

    def _click(_event):
        comando()

    for item in (id_circulo, *ids_bisel_extra, *ids_icono):
        canvas.tag_bind(item, "<Button-1>", _click)

    canvas.datos_boton = {
        "circulo": id_circulo,
        "texto": texto_id,
        "iconos": ids_icono,
        "tipo_icono": tipo_icono,
        "comando": comando,
        "usa_pillow": HAY_PILLOW,
        "lado": lado,
        "bisel_claro": bisel_claro,
        "bisel_oscuro": bisel_oscuro,
        "ranuras": [],
    }
    return canvas


_cache_circulo_blanco = {}


def _imagen_circulo_blanco(radio):
    """Perilla blanca con bordes suaves (supersampling + LANCZOS),
    cacheada por radio. None sin Pillow (se usa óvalo de respaldo)."""
    if not HAY_PILLOW:
        return None
    radio = max(4, int(radio))
    if radio in _cache_circulo_blanco:
        return _cache_circulo_blanco[radio]
    try:
        S = 4
        lado = radio * 2 * S
        img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([S, S, lado - S - 1, lado - S - 1],
                  fill=(242, 245, 250, 255), outline=(154, 164, 178, 255), width=S)
        foto = ImageTk.PhotoImage(img.resize((radio * 2, radio * 2), Image.LANCZOS))
        _cache_circulo_blanco[radio] = foto
        return foto
    except Exception:
        return None


_cache_pildora_blanca = {}


def _imagen_pildora_blanca(ancho, alto):
    """Perilla pastilla (círculo alargado) estilo OBS, con bordes suaves
    (supersampling + LANCZOS), cacheada por medida. None sin Pillow (se
    usa óvalo de respaldo)."""
    if not HAY_PILLOW:
        return None
    ancho = max(6, int(ancho))
    alto = max(ancho, int(alto))
    clave = (ancho, alto)
    if clave in _cache_pildora_blanca:
        return _cache_pildora_blanca[clave]
    try:
        S = 4
        w, h = ancho * S, alto * S
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            [S, S, w - S - 1, h - S - 1], radius=(w - 2 * S) // 2,
            fill=(242, 245, 250, 255), outline=(154, 164, 178, 255), width=S)
        foto = ImageTk.PhotoImage(img.resize((ancho, alto), Image.LANCZOS))
        _cache_pildora_blanca[clave] = foto
        return foto
    except Exception:
        return None


_cache_pista_fader = {}


def _imagen_pista_fader(alto, color_pista="#0a0a0a", color_punta="#4365cb"):
    """Pista del fader con extremos redondos y punta inferior azul, todo
    en una sola imagen con bordes suaves (supersampling + LANCZOS): los
    óvalos de 4px dibujados directo en canvas salen deformes porque Tk
    no suaviza nada. La imagen cubre el tramo de la pista (8px de ancho
    con la barra de 4px al centro); el relleno azul del nivel se dibuja
    aparte encima hasta donde empieza la punta. Cacheada por alto. None
    sin Pillow (se cae al dibujo de canvas)."""
    if not HAY_PILLOW:
        return None
    alto = max(12, int(alto))
    clave = (alto, color_pista, color_punta)
    if clave in _cache_pista_fader:
        return _cache_pista_fader[clave]
    try:
        S = 4
        ancho = 8
        w, h = ancho * S, alto * S
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            [2 * S, 0, w - 2 * S - 1, h - 1], radius=2 * S,
            fill=_hex_a_rgb(color_pista) + (255,))
        d.ellipse(
            [2 * S, h - 4 * S - 1, w - 2 * S - 1, h - 1],
            fill=_hex_a_rgb(color_punta) + (255,))
        foto = ImageTk.PhotoImage(img.resize((ancho, alto), Image.LANCZOS))
        _cache_pista_fader[clave] = foto
        return foto
    except Exception:
        return None


def _color_mute(muted):
    """Color del altavoz: rojo si muteado, o gris (más claro en Moderna)."""
    if muted:
        return "#ff5567"
    return C.MOD_ICONO_APAGADO if E.es_moderna() else "#394151"


def _cuadrado_monitor(tipo):
    """(fondo, borde) del cuadrado de monitoreo en Moderna; (None, None)
    apagado (sin cuadrado). En Profesional no se usa (el botón circular
    toma el color directo de COLORES_MONITOREO)."""
    if tipo == "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT":
        return ("#1e8528", "#59d966")
    if tipo == "OBS_MONITORING_TYPE_MONITOR_ONLY":
        return ("#4dabf7", "#8fc8ff")
    return (None, None)


_cache_emoji = {}


def _rutas_fuentes_emoji():
    import os as _os
    if _os.name == "nt":
        base = _os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts"
        return [base + "\\" + f for f in ("seguisym.ttf", "segoeui.ttf", "arial.ttf")]
    return ["DejaVuSans.ttf"]


def _imagen_emoji(texto, tam_px, color, fuentes=None):
    """El mismo emoji de siempre, pero rasterizado en grande con Pillow
    y reducido con LANCZOS: mismo diseño, bordes suaves, teñido con el
    color de estado. Cacheado. None sin Pillow (texto de respaldo).
    Con 'fuentes' se puede forzar el orden de búsqueda (el auricular
    de Moderna usa Segoe UI Emoji primero, de trazo más parecido al
    de OBS)."""
    if not HAY_PILLOW:
        return None
    tam_px = max(12, int(tam_px))
    color = {"white": "#ffffff", "black": "#000000"}.get(color, color)
    clave = (texto, tam_px, color, tuple(fuentes) if fuentes else None)
    if clave in _cache_emoji:
        return _cache_emoji[clave]
    try:
        from PIL import ImageFont
        S = 4
        fuente = None
        for ruta in (fuentes or _rutas_fuentes_emoji()):
            try:
                candidata = ImageFont.truetype(ruta, tam_px * S)
                if candidata.getmask(texto).getbbox():
                    fuente = candidata
                    break
            except Exception:
                continue
        if fuente is None:
            return None
        # Se dibuja en la caja del em y se recorta por lo que SALIÓ
        # (no por la caja de la máscara, que en estas fuentes queda
        # más chica y cortaba el glifo por abajo).
        em = tam_px * S
        img = Image.new("RGBA", (em, em), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((0, 0), texto, font=fuente, anchor="lt",
                                 fill=_hex_a_rgb(color) + (255,))
        bb = img.getbbox()
        if not bb:
            return None
        pad = max(2, tam_px * S // 16)
        img = img.crop((max(0, bb[0] - pad), max(0, bb[1] - pad),
                        min(em, bb[2] + pad), min(em, bb[3] + pad)))
        w, h = img.size
        lado = max(w, h)
        lienzo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        lienzo.paste(img, ((lado - w) // 2, (lado - h) // 2), img)
        foto = ImageTk.PhotoImage(lienzo.resize((tam_px, tam_px), Image.LANCZOS))
    except Exception:
        return None
    if len(_cache_emoji) > 200:
        _cache_emoji.clear()
    _cache_emoji[clave] = foto
    return foto


def _repintar_icono_plano(etiqueta):
    foto = None
    if getattr(etiqueta, "tiene_cuadrado", False):
        foto = _imagen_monitor_svg(etiqueta.tam_icono, etiqueta.cuadrado_color)
    else:
        nombre = _SVG_POR_TEXTO.get(etiqueta.texto_icono)
        if nombre is not None:
            foto = _imagen_svg(nombre, etiqueta.tam_icono)
    if foto is None:
        foto = _imagen_emoji(etiqueta.texto_icono, etiqueta.tam_icono, etiqueta.color_icono,
                             fuentes=getattr(etiqueta, "fuentes_emoji", None))
    if foto is not None:
        etiqueta.imagen_icono = foto
        etiqueta.config(image=foto)
    else:
        etiqueta.config(image="", text=etiqueta.texto_icono)
        try:
            etiqueta.config(fg=("#b5b5b5" if getattr(
                etiqueta, "tiene_cuadrado", False) else etiqueta.color_icono))
        except Exception:
            pass


_RUTAS_EMOJI_ALTAVOZ = None


def _rutas_emoji_altavoz():
    """Segoe UI Emoji primero para el parlante (el muteado trae una X
    en vez del círculo de prohibido); respaldo detrás."""
    global _RUTAS_EMOJI_ALTAVOZ
    if _RUTAS_EMOJI_ALTAVOZ is None:
        import os as _os
        if _os.name == "nt":
            base = _os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts"
            _RUTAS_EMOJI_ALTAVOZ = [base + "\\" + f for f in (
                "seguiemj.ttf", "seguisym.ttf", "segoeui.ttf", "arial.ttf")]
        else:
            _RUTAS_EMOJI_ALTAVOZ = ["DejaVuSans.ttf"]
    return _RUTAS_EMOJI_ALTAVOZ


_cache_svg = {}

# SVG originales (sin modificar) para los iconos planos de Moderna.
_SVG_POR_TEXTO = {"🔊": "mixer-audio.svg", "🔇": "mixer-mute.svg", "🎧": "mixer-headphones.svg"}


def _imagen_svg(nombre_archivo, lado):
    """Renderiza un SVG original con pymupdf a 256px y lo baja a `lado`
    con LANCZOS (fondo transparente, centrado sin recortar). Cacheado.
    None si falta pymupdf/Pillow o el archivo (se cae al emoji)."""
    if not HAY_PILLOW:
        return None
    try:
        import pymupdf
    except Exception:
        return None
    lado = max(8, int(lado))
    clave = (nombre_archivo, lado)
    if clave in _cache_svg:
        return _cache_svg[clave]
    try:
        import os as _os
        ruta = _os.path.join(R.CARPETA_ICONOS, nombre_archivo)
        if not _os.path.isfile(ruta):
            print(f"No se encontró el icono SVG: {ruta}")
            return None
        doc = pymupdf.open(ruta)
        page = doc[0]
        zoom = 256 / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
        img = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
        try:
            doc.close()
        except Exception:
            pass
        lienzo = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        lienzo.alpha_composite(img, ((256 - img.width) // 2, (256 - img.height) // 2))
        foto = ImageTk.PhotoImage(lienzo.resize((lado, lado), Image.LANCZOS))
        _cache_svg[clave] = foto
        return foto
    except Exception:
        return None


def _imagen_svg_menu(nombre_archivo, lado):
    """Icono de menú clic-derecho: igual que _imagen_svg pero normaliza
    el tamaño VISUAL recortando el aire del viewBox.

    Por qué: los SVG nuevos no comparten viewBox (renombrar y
    propiedades usan 40x40 con el dibujo ocupando solo una parte,
    el resto 24x24 casi a sangre). Renderizados a la misma escala,
    el lápiz y el engranaje se veían más chicos que la estrella o
    el filtro. Recortando por el bbox del contenido (con un poco de
    aire) y encajando en un cuadrado, todos quedan del mismo tamaño
    visual sin importar el viewBox original. Cacheado."""
    if not HAY_PILLOW:
        return None
    lado = max(8, int(lado))
    clave = ("menu", nombre_archivo, lado)
    if clave in _cache_svg:
        return _cache_svg[clave]
    try:
        import pymupdf
    except Exception:
        return None
    try:
        import os as _os
        ruta = _os.path.join(R.CARPETA_ICONOS, nombre_archivo)
        if not _os.path.isfile(ruta):
            print(f"No se encontró el icono SVG: {ruta}")
            return None
        doc = pymupdf.open(ruta)
        page = doc[0]
        zoom = 256 / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
        img = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
        try:
            doc.close()
        except Exception:
            pass
        # Recorte por contenido: el bbox de lo no-transparente.
        try:
            caja = img.getbbox()
        except Exception:
            caja = None
        if caja:
            aire = max(4, int(256 * 0.04))
            x0 = max(0, caja[0] - aire)
            y0 = max(0, caja[1] - aire)
            x1 = min(img.width, caja[2] + aire)
            y1 = min(img.height, caja[3] + aire)
            if x1 > x0 and y1 > y0:
                img = img.crop((x0, y0, x1, y1))
        # Encuadre cuadrado: el lado mayor manda, centrado.
        costado = max(img.width, img.height) or 1
        lienzo = Image.new("RGBA", (costado, costado), (0, 0, 0, 0))
        lienzo.alpha_composite(img, ((costado - img.width) // 2, (costado - img.height) // 2))
        foto = ImageTk.PhotoImage(lienzo.resize((lado, lado), Image.LANCZOS))
        _cache_svg[clave] = foto
        return foto
    except Exception:
        return None


def _imagen_monitor_svg(tam_px, color_cuadrado):
    """Auricular SVG original sobre su cuadrado de estado (azul/verde);
    apagado usa mixer-headphones-off.svg tal cual (ya trae su X y su diadema
    atenuada). El label mide SIEMPRE lo mismo (lado = tam + 8) con el
    glifo centrado: el fondo aparece detrás sin mover al resto.
    Cacheado. None si no se pudo (cae al emoji)."""
    fondo = borde = None
    if color_cuadrado:
        fondo, borde = color_cuadrado
    tam_px = max(12, int(tam_px))
    lado = tam_px + 8
    tam_glifo = max(8, tam_px - 2)
    clave = ("monitor", tam_px, fondo, borde)
    if clave in _cache_svg:
        return _cache_svg[clave]
    try:
        from PIL import ImageDraw as _Draw, ImageTk as _ImageTk
        if fondo is None:
            foto_glifo = _imagen_svg("mixer-headphones-off.svg", tam_glifo)
            if foto_glifo is None:
                return None
            base = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
            base.alpha_composite(
                _ImageTk.getimage(foto_glifo),
                ((lado - tam_glifo) // 2, (lado - tam_glifo) // 2))
            foto = _ImageTk.PhotoImage(base)
            _cache_svg[clave] = foto
            return foto
        S = 4
        base = Image.new("RGBA", (lado * S, lado * S), (0, 0, 0, 0))
        dw = _Draw.Draw(base)
        dw.rounded_rectangle(
            [S, S, lado * S - S - 1, lado * S - S - 1], radius=6 * S,
            fill=_hex_a_rgb(borde or fondo) + (255,))
        dw.rounded_rectangle(
            [3 * S, 3 * S, lado * S - 3 * S - 1, lado * S - 3 * S - 1], radius=4 * S,
            fill=_hex_a_rgb(fondo) + (255,))
        base = base.resize((lado, lado), Image.LANCZOS)
        foto_glifo = _imagen_svg("mixer-headphones.svg", tam_glifo)
        if foto_glifo is None:
            return None
        base.alpha_composite(
            _ImageTk.getimage(foto_glifo),
            ((lado - tam_glifo) // 2, (lado - tam_glifo) // 2))
        foto = _ImageTk.PhotoImage(base)
        _cache_svg[clave] = foto
        return foto
    except Exception:
        return None


def _crear_icono_plano(parent, texto, fuente_tam, color, comando, cuadrado=False):
    """Ícono solo (sin círculo detrás) para el tema Moderna: una etiqueta
    clickeable cuyo color marca el estado. Usa los SVG originales
    (audio/mute/headphones vía pymupdf) o cae al emoji sin ellos.
    Compatible con _actualizar_boton_circular (texto/color).
    Con cuadrado=True (auricular) el cuadrado de detrás marca el estado
    y apagado usa mixer-headphones-off.svg tal cual."""
    etiqueta = tk.Label(parent, bg=parent["bg"], cursor="hand2")
    etiqueta.es_plano = True
    etiqueta.texto_icono = texto
    etiqueta.tam_icono = max(12, int(fuente_tam + 2))
    etiqueta.tiene_cuadrado = bool(cuadrado)
    # El parlante se rasteriza desde Segoe UI Emoji (mute con X).
    etiqueta.fuentes_emoji = _rutas_emoji_altavoz() if texto in ("🔇", "🔊") else None
    if cuadrado:
        etiqueta.color_icono = color
        etiqueta.cuadrado_color = color
    else:
        etiqueta.color_icono = color
        etiqueta.cuadrado_color = None
    etiqueta.bind("<Button-1>", lambda _e: comando())
    _repintar_icono_plano(etiqueta)
    if not HAY_PILLOW:
        etiqueta.config(font=(E.FUENTE_EMOJI, fuente_tam))
    return etiqueta


def _actualizar_boton_circular(canvas, texto_nuevo=None, color_nuevo=None):
    if getattr(canvas, "es_plano", False):
        if texto_nuevo in ("🔇", "🔊", "🎧"):
            canvas.texto_icono = texto_nuevo
        if color_nuevo is not None:
            if getattr(canvas, "tiene_cuadrado", False):
                canvas.cuadrado_color = color_nuevo
            else:
                canvas.color_icono = color_nuevo
        _repintar_icono_plano(canvas)
        return
    datos = canvas.datos_boton
    if texto_nuevo is not None and datos.get("texto") is not None:
        canvas.itemconfig(datos["texto"], text=texto_nuevo)
    if color_nuevo is not None:
        # Por las dudas: si llega una tupla (fondo, borde) del modo
        # cuadrado, se usa el fondo (gris apagado si es None).
        _relleno = color_nuevo[0] if isinstance(color_nuevo, tuple) else color_nuevo
        if _relleno is None:
            _relleno = "#394151"
        if datos.get("usa_pillow"):
            imagen_tk = _renderizar_circulo_boton(datos["lado"], _relleno)
            canvas.itemconfig(datos["circulo"], image=imagen_tk)
            canvas.imagen_circulo_actual = imagen_tk
        else:
            canvas.itemconfig(datos["circulo"], fill=_relleno)
            claro = _aclarar_color(_relleno)
            oscuro = _oscurecer_color(_relleno)
            for iid in datos["bisel_claro"]:
                canvas.itemconfig(iid, fill=claro)
            for iid in datos["bisel_oscuro"]:
                canvas.itemconfig(iid, fill=oscuro)
        # Las almohadillas de los auriculares tienen una "ranura" pintada
        # del color de fondo del botón (para simular el corte del ícono
        # de referencia); si el color de fondo cambia (ej. al cambiar el
        # modo de escucha), hay que actualizar también esa ranura o
        # queda con el color viejo pegado encima.
        for iid in datos.get("ranuras", []):
            canvas.itemconfig(iid, fill=_relleno)
