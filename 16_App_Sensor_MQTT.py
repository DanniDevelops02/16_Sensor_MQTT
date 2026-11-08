import json
import math
import random
import string
import threading
import time
from collections import deque
from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st

try:
    import paho.mqtt.client as mqtt
except ImportError:  # se avisa en pantalla; la app no puede conectarse sin esta librería
    mqtt = None

try:
    from zoneinfo import ZoneInfo

    ZONA = ZoneInfo("America/Bogota")
except Exception:  # sin base de zonas horarias se usa la hora del servidor
    ZONA = None

st.set_page_config(
    page_title="Sensor MQTT · Daniel Flórez",
    page_icon="📡",
    layout="centered",
    initial_sidebar_state="expanded",
)

# =====================================================================
#  AJUSTES  (los valores por defecto coinciden con el sketch de Wokwi)
# =====================================================================
BROKER_DEFECTO = "broker.mqttdashboard.com"
PUERTO_DEFECTO = 1883
TOPICO_DEFECTO = "Sensor/THP2"

MAX_HISTORIAL = 300        # lecturas que se guardan en memoria
MAX_RECEPTORES = 4         # conexiones simultáneas permitidas en este servidor
INACTIVO_MAX = 900         # segundos sin uso tras los que se cierra una conexión
SIN_DATOS_AVISO = 10       # segundos sin mensajes para mostrar una ayuda
REFRESCO_SEG = 2           # cada cuánto se actualiza la página en modo automático

# Nombres bonitos y unidades para los campos que manda el ESP32
ETIQUETAS = {
    "temp": ("Temperatura", "°C"),
    "temperature": ("Temperatura", "°C"),
    "temperatura": ("Temperatura", "°C"),
    "hum": ("Humedad", "%"),
    "humidity": ("Humedad", "%"),
    "humedad": ("Humedad", "%"),
}
COLORES_GRAFICA = ["#3f71a6", "#f0a030", "#2f9e6f", "#8a5cc2"]

# =====================================================================
#  ESTILO (paleta fría basada en #3f71a6)
# =====================================================================
PRIMARIO = "#3f71a6"
OSCURO = "#1b2f45"
CLARO = "#eaf2f9"
SUAVE = "#a9c7e3"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Playfair+Display:wght@500;600;700&display=swap');

:root, .stApp { color-scheme: light; }
html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; font-size: 1.06rem; }
.stApp { background: linear-gradient(180deg, #f6fafd 0%, __CLARO__ 100%); }
header[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 860px; padding-top: 3rem; padding-bottom: 4rem; }
[data-testid="stHeaderActionElements"] { display: none !important; }

/* Texto de la página principal: siempre oscuro, aunque el navegador esté en modo oscuro */
.block-container p, .block-container li, .block-container label,
.block-container [data-testid="stMarkdownContainer"],
.block-container [data-testid="stWidgetLabel"] * { color: __OSCURO__; }
.block-container [data-testid="stCaptionContainer"] * { color: #4d6479 !important; }

/* Hero */
.hero { text-align: center; padding: 1rem 0 .5rem 0; }
.hero .etiqueta {
    color: __PRIMARIO__; letter-spacing: .25em; text-transform: uppercase;
    font-size: .85rem; font-weight: 600;
}
.hero h1 {
    font-family: 'Playfair Display', serif; font-size: 3.1rem; color: __OSCURO__;
    margin: .3rem 0 .6rem 0; line-height: 1.12;
}
.hero p { color: #4d6479 !important; font-size: 1.2rem; max-width: 640px; margin: 0 auto; }
.linea { width: 70px; height: 4px; border-radius: 4px; background: __PRIMARIO__; margin: 1.4rem auto; }
h2, h3 { font-family: 'Playfair Display', serif !important; color: __OSCURO__ !important; }

/* Tarjetas (contenedores con key="tarjeta_...") */
[class*="st-key-tarjeta"] {
    background: #ffffff !important;
    border: 1px solid __SUAVE__88 !important;
    border-radius: 18px !important;
    box-shadow: 0 8px 24px rgba(63, 113, 166, .08);
    padding: 1.4rem 1.5rem 1.3rem 1.5rem !important;
}
[class*="st-key-tarjeta"] p, [class*="st-key-tarjeta"] label, [class*="st-key-tarjeta"] li,
[class*="st-key-tarjeta"] [data-testid="stWidgetLabel"] * { color: __OSCURO__ !important; }

/*__CAMPOS__*/

/* Botones */
.stButton > button, .stDownloadButton > button {
    background: __PRIMARIO__; color: #ffffff !important; border: 1.5px solid __PRIMARIO__;
    border-radius: 999px; padding: .6rem 1.4rem; font-weight: 600; transition: all .2s ease;
}
.stButton > button p, .stDownloadButton > button p { color: #ffffff !important; }
.stButton > button:hover, .stDownloadButton > button:hover {
    background: __OSCURO__; border-color: __OSCURO__; transform: translateY(-2px);
}

/* Estado de la conexión */
.estado {
    display: inline-flex; align-items: center; gap: 10px; border-radius: 999px; padding: 7px 18px;
    font-weight: 600; font-size: .95rem; margin-bottom: .6rem;
}
.estado .punto { width: 11px; height: 11px; border-radius: 50%; background: currentColor; }
.estado.ok { background: #e8f6ef; color: #1f7a52 !important; }
.estado.espera { background: #fff6e0; color: #96630a !important; }
.estado.error { background: #fdecec; color: #b03030 !important; }
.estado.ok .punto { animation: pulso 1.6s ease-in-out infinite; }
@keyframes pulso { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .35; transform: scale(.75); } }
@media (prefers-reduced-motion: reduce) { .estado.ok .punto { animation: none; } }
.dato-linea { color: #4d6479 !important; font-size: .92rem; margin: .1rem 0 .8rem 0; }

/* Medidas */
.medidas { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin: .4rem 0; }
.medida {
    background: linear-gradient(160deg, #f6fafd, __CLARO__); border: 1px solid __SUAVE__99;
    border-radius: 16px; padding: 1.1rem 1.2rem; text-align: center;
}
.medida .nombre { font-size: .8rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: #4d6479 !important; }
.medida .valor { font-family: 'Playfair Display', serif; font-size: 3.2rem; line-height: 1.15; color: __PRIMARIO__ !important; font-weight: 700; }
.medida .unidad { font-size: 1.3rem; font-weight: 500; color: __OSCURO__ !important; }
.medida .delta { font-size: .85rem; color: #4d6479 !important; min-height: 1.2em; }

/* Sidebar */
[data-testid="stSidebar"] { background: __OSCURO__; }
[data-testid="stSidebar"] * { color: #e6f0f9 !important; }

#MainMenu, footer { visibility: hidden; }
</style>
"""


def inyectar_css() -> None:
    css = CSS.replace("/*__CAMPOS__*/", CSS_CAMPOS)
    for token, valor in {
        "__PRIMARIO__": PRIMARIO, "__OSCURO__": OSCURO, "__CLARO__": CLARO, "__SUAVE__": SUAVE,
    }.items():
        css = css.replace(token, valor)
    st.markdown(css, unsafe_allow_html=True)


CSS_CAMPOS = """
/* ---- Campos, selectores, desplegables y avisos: siempre claros (a prueba de modo oscuro) ---- */
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stNumberInput"] [data-baseweb="input"],
[data-testid="stTextArea"] [data-baseweb="textarea"] {
    background-color: #ffffff !important; border: 1px solid __SUAVE__ !important;
    border-radius: 12px !important; box-shadow: none !important;
}
[data-testid="stTextInput"] [data-baseweb="input"] *,
[data-testid="stNumberInput"] [data-baseweb="input"] *,
[data-testid="stTextArea"] [data-baseweb="textarea"] * {
    background-color: transparent !important; border-color: transparent !important; box-shadow: none !important;
    color: __OSCURO__ !important; -webkit-text-fill-color: __OSCURO__ !important; fill: __OSCURO__ !important;
}
[data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
[data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
[data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within {
    border-color: __PRIMARIO__ !important; box-shadow: 0 0 0 1px __PRIMARIO__ !important;
}
[data-testid="stTextInput"] input::placeholder { color: #7d93a8 !important; -webkit-text-fill-color: #7d93a8 !important; opacity: 1; }

/* Avisos (st.info, st.warning, st.error, st.success) */
[data-testid="stAlert"] { --alerta-fondo: __CLARO__; --alerta-borde: __SUAVE__; }
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) { --alerta-fondo: #fff6e0; --alerta-borde: #f2d08a; }
[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) { --alerta-fondo: #fdecec; --alerta-borde: #f0b4b4; }
[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) { --alerta-fondo: #e8f6ef; --alerta-borde: #a6d8bf; }
[data-testid="stAlert"] {
    background-color: var(--alerta-fondo) !important; border: 1px solid var(--alerta-borde) !important;
    border-radius: 14px !important; overflow: hidden;
}
[data-testid="stAlert"] > div, [data-testid="stAlert"] [data-baseweb="notification"] {
    background-color: var(--alerta-fondo) !important; border: none !important; border-radius: 14px !important;
}
[data-testid="stAlert"] * { color: __OSCURO__ !important; -webkit-text-fill-color: __OSCURO__ !important; }
[data-testid="stAlert"] p, [data-testid="stAlert"] span, [data-testid="stAlert"] div { background-color: transparent !important; }

/* Desplegables (st.expander): la barra del título también es clara */
[data-testid="stExpander"] details {
    background-color: #ffffff !important; border: 1px solid __SUAVE__88 !important; border-radius: 16px !important;
    box-shadow: 0 8px 24px rgba(63, 113, 166, .08); overflow: hidden;
}
[data-testid="stExpander"] summary { background-color: #ffffff !important; }
[data-testid="stExpander"] summary:hover { background-color: __CLARO__ !important; }
[data-testid="stExpander"] summary * { background-color: transparent !important; color: __OSCURO__ !important; fill: __OSCURO__ !important; }
[data-testid="stExpander"] p, [data-testid="stExpander"] li, [data-testid="stExpander"] label { color: __OSCURO__ !important; }
[data-testid="stExpander"] svg { fill: __OSCURO__ !important; color: __OSCURO__ !important; }

/* Interruptor (st.toggle) */
[data-testid="stCheckbox"] label, [data-testid="stToggle"] label { color: __OSCURO__ !important; }

/* El menú con el cambio de tema se oculta: esta página está diseñada solo en claro */
[data-testid="stMainMenu"] { display: none !important; }
"""


# =====================================================================
#  CONEXIÓN MQTT
#
#  MQTT funciona con "publicar / suscribirse":
#    - El ESP32 PUBLICA mensajes en un tópico (aquí «Sensor/THP2»).
#    - Esta app se SUSCRIBE al mismo tópico y el BROKER le reenvía cada mensaje.
#  Esta app abre UNA conexión que se queda abierta en segundo plano y guarda lo que llega.
# =====================================================================
def crear_cliente_paho(id_cliente: str):
    """Crea el cliente MQTT; funciona igual con paho-mqtt 1.x y 2.x."""
    if mqtt is None:
        raise RuntimeError("Falta la librería paho-mqtt en requirements.txt")
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=id_cliente)  # paho 2.x
    except AttributeError:
        return mqtt.Client(client_id=id_cliente)  # paho 1.x


class Receptor:
    """Mantiene una suscripción MQTT abierta y guarda los mensajes recibidos."""

    def __init__(self, broker: str, puerto: int, topico: str, fabrica=None):
        self.broker, self.puerto, self.topico = broker, puerto, topico
        # El ID de cliente debe ser único en el broker: si dos clientes usan el mismo,
        # el broker desconecta al anterior. Por eso lleva un sufijo al azar.
        sufijo = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        self.id_cliente = f"streamlit-{sufijo}"
        self.mensajes = deque(maxlen=MAX_HISTORIAL)  # (hora_epoch, tópico, texto)
        self.total = 0
        self.conectado = False
        self.error = ""
        self.creado = time.time()
        self.ultimo_uso = self.creado
        self._cerrojo = threading.Lock()

        self.cliente = (fabrica or crear_cliente_paho)(self.id_cliente)
        self.cliente.on_connect = self._al_conectar
        self.cliente.on_disconnect = self._al_desconectar
        self.cliente.on_connect_fail = self._al_fallar
        self.cliente.on_message = self._al_recibir
        self.cliente.reconnect_delay_set(min_delay=1, max_delay=15)
        self.cliente.connect_async(broker, puerto, keepalive=30)
        self.cliente.loop_start()  # hilo en segundo plano: conecta, escucha y reconecta solo

    # --- Se ejecutan en el hilo de paho ---
    def _al_conectar(self, cliente, userdata, flags, rc, *extra):
        codigo = getattr(rc, "value", rc)  # paho 2.x entrega un objeto; paho 1.x un entero
        if codigo == 0:
            self.conectado = True
            self.error = ""
            cliente.subscribe(self.topico, qos=0)  # se repite en cada reconexión
        else:
            self.conectado = False
            self.error = f"El broker rechazó la conexión (código {codigo})."

    def _al_desconectar(self, cliente, userdata, *args):
        self.conectado = False

    def _al_fallar(self, cliente, userdata, *args):
        self.conectado = False
        self.error = (
            f"No se pudo conectar con {self.broker}:{self.puerto}. "
            "Revisa la dirección, el puerto o la conexión a internet."
        )

    def _al_recibir(self, cliente, userdata, mensaje):
        texto = mensaje.payload.decode("utf-8", errors="replace")
        with self._cerrojo:
            self.mensajes.append((time.time(), mensaje.topic, texto))
            self.total += 1

    # --- Se usan desde Streamlit ---
    def estado(self) -> str:
        if self.conectado:
            return "conectado"
        return "error" if self.error else "conectando"

    def instantanea(self) -> list:
        with self._cerrojo:
            return list(self.mensajes)

    def detener(self) -> None:
        try:
            self.cliente.disconnect()
            self.cliente.loop_stop()
        except Exception:
            pass


@st.cache_resource
def registro() -> dict:
    """Guarda las conexiones abiertas (se conserva entre ejecuciones y entre visitantes)."""
    return {"cerrojo": threading.Lock(), "receptores": {}}


def obtener_receptor(broker: str, puerto: int, topico: str) -> Receptor:
    """Devuelve la conexión para esta configuración, creándola si hace falta."""
    reg = registro()
    clave = (broker, puerto, topico)
    ahora = time.time()
    with reg["cerrojo"]:
        activos = reg["receptores"]
        for k, r in list(activos.items()):  # cierra las que llevan mucho tiempo sin usarse
            if k != clave and ahora - r.ultimo_uso > INACTIVO_MAX:
                r.detener()
                del activos[k]
        receptor = activos.get(clave)
        if receptor is None:
            while len(activos) >= MAX_RECEPTORES:
                k_viejo = min(activos, key=lambda k: activos[k].ultimo_uso)
                activos.pop(k_viejo).detener()
            receptor = Receptor(broker, puerto, topico)
            activos[clave] = receptor
        receptor.ultimo_uso = ahora
        return receptor


# =====================================================================
#  DATOS: de texto recibido a números y tablas
# =====================================================================
def campos_numericos(texto: str) -> dict:
    """{'Temp': 24.1, 'Hum': 55.0} a partir de un JSON; ignora lo que no sea un número."""
    try:
        dato = json.loads(texto)
    except ValueError:
        return {}
    if isinstance(dato, (int, float)) and not isinstance(dato, bool):
        dato = {"valor": dato}
    if not isinstance(dato, dict):
        return {}
    salida = {}
    for clave, valor in dato.items():
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            continue
        if math.isfinite(valor):
            salida[str(clave)] = float(valor)
    return salida


def hora_local(epoch: float) -> datetime:
    if ZONA is not None:
        return datetime.fromtimestamp(epoch, ZONA).replace(tzinfo=None)
    return datetime.fromtimestamp(epoch)


def construir_tabla(mensajes: list, corte: float = 0.0) -> pd.DataFrame:
    filas = []
    for epoch, _topico, texto in mensajes:
        if epoch <= corte:
            continue
        campos = campos_numericos(texto)
        if campos:
            filas.append({"hora": hora_local(epoch), **campos})
    return pd.DataFrame(filas)


def etiqueta_de(clave: str) -> tuple:
    return ETIQUETAS.get(clave.lower(), (clave, ""))


def hace_cuanto(segundos: float) -> str:
    segundos = max(0, int(segundos))
    if segundos < 60:
        return f"hace {segundos} s"
    return f"hace {segundos // 60} min {segundos % 60} s"


def html_medidas(tabla: pd.DataFrame) -> str:
    columnas = [c for c in tabla.columns if c != "hora"]
    tarjetas = []
    for col in columnas:
        serie = tabla[col].dropna()  # si una lectura llega incompleta, se usa el último valor válido
        if serie.empty:
            continue
        valor = serie.iloc[-1]
        delta = ""
        if len(serie) > 1:
            d = valor - serie.iloc[-2]
            flecha = "▲" if d > 0.05 else ("▼" if d < -0.05 else "•")
            delta = f"{flecha} {abs(d):.1f} desde la lectura anterior"
        nombre, unidad = etiqueta_de(col)
        tarjetas.append(
            '<div class="medida">'
            f'<div class="nombre">{escape(nombre)}</div>'
            f'<div class="valor">{valor:.1f}<span class="unidad"> {escape(unidad)}</span></div>'
            f'<div class="delta">{delta}</div></div>'
        )
    return '<div class="medidas">' + "".join(tarjetas) + "</div>"


def describir_estado(receptor: Receptor, mensajes: list) -> tuple:
    """(clase CSS, texto del distintivo, ayuda o None)."""
    estado = receptor.estado()
    ahora = time.time()
    if estado == "error":
        return "error", "Sin conexión", receptor.error
    if estado == "conectando":
        if ahora - receptor.creado > SIN_DATOS_AVISO:
            return "espera", "Conectando…", (
                "Está tardando más de lo normal. Revisa la dirección y el puerto del broker "
                "en «Ajustes de conexión»."
            )
        return "espera", "Conectando al broker…", None
    if not mensajes:
        ayuda = None
        if ahora - receptor.creado > SIN_DATOS_AVISO:
            ayuda = (
                "La conexión con el broker funciona, pero todavía no llega ningún mensaje. "
                "¿Está corriendo la simulación en Wokwi? ¿El tópico es exactamente el mismo que en el sketch?"
            )
        return "espera", "Conectado · esperando datos", ayuda
    edad = ahora - mensajes[-1][0]
    if edad > SIN_DATOS_AVISO + 5:
        return "espera", "Conectado · sin mensajes recientes", (
            f"El último mensaje llegó {hace_cuanto(edad)}. Si apagaste la simulación en Wokwi, es normal."
        )
    return "ok", "Conectado · recibiendo datos", None


# =====================================================================
#  PÁGINA
# =====================================================================
inyectar_css()

with st.sidebar:
    st.subheader("Cómo funciona")
    st.markdown(
        "1. El ESP32 de Wokwi **publica** su lectura en un tópico.\n"
        "2. El **broker** MQTT recibe el mensaje.\n"
        "3. Esta página está **suscrita** a ese tópico y el broker se lo reenvía.\n"
        "4. Aquí se muestra el valor y se guarda el historial."
    )
    st.caption("Esta página solo escucha: no envía nada al sensor.")
    st.subheader("Privacidad")
    st.markdown(
        "El broker público es compartido: cualquiera que conozca el tópico puede leer "
        "y publicar en él. No lo uses para datos privados."
    )

st.markdown(
    """
    <div class="hero">
        <div class="etiqueta">Internet de las cosas</div>
        <h1>Sensor en vivo</h1>
        <p>Un ESP32 simulado en Wokwi mide temperatura y humedad y las publica por MQTT.
        Esta página las recibe en tiempo real.</p>
        <div class="linea"></div>
    </div>
    """,
    unsafe_allow_html=True,
)

if mqtt is None:
    st.error("Falta la librería `paho-mqtt`. Agrégala a `requirements.txt` y reinicia la app.")
    st.stop()

# ---- Conexión ----
with st.container(key="tarjeta_conexion"):
    st.subheader("Conexión")
    st.caption(
        "Con la simulación de Wokwi en marcha, los valores por defecto ya funcionan: no necesitas cambiar nada."
    )
    with st.expander("Ajustes de conexión"):
        broker = st.text_input("Broker MQTT", value=BROKER_DEFECTO, help="Dirección del servidor MQTT").strip()
        puerto = st.number_input(
            "Puerto", value=PUERTO_DEFECTO, min_value=1, max_value=65535, step=1,
            help="1883 es el puerto estándar sin cifrado.",
        )
        topico = st.text_input(
            "Tópico", value=TOPICO_DEFECTO, help="Debe ser idéntico al que usa el sketch del ESP32."
        ).strip()
    en_vivo = st.toggle("Actualizar automáticamente", value=True)
    if not en_vivo:
        st.button("Actualizar ahora")

if not broker or not topico or " " in broker:
    st.error("Escribe un broker y un tópico válidos (sin espacios en la dirección del broker).")
    st.stop()

try:
    receptor = obtener_receptor(broker, int(puerto), topico)
except Exception as error:
    st.error(f"No se pudo iniciar la conexión: {error}")
    st.stop()

if "corte" not in st.session_state:
    st.session_state["corte"] = 0.0  # «Limpiar historial» oculta lo anterior solo para ti

st.write("")


@st.fragment(run_every=REFRESCO_SEG if en_vivo else None)
def panel() -> None:
    mensajes = receptor.instantanea()
    receptor.ultimo_uso = time.time()
    clase, texto_estado, ayuda = describir_estado(receptor, mensajes)
    tabla = construir_tabla(mensajes, st.session_state["corte"])

    with st.container(key="tarjeta_lecturas"):
        st.subheader("Lecturas")
        st.markdown(
            f'<div class="estado {clase}"><span class="punto"></span>{escape(texto_estado)}</div>',
            unsafe_allow_html=True,
        )
        detalle = f"{escape(receptor.broker)}:{receptor.puerto} · tópico {escape(receptor.topico)}"
        if mensajes:
            detalle += f" · último mensaje {hace_cuanto(time.time() - mensajes[-1][0])}"
        st.markdown(f'<div class="dato-linea">{detalle}</div>', unsafe_allow_html=True)
        if ayuda:
            st.warning(ayuda)

        if not tabla.empty:
            st.markdown(html_medidas(tabla), unsafe_allow_html=True)
        elif mensajes:
            st.info("Llegan mensajes, pero no contienen números que se puedan graficar. Mira el mensaje crudo abajo.")

    if not tabla.empty:
        st.write("")
        with st.container(key="tarjeta_historial"):
            st.subheader("Historial")
            columnas = [c for c in tabla.columns if c != "hora"]
            if len(tabla) < 2:
                st.caption("Esperando más lecturas para dibujar la gráfica…")
            else:
                for i, col in enumerate(columnas):
                    nombre, unidad = etiqueta_de(col)
                    st.caption(f"{nombre} ({unidad})" if unidad else nombre)
                    st.line_chart(
                        tabla.set_index("hora")[[col]],
                        color=COLORES_GRAFICA[i % len(COLORES_GRAFICA)],
                        height=210,
                    )
            izq, der = st.columns(2)
            with izq:
                st.download_button(
                    "Descargar datos (CSV)",
                    data=tabla.to_csv(index=False).encode("utf-8"),
                    file_name="lecturas_sensor.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with der:
                if st.button("Limpiar historial", use_container_width=True):
                    st.session_state["corte"] = time.time()
                    st.rerun()

    st.write("")
    with st.expander("Detalles técnicos"):
        st.markdown(
            f"- **Broker:** `{receptor.broker}` · **puerto:** `{receptor.puerto}` (MQTT sin cifrar)\n"
            f"- **Tópico:** `{receptor.topico}` · **QoS:** 0\n"
            f"- **ID de cliente de esta app:** `{receptor.id_cliente}`\n"
            f"- **Mensajes recibidos desde que se abrió la conexión:** {receptor.total}"
        )
        if mensajes:
            _epoch, topico_msg, ultimo = mensajes[-1]
            st.caption(f"Último mensaje crudo (tópico `{topico_msg}`):")
            st.code(ultimo, language="json")


panel()
