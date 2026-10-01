"""
PREDICTOR DE LA LIGA ESPAÑOLA 2026-27  (v2 - datos precargados)
===============================================================
Ya NO tienes que escribir datos: los 20 equipos de la temporada 2026-27 vienen
cargados con sus estadisticas REALES de la temporada pasada (2025-26).

Solo eliges un equipo y el programa:
  - muestra su ficha completa y todos sus promedios,
  - lo compara contra los otros 19 (local y visitante),
  - compara dos equipos cara a cara,
  - simula la temporada completa para predecir campeon, Champions y descenso.

El modelo tiene en cuenta que los GRANDES equipos tienen mas probabilidad de ganar:
cada club tiene una "jerarquia" (1-10, segun plantilla, presupuesto e historia) que
mejora su ataque y su defensa. Puedes cambiar el peso con PESO_JERARQUIA (0 = sin efecto).

Uso:  python prediccion_laliga_v2.py
"""

import math
import random

# ----------------------------------------------------------------------------
# PARAMETROS DEL MODELO (puedes modificarlos)
# ----------------------------------------------------------------------------
VENTAJA_LOCAL = 1.15       # el local marca ~15% mas
DESVENTAJA_VISITA = 0.90   # el visitante marca ~10% menos
PESO_JERARQUIA = 0.12      # +-12% en ataque/defensa para el club mas grande/pequeño (0 = desactivar)
REGRESION = 0.25           # 25% de "enfriamiento": una sola temporada tiene suerte/azar
FACTOR_SEGUNDA = 0.85      # los ascendidos vienen de Segunda: sus numeros se rebajan un 15%
MAX_GOLES = 8
N_SIM = 2000               # temporadas simuladas

# ----------------------------------------------------------------------------
# DATOS: temporada 2025-26 (tabla final de LaLiga; ascendidos con datos de Segunda)
# Formato: PJ, G, E, P, GF, GC, PTS, JERARQUIA (1-10), DIVISION (1=Primera, 2=Segunda)
# La jerarquia es una estimacion propia (plantilla, presupuesto, historia, Europa).
# ----------------------------------------------------------------------------
DATOS_CRUDOS = {
    "FC Barcelona":       (38, 31,  1,  6, 95, 36, 94, 10.0, 1),
    "Real Madrid":        (38, 27,  5,  6, 77, 35, 86, 10.0, 1),
    "Villarreal":         (38, 22,  6, 10, 72, 46, 72,  6.5, 1),
    "Atlético de Madrid": (38, 21,  6, 11, 62, 44, 69,  8.5, 1),
    "Real Betis":         (38, 15, 15,  8, 59, 48, 60,  7.0, 1),
    "Celta de Vigo":      (38, 14, 12, 12, 53, 48, 54,  5.5, 1),
    "Getafe":             (38, 15,  6, 17, 32, 38, 51,  4.5, 1),
    "Rayo Vallecano":     (38, 12, 14, 12, 41, 44, 50,  4.5, 1),
    "Valencia":           (38, 13, 10, 15, 46, 55, 49,  6.5, 1),
    "Real Sociedad":      (38, 11, 13, 14, 59, 61, 46,  6.5, 1),
    "Espanyol":           (38, 12, 10, 16, 43, 55, 46,  4.5, 1),
    "Athletic Club":      (38, 13,  6, 19, 43, 58, 45,  6.5, 1),
    "Sevilla":            (38, 12,  7, 19, 46, 60, 43,  7.0, 1),
    "Alavés":             (38, 11, 10, 17, 44, 56, 43,  4.0, 1),
    "Elche":              (38, 10, 13, 15, 49, 57, 43,  4.0, 1),
    "Levante":            (38, 11,  9, 18, 47, 61, 42,  4.0, 1),
    "Osasuna":            (38, 11,  9, 18, 44, 50, 42,  4.5, 1),
    # Ascendidos (datos de Segunda Division 2025-26, 42 partidos)
    "Racing de Santander": (42, 25,  7, 10, 90, 61, 82, 4.0, 2),
    "Deportivo La Coruña": (42, 22, 11,  9, 65, 44, 77, 4.5, 2),
    "Málaga":              (42, 21, 10, 11, 75, 52, 73, 4.5, 2),
}

datos = {}
for _n, (_pj, _g, _e, _p, _gf, _gc, _pts, _jer, _div) in DATOS_CRUDOS.items():
    assert _g + _e + _p == _pj and 3 * _g + _e == _pts, f"Datos inconsistentes: {_n}"
    datos[_n] = dict(pj=_pj, g=_g, e=_e, p=_p, gf=_gf, gc=_gc, pts=_pts, jer=_jer, div=_div)

# Caches que se recalculan cuando cambian los datos
FUERZA = {}      # equipo -> (ataque, debilidad_defensiva)
MEDIA = 0.0      # goles promedio por equipo y partido (ajustado)
PROB = {}        # (local, visita) -> dict con probabilidades
POTENCIA = {}    # equipo -> puntos esperados en una temporada de 38 partidos


# ----------------------------------------------------------------------------
# UTILIDADES DE ENTRADA
# ----------------------------------------------------------------------------
def pedir_entero(mensaje, minimo, maximo):
    while True:
        try:
            v = int(input(mensaje).strip())
            if minimo <= v <= maximo:
                return v
        except ValueError:
            pass
        print(f"  ⚠ Escribe un numero entero entre {minimo} y {maximo}.")


def pedir_decimal(mensaje, minimo, maximo):
    while True:
        try:
            v = float(input(mensaje).strip().replace(",", "."))
            if minimo <= v <= maximo:
                return v
        except ValueError:
            pass
        print(f"  ⚠ Escribe un numero entre {minimo} y {maximo}.")


def elegir_equipo(titulo="Selecciona un equipo", excluir=None):
    orden = sorted(datos, key=lambda e: (-datos[e]["pts"] / datos[e]["pj"]))
    lista = [e for e in orden if e != excluir]
    print(f"\n{titulo}:")
    for i, e in enumerate(lista, 1):
        marca = " (ascendido)" if datos[e]["div"] == 2 else ""
        print(f"  {i:2d}. {e}{marca}")
    return lista[pedir_entero("Numero: ", 1, len(lista)) - 1]


# ----------------------------------------------------------------------------
# ESTADISTICAS Y PROMEDIOS
# ----------------------------------------------------------------------------
def promedios(eq):
    d = datos[eq]
    pj = d["pj"]
    return {
        "ppp": d["pts"] / pj,
        "gf_pp": d["gf"] / pj,
        "gc_pp": d["gc"] / pj,
        "dg": d["gf"] - d["gc"],
        "dg_pp": (d["gf"] - d["gc"]) / pj,
        "pct_g": 100 * d["g"] / pj,
        "pct_e": 100 * d["e"] / pj,
        "pct_p": 100 * d["p"] / pj,
        "pct_pts": 100 * d["pts"] / (3 * pj),
        "goles_partido": (d["gf"] + d["gc"]) / pj,
        "pts_38": d["pts"] / pj * 38,  # puntos proyectados a 38 partidos
    }


def ranking(eq, clave, mayor_mejor=True):
    orden = sorted(datos, key=lambda e: clave(e), reverse=mayor_mejor)
    return orden.index(eq) + 1


def mostrar_ficha(eq):
    d, a = datos[eq], promedios(eq)
    n = len(datos)
    ascendido = d["div"] == 2
    print(f"\n{'=' * 62}\n  {eq.upper()}   (temporada 2025-26"
          f"{' - SEGUNDA DIVISION' if ascendido else ''})\n{'=' * 62}")
    print(f"  Partidos: {d['pj']}   Ganados: {d['g']}   Empatados: {d['e']}   Perdidos: {d['p']}")
    print(f"  Puntos: {d['pts']}   GF: {d['gf']}   GC: {d['gc']}   DG: {a['dg']:+d}")
    print("\n  --- PROMEDIOS ---")
    print(f"  Puntos por partido ............ {a['ppp']:.2f}   (promedio liga: {media_liga('ppp'):.2f})")
    print(f"  Goles a favor por partido ..... {a['gf_pp']:.2f}   (promedio liga: {media_liga('gf_pp'):.2f})")
    print(f"  Goles en contra por partido ... {a['gc_pp']:.2f}   (promedio liga: {media_liga('gc_pp'):.2f})")
    print(f"  Diferencia de gol / partido ... {a['dg_pp']:+.2f}")
    print(f"  Goles totales por partido ..... {a['goles_partido']:.2f}")
    print(f"  % victorias / empates / derrotas: {a['pct_g']:.1f}% / {a['pct_e']:.1f}% / {a['pct_p']:.1f}%")
    print(f"  % de puntos conseguidos ....... {a['pct_pts']:.1f}%")
    print(f"  Puntos proyectados a 38 partidos {a['pts_38']:.1f}")
    print("\n  --- POSICION ENTRE LOS 20 EQUIPOS ---")
    print(f"  Puntos por partido: {ranking(eq, lambda e: promedios(e)['ppp'])}º   "
          f"Ataque: {ranking(eq, lambda e: promedios(e)['gf_pp'])}º   "
          f"Defensa: {ranking(eq, lambda e: promedios(e)['gc_pp'], False)}º   "
          f"Dif. gol: {ranking(eq, lambda e: promedios(e)['dg_pp'])}º")
    att, dfn = FUERZA[eq]
    print("\n  --- VALORES DEL MODELO ---")
    print(f"  Jerarquia del club (1-10) ..... {d['jer']:.1f}")
    print(f"  Fuerza de ataque (1.00=media) . {att:.2f}")
    print(f"  Goles que concede vs media .... {dfn:.2f}  (menos de 1.00 = defensa mejor que la media)")
    print(f"  Puntos esperados 2026-27 ...... {POTENCIA[eq]:.1f}   "
          f"(puesto esperado: {ranking(eq, lambda e: POTENCIA[e])}º)")
    if ascendido:
        print(f"  ℹ Sus numeros vienen de Segunda: el modelo los rebaja un "
              f"{round((1 - FACTOR_SEGUNDA) * 100)}%.")


def media_liga(clave):
    return sum(promedios(e)[clave] for e in datos) / len(datos)


def mostrar_resumen_liga():
    print(f"\n{'=' * 84}\n  PROMEDIOS DE LA LIGA (temporada 2025-26)\n{'=' * 84}")
    print(f"  Promedio de puntos por partido: {media_liga('ppp'):.2f} | "
          f"goles por equipo y partido: {media_liga('gf_pp'):.2f}")
    orden = sorted(datos, key=lambda e: (datos[e]["pts"] / datos[e]["pj"], datos[e]["gf"] - datos[e]["gc"]),
                   reverse=True)
    print(f"\n  {'#':>2} {'Equipo':<21}{'PJ':>3}{'PTS':>5}{'GF':>5}{'GC':>5}{'DG':>5}"
          f"{'PPP':>6}{'GF/p':>6}{'GC/p':>6}{'%Vic':>6}{'Jerar.':>7}")
    for i, e in enumerate(orden, 1):
        d, a = datos[e], promedios(e)
        print(f"  {i:>2} {e:<21}{d['pj']:>3}{d['pts']:>5}{d['gf']:>5}{d['gc']:>5}{a['dg']:>+5}"
              f"{a['ppp']:>6.2f}{a['gf_pp']:>6.2f}{a['gc_pp']:>6.2f}{a['pct_g']:>5.0f}%{d['jer']:>7.1f}")
    print("\n  (Racing, Deportivo y Málaga: datos de Segunda División, 42 partidos)")
    mejor_a = max(datos, key=lambda e: promedios(e)["gf_pp"])
    mejor_d = min(datos, key=lambda e: promedios(e)["gc_pp"])
    print(f"  Mejor ataque:  {mejor_a} ({promedios(mejor_a)['gf_pp']:.2f} goles/partido)")
    print(f"  Mejor defensa: {mejor_d} ({promedios(mejor_d)['gc_pp']:.2f} goles recibidos/partido)")


# ----------------------------------------------------------------------------
# MODELO DE PREDICCION
# ----------------------------------------------------------------------------
def poisson(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def recalcular():
    """Calcula la fuerza de cada equipo, las probabilidades de los 380 partidos y la potencia."""
    global MEDIA
    # 1) Goles ajustados por division (los ascendidos se rebajan)
    aj = {}
    for e, d in datos.items():
        f = FACTOR_SEGUNDA if d["div"] == 2 else 1.0
        aj[e] = (d["gf"] / d["pj"] * f, d["gc"] / d["pj"] / f)
    MEDIA = (sum(g for g, _ in aj.values()) + sum(c for _, c in aj.values())) / (2 * len(aj))

    # 2) Ataque / defensa relativos + enfriamiento + jerarquia del club
    for e, d in datos.items():
        att = aj[e][0] / MEDIA
        dfn = aj[e][1] / MEDIA
        att = 1 + (att - 1) * (1 - REGRESION)
        dfn = 1 + (dfn - 1) * (1 - REGRESION)
        k = (d["jer"] - 5.5) / 4.5              # -1 (club pequeño) ... +1 (club grande)
        att *= 1 + PESO_JERARQUIA * k
        dfn *= 1 - PESO_JERARQUIA * k
        FUERZA[e] = (att, dfn)

    # 3) Probabilidades de todos los partidos posibles
    PROB.clear()
    for loc in datos:
        for vis in datos:
            if loc != vis:
                PROB[(loc, vis)] = calcular_partido(loc, vis)

    # 4) Potencia: puntos esperados jugando contra los demas (ida y vuelta)
    for e in datos:
        pts = 0.0
        for r in datos:
            if r == e:
                continue
            p1, p2 = PROB[(e, r)], PROB[(r, e)]
            pts += 3 * p1["local"] + p1["empate"] + 3 * p2["visita"] + p2["empate"]
        POTENCIA[e] = pts * 38 / (2 * (len(datos) - 1))


def calcular_partido(loc, vis):
    att_l, dfn_l = FUERZA[loc]
    att_v, dfn_v = FUERZA[vis]
    lam_l = max(MEDIA * att_l * dfn_v * VENTAJA_LOCAL, 0.05)
    lam_v = max(MEDIA * att_v * dfn_l * DESVENTAJA_VISITA, 0.05)
    pl = pe = pv = 0.0
    mejor, mejor_p = (0, 0), 0.0
    for i in range(MAX_GOLES + 1):
        for j in range(MAX_GOLES + 1):
            p = poisson(i, lam_l) * poisson(j, lam_v)
            if i > j:
                pl += p
            elif i == j:
                pe += p
            else:
                pv += p
            if p > mejor_p:
                mejor, mejor_p = (i, j), p
    t = pl + pe + pv
    return {"lam_l": lam_l, "lam_v": lam_v, "local": pl / t, "empate": pe / t,
            "visita": pv / t, "marcador": mejor, "p_marcador": mejor_p / t}


def pronostico(r, local, visita):
    m = max(("local", r["local"]), ("empate", r["empate"]), ("visita", r["visita"]), key=lambda x: x[1])[0]
    return {"local": f"Gana {local}", "visita": f"Gana {visita}", "empate": "Empate"}[m]


# ----------------------------------------------------------------------------
# OPCION: COMPARAR UN EQUIPO CONTRA LOS OTROS 19
# ----------------------------------------------------------------------------
def comparar_con_todos():
    eq = elegir_equipo("¿Que equipo quieres analizar?")
    mostrar_ficha(eq)

    rivales = sorted([r for r in datos if r != eq], key=lambda r: -POTENCIA[r])
    print(f"\n{'=' * 92}\n  {eq.upper()} CONTRA CADA RIVAL (probabilidades de {eq})\n{'=' * 92}")
    print(f"  {'Rival':<21}| {'COMO LOCAL':^22} | {'COMO VISITANTE':^22} | Marcador probable")
    print(f"  {'':<21}| {'Gana':>6}{'Empata':>8}{'Pierde':>8} | {'Gana':>6}{'Empata':>8}{'Pierde':>8} | (local / visita)")
    pts_esp = vic = emp = der = 0.0
    pron = {"G": 0, "E": 0, "P": 0}
    for r in rivales:
        a, b = PROB[(eq, r)], PROB[(r, eq)]
        gl, el, pl = a["local"], a["empate"], a["visita"]      # eq como local
        gv, ev, pv = b["visita"], b["empate"], b["local"]       # eq como visitante
        pts_esp += 3 * gl + el + 3 * gv + ev
        vic += gl + gv; emp += el + ev; der += pl + pv
        for g_, e_, p_ in ((gl, el, pl), (gv, ev, pv)):
            m = max(g_, e_, p_)
            pron["G" if m == g_ else "E" if m == e_ else "P"] += 1
        print(f"  {r:<21}| {gl * 100:5.1f}%{el * 100:7.1f}%{pl * 100:7.1f}% | "
              f"{gv * 100:5.1f}%{ev * 100:7.1f}%{pv * 100:7.1f}% | "
              f"{a['marcador'][0]}-{a['marcador'][1]} / {b['marcador'][1]}-{b['marcador'][0]}")

    print(f"\n  --- RESUMEN DE {eq.upper()} EN SUS 38 PARTIDOS ---")
    print(f"  Victorias esperadas: {vic:.1f} | Empates: {emp:.1f} | Derrotas: {der:.1f}")
    print(f"  Puntos esperados: {pts_esp:.1f}")
    print(f"  Partidos donde es favorito: {pron['G']} | donde se espera empate: {pron['E']} "
          f"| donde es el menos favorito: {pron['P']}")
    pos = ranking(eq, lambda e: POTENCIA[e])
    print(f"  Puesto esperado en la tabla: {pos}º de {len(datos)}")
    mas_dificil = min(rivales, key=lambda r: PROB[(eq, r)]["local"] + PROB[(r, eq)]["visita"])
    mas_facil = max(rivales, key=lambda r: PROB[(eq, r)]["local"] + PROB[(r, eq)]["visita"])
    print(f"  Rival mas dificil: {mas_dificil} | Rival mas facil: {mas_facil}")


# ----------------------------------------------------------------------------
# OPCION: CARA A CARA
# ----------------------------------------------------------------------------
def cara_a_cara():
    a = elegir_equipo("Equipo 1")
    b = elegir_equipo("Equipo 2", excluir=a)
    pa, pb = promedios(a), promedios(b)
    da, db = datos[a], datos[b]
    fa, fb = FUERZA[a], FUERZA[b]

    filas = [
        ("Puntos 2025-26", da["pts"], db["pts"], True, "{:.0f}"),
        ("Puntos por partido", pa["ppp"], pb["ppp"], True, "{:.2f}"),
        ("Victorias", da["g"], db["g"], True, "{:.0f}"),
        ("Empates", da["e"], db["e"], None, "{:.0f}"),
        ("Derrotas", da["p"], db["p"], False, "{:.0f}"),
        ("% victorias", pa["pct_g"], pb["pct_g"], True, "{:.1f}"),
        ("Goles a favor", da["gf"], db["gf"], True, "{:.0f}"),
        ("Goles en contra", da["gc"], db["gc"], False, "{:.0f}"),
        ("Goles a favor / partido", pa["gf_pp"], pb["gf_pp"], True, "{:.2f}"),
        ("Goles en contra / partido", pa["gc_pp"], pb["gc_pp"], False, "{:.2f}"),
        ("Diferencia de gol", pa["dg"], pb["dg"], True, "{:+.0f}"),
        ("Jerarquia del club (1-10)", da["jer"], db["jer"], True, "{:.1f}"),
        ("Fuerza de ataque (modelo)", fa[0], fb[0], True, "{:.2f}"),
        ("Goles que concede (modelo)", fa[1], fb[1], False, "{:.2f}"),
        ("Puntos esperados 2026-27", POTENCIA[a], POTENCIA[b], True, "{:.1f}"),
    ]
    print(f"\n{'=' * 66}\n  {a}  vs  {b}\n{'=' * 66}")
    print(f"  {'':<28}{a[:16]:>16}{b[:16]:>16}")
    gana_a = gana_b = 0
    for nombre, x, y, mayor_mejor, fmt in filas:
        sx, sy = fmt.format(x), fmt.format(y)
        if mayor_mejor is not None and x != y:
            mejor_a = (x > y) == mayor_mejor
            gana_a += mejor_a
            gana_b += not mejor_a
            sx += " ✔" if mejor_a else ""
            sy += "" if mejor_a else " ✔"
        print(f"  {nombre:<28}{sx:>16}{sy:>16}")
    print(f"\n  Categorias ganadas: {a} {gana_a} - {gana_b} {b}")

    for loc, vis in ((a, b), (b, a)):
        r = PROB[(loc, vis)]
        print(f"\n  📍 En casa de {loc}: {loc} {r['lam_l']:.2f} - {r['lam_v']:.2f} {vis} (goles esperados)")
        print(f"     Gana {loc}: {r['local'] * 100:.1f}% | Empate: {r['empate'] * 100:.1f}% | "
              f"Gana {vis}: {r['visita'] * 100:.1f}%")
        print(f"     Marcador mas probable: {r['marcador'][0]}-{r['marcador'][1]} "
              f"({r['p_marcador'] * 100:.1f}%)  →  {pronostico(r, loc, vis)}")
    # Doble enfrentamiento
    pts_a = 3 * PROB[(a, b)]["local"] + PROB[(a, b)]["empate"] + 3 * PROB[(b, a)]["visita"] + PROB[(b, a)]["empate"]
    pts_b = 3 * PROB[(b, a)]["local"] + PROB[(b, a)]["empate"] + 3 * PROB[(a, b)]["visita"] + PROB[(a, b)]["empate"]
    print(f"\n  En los dos partidos de la temporada, puntos esperados: {a} {pts_a:.2f} - {pts_b:.2f} {b}")
    fav = a if pts_a > pts_b else b
    print(f"  🏆 Favorito en el cara a cara: {fav}")


# ----------------------------------------------------------------------------
# OPCION: SIMULAR LA TEMPORADA
# ----------------------------------------------------------------------------
def muestrear_poisson(lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= random.random()
        if p <= L:
            return k
        k += 1


def predecir_temporada():
    pedir_datos_todos()
    equipos = list(datos)
    resaltar = None
    if input("\n¿Quieres resaltar un equipo en la tabla? (s/n): ").strip().lower() == "s":
        resaltar = elegir_equipo("Equipo a resaltar")

    partidos = [(l, v, PROB[(l, v)]["lam_l"], PROB[(l, v)]["lam_v"])
                for l in equipos for v in equipos if l != v]
    print(f"\nSimulando {N_SIM} temporadas completas (380 partidos cada una)...")

    n = len(equipos)
    campeon = dict.fromkeys(equipos, 0)
    top4 = dict.fromkeys(equipos, 0)
    europa = dict.fromkeys(equipos, 0)
    descenso = dict.fromkeys(equipos, 0)
    suma_pos = dict.fromkeys(equipos, 0)
    suma_pts = dict.fromkeys(equipos, 0)

    for _ in range(N_SIM):
        t = {e: [0, 0, 0] for e in equipos}
        for loc, vis, ll, lv in partidos:
            gl, gv = muestrear_poisson(ll), muestrear_poisson(lv)
            t[loc][1] += gl; t[loc][2] += gv
            t[vis][1] += gv; t[vis][2] += gl
            if gl > gv:
                t[loc][0] += 3
            elif gl < gv:
                t[vis][0] += 3
            else:
                t[loc][0] += 1; t[vis][0] += 1
        orden = sorted(equipos, key=lambda e: (t[e][0], t[e][1] - t[e][2], t[e][1]), reverse=True)
        campeon[orden[0]] += 1
        for pos, e in enumerate(orden, 1):
            suma_pos[e] += pos
            suma_pts[e] += t[e][0]
            top4[e] += pos <= 4
            europa[e] += 5 <= pos <= 6
            descenso[e] += pos > n - 3

    orden_final = sorted(equipos, key=lambda e: suma_pts[e], reverse=True)
    print(f"\n{'=' * 80}\n  TABLA PROYECTADA 2026-27\n{'=' * 80}")
    print(f"  {'#':>2} {'Equipo':<21}{'PTS':>6}{'Pos.med':>8}{'Campeon':>9}{'Top 4':>8}{'Europa':>8}{'Descenso':>10}")
    for i, e in enumerate(orden_final, 1):
        marca = "  ◄" if e == resaltar else ""
        print(f"  {i:>2} {e:<21}{suma_pts[e] / N_SIM:>6.1f}{suma_pos[e] / N_SIM:>8.1f}"
              f"{100 * campeon[e] / N_SIM:>8.1f}%{100 * top4[e] / N_SIM:>7.1f}%"
              f"{100 * europa[e] / N_SIM:>7.1f}%{100 * descenso[e] / N_SIM:>9.1f}%{marca}")

    fav = max(campeon, key=campeon.get)
    print(f"\n  🏆 CAMPEON PREDICHO: {fav} ({100 * campeon[fav] / N_SIM:.1f}% de probabilidad)")
    print(f"  Champions (top 4): {', '.join(orden_final[:4])}")
    print(f"  Europa League (5-6): {', '.join(orden_final[4:6])}")
    print(f"  Descenso: {', '.join(orden_final[-3:])}")
    if resaltar:
        pos = orden_final.index(resaltar) + 1
        print(f"\n  ➜ {resaltar}: puesto proyectado {pos}º con {suma_pts[resaltar] / N_SIM:.1f} puntos, "
              f"{100 * campeon[resaltar] / N_SIM:.1f}% de ser campeon, "
              f"{100 * descenso[resaltar] / N_SIM:.1f}% de descender.")


# ----------------------------------------------------------------------------
# OPCION: RANKING DE FUERZA
# ----------------------------------------------------------------------------
def ranking_fuerza():
    print(f"\n{'=' * 66}\n  RANKING DE FUERZA (puntos esperados en 38 partidos)\n{'=' * 66}")
    print(f"  {'#':>2} {'Equipo':<21}{'Esperados':>10}{'2025-26':>9}{'Dif.':>7}{'Jerar.':>8}")
    for i, e in enumerate(sorted(datos, key=lambda x: POTENCIA[x], reverse=True), 1):
        real = datos[e]["pts"] / datos[e]["pj"] * 38
        print(f"  {i:>2} {e:<21}{POTENCIA[e]:>10.1f}{real:>9.1f}{POTENCIA[e] - real:>+7.1f}{datos[e]['jer']:>8.1f}")
    print("\n  'Dif.' positiva = el modelo cree que subira respecto a lo que hizo (por jerarquia/regresion).")


# ----------------------------------------------------------------------------
# CAPTURA DE DATOS: solo ganados, perdidos, GF y GC (maximo 38 partidos)
# ----------------------------------------------------------------------------
def pedir_datos_equipo(eq, numero=None, total=None):
    """Pide SOLO ganados, perdidos, GF y GC. Empates y puntos se calculan solos."""
    cab = f"[{numero}/{total}] " if numero else ""
    print(f"\n{'-' * 50}\n  {cab}{eq.upper()}  (temporada de 38 partidos)\n{'-' * 50}")
    g = pedir_entero("  Partidos ganados (0-38): ", 0, 38)
    p = pedir_entero(f"  Partidos perdidos (0-{38 - g}): ", 0, 38 - g)
    e = 38 - g - p
    gf = pedir_entero("  Goles a favor (GF): ", 0, 300)
    gc = pedir_entero("  Goles en contra (GC): ", 0, 300)
    d = datos[eq]
    d.update(pj=38, g=g, e=e, p=p, pts=3 * g + e, gf=gf, gc=gc)
    print(f"  ✔ Empates: {e} | Puntos: {d['pts']} | Diferencia de gol: {gf - gc:+d}")


def pedir_datos_todos():
    """Recorre los 20 equipos, uno por uno, pidiendo sus datos."""
    equipos = list(datos)
    print("\nVas a ingresar los datos de los 20 equipos, uno por uno.")
    print("Solo se piden: ganados, perdidos, GF y GC (G + P no puede pasar de 38).")
    for i, eq in enumerate(equipos, 1):
        pedir_datos_equipo(eq, i, len(equipos))
    recalcular()
    print("\n✔ Datos de los 20 equipos ingresados. Modelo recalculado.")


def editar_equipo():
    eq = elegir_equipo("Equipo al que quieres ingresar datos")
    pedir_datos_equipo(eq)
    recalcular()
    print("✔ Datos actualizados y modelo recalculado.")
    mostrar_ficha(eq)


# ----------------------------------------------------------------------------
# MENU
# ----------------------------------------------------------------------------
def menu():
    recalcular()
    print("\n⚽  PREDICTOR DE LA LIGA ESPAÑOLA 2026-27 ⚽")
    print("Datos reales de la temporada 2025-26 ya cargados para los 20 equipos.")
    while True:
        print(f"\n{'-' * 52}")
        print("  1. Elegir un equipo: ficha + comparacion contra los 19 rivales")
        print("  2. Comparar dos equipos cara a cara")
        print("  3. Predecir temporada (te pide los datos de los 20 equipos)")
        print("  4. Ranking de fuerza de los 20 equipos")
        print("  5. Promedios y resumen de la liga")
        print("  6. Ingresar datos de un solo equipo")
        print("  0. Salir")
        op = input("Opcion: ").strip()
        if op == "1":
            comparar_con_todos()
        elif op == "2":
            cara_a_cara()
        elif op == "3":
            predecir_temporada()
        elif op == "4":
            ranking_fuerza()
        elif op == "5":
            mostrar_resumen_liga()
        elif op == "6":
            editar_equipo()
        elif op == "0":
            print("¡Hasta luego!")
            break
        else:
            print("  ⚠ Opcion no valida.")


if __name__ == "__main__":
    menu()