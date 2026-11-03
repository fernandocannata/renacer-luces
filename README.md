# Renacer LightShow

Control de iluminación simple para la PC, pensado para eventos sociales.
Maneja cabezales móviles, pares LED, strobos y máquina de humo con una
interfaz USB-DMX tipo Open DMX, como la **ElectroTAS TZ-1U**.

Viene configurado con:

| Equipo | Cantidad | Modo | Direcciones |
|---|---|---|---|
| Venetian VT-B100 | 4 | 12 canales | 1, 13, 25, 37 |
| Tecshow Nebula Quad 14 | 8 | 8 canales | 49, 57, 65, 73, 81, 89, 97, 105 |

Si tus equipos tienen otras direcciones, cambialas en **Equipos y direcciones**.
Lo que importa es que coincidan con las que figuran en el display de cada equipo.

## Instalación

1. **Driver de la interfaz.** La TZ-1U usa un chip FTDI. Si ya la usaste con
   QLC+ o FreeStyler, el driver ya está instalado. Si no, bajalo de la sección
   Descargas de electrotas.com.ar o de ftdichip.com (driver "CDM" / D2XX).
2. **Abrir el programa**, de una de estas dos formas:
   - `RenacerLightShow.exe` (no necesita nada más), o
   - `iniciar.bat`, si tenés Python 3.9 o más nuevo instalado.
3. Se abre una ventana. Arriba a la izquierda tiene que decir
   **Interfaz conectada** en verde. Si dice "Simulador" o "no encontrada",
   revisá el cable, el driver y que no esté abierto QLC+, FreeStyler ni MagicQ:
   la interfaz la puede usar un solo programa a la vez.

Conectá también la fuente de 12 V de la TZ-1U: alimenta la etapa aislada de la salida DMX.

## Antes del primer evento: verificar el VT-B100

No hay tabla de canales publicada del VT-B100, así que el perfil trae el orden
más común en beams de 100 W de 12 canales. Hay que confirmarlo una vez:

1. Pestaña **Probar canales**, elegí "Cabezal 1".
2. Mové cada canal y mirá qué hace el equipo.
3. Si un canal hace otra cosa, cambiale la función en la lista.
4. Para la rueda de color y los gobos: subí el canal de a poco y anotá en qué
   valor aparece cada color o gobo. Escribilos en los recuadros de abajo.
5. Tocá **Guardar perfil**. Los cuatro cabezales toman el cambio al instante.

Si tenés el manual en papel, con la tabla de canales alcanza.

## Cómo se usa

**Elegir equipos.** Tocá los equipos de la izquierda, o un grupo: Todos,
Cabezales, Pares LED, 1-3-5, primera mitad…

**Programar.** Con equipos elegidos, en el centro:
- **Color e intensidad:** dimmer y paleta de colores. Sirve también para los
  cabezales: el programa elige el color más parecido de la rueda.
- **Posición:** arrastrá en el recuadro para apuntar. *Abanico* abre los
  cabezales. Podés guardar posiciones (ej. "Pista", "Novios").
- **Haz:** gobo, prisma, rueda de color y strobo del equipo.
- **Efectos:** persecución, onda, respiración, aleatorio, arcoíris, alternar
  colores, círculo, ocho, paneo y tilt. Van al tempo (tocá *Tap* al ritmo de la
  música) o a velocidad libre. Un efecto de color, uno de intensidad y uno de
  movimiento pueden convivir en los mismos equipos.

**Movimientos (cabezales en trípode, mirando al público).** En la pestaña
*Movimientos* está todo pensado de frente: posiciones fijas (al frente, al
público, abanico, cruzados, a los costados, en V, escalera, foco al centro) y
16 movimientos (círculos, ochos, barridos, espejo, ola, cascada, tijera,
abanico, péndulo, cuadrado, búsqueda al azar…). Los movimientos arrancan desde la posición actual de
cada cabezal: elegí primero una posición (abanico, en V…) y después el
movimiento; podés cambiar de posición con el movimiento andando, y
*Frenar movimiento* los deja quietos donde están. Cada movimiento se ajusta con
tamaño, altura, apertura, escalón, desfase, espejo y velocidad al tempo. Si no
elegiste cabezales, se aplica a todos.

**Ajustar el frente (una sola vez).** Al final de *Movimientos*: tocá un
cabezal, apuntalo al centro del público a la altura de la cabeza de la gente
y tocá *Este es su frente*. Repetí con cada uno. Después usá los botones
*Izquierda / Derecha / Arriba / Abajo* para verificar, y si alguno va al revés
tildá la opción que corresponda. Colgados, los cabezales casi no suben más
allá de la horizontal: el programa achata el movimiento para que entre.

**Las opciones se adaptan a lo que elegís.** Con solo cabezales aparecen
Posición, Movimientos y la rueda de color; con solo pares, sus efectos de
color; si elegís todo, solo lo que tienen en común.

**Efectos para los pares.** Persecución, rebote, llenado, onda, respiración,
aleatorio, chispas, relámpago, pares e impares, arcoíris, ola arcoíris,
alternar colores, pares e impares de color, mitades y fuego. Cada uno muestra
un dibujito de cómo se ve.

**Sumar movimientos.** En *Movimientos*, prendé *Sumar movimientos* y cada
movimiento nuevo se suma a los que ya andan (hasta 4). Apagado, reemplaza.

**Strobo 2.** Botón al lado de Strobo (tecla **A**). La flechita ▾ abre el
ritmo: al tempo (cada 2 tiempos, 1, 2 o 4 por tiempo) o libre (hasta 12 por
segundo), y si los destellos son en blanco.

**Calibrar la rueda de color y los gobos.** En *Probar canales*, elegí un
cabezal: *Prender el equipo para ver*, mové la rueda hasta ver un color entero
y tocá su nombre. Repetí con todos y tocá *Guardar perfil*.

**Tempo desde VirtualDJ (botón VDJ, al lado de Tap).** Prendido, el tempo
de los efectos y del Strobo 2 sigue a la música que suena en VirtualDJ y se
alinea con cada pulso. Apagado, el tempo lo marcás con Tap. Configuración en
VirtualDJ (una sola vez): *Settings → Options*, buscá **os2l**, poné `os2l` en
`yes` y `os2lDirectIp` en `127.0.0.1:9996`. Después, en *Settings → Controllers
→ Keyboard*, agregá una tecla (por ejemplo F12) con la acción
`os2l_button "renacer" on`. VirtualDJ se conecta recién cuando recibe un
comando OS2L: con Renacer LightShow abierto, tocá esa tecla una vez y desde
ahí manda el pulso solo. El punto del botón se pone verde cuando llegan los
pulsos.

**Clear.** Vuelve todo a cero, como recién abierto (luces apagadas, sin
efectos, master al 100%, sin blackout). Durante unos segundos aparece
*Deshacer* por si lo tocaste sin querer. No borra escenas ni el frente.

**Escenas.** Cuando te gusta lo que hay, tocá *Guardar escena*. Después la
recuperás con un toque, con fundido (barra *Fundido* de arriba). Las primeras
nueve también responden a las teclas 1 a 9.

**Secuencia.** Para momentos armados (entrada, vals, torta): agregá escenas en
orden y avanzá con **GO** o la barra espaciadora. Si le ponés *Espera*, pasa
solo al siguiente paso.

**Botones de golpe.** *Flash* (todo blanco), *Strobo* y *Humo* funcionan
mientras los mantenés apretados. *Blackout* apaga todo hasta que lo vuelvas a tocar.

## Atajos

| Tecla | Acción |
|---|---|
| Espacio | GO |
| 1 a 9 | Escenas |
| T | Tap de tempo |
| F / S / H (mantener) | Flash, strobo, humo |
| B | Blackout |
| A (mantener) | Strobo 2 |
| Ctrl+A / Esc | Seleccionar todo / nada |

## Desde el celular

En **Show y ajustes**, activá *Permitir controlar desde otros equipos*, cerrá y
volvé a abrir el programa. En el celular, conectado a la misma Wi-Fi, abrí la
dirección que aparece ahí.

## Dónde se guarda todo

En `Documentos\Renacer LightShow`: los shows (`shows\`), tus perfiles de equipos
(`perfiles\`) y los ajustes. El show se guarda solo cada pocos segundos.
Si venías usando la versión anterior (Renacer Luces), la primera vez se
copian solos tus shows y perfiles desde `Documentos\Renacer Luces`.

## Sumar equipos

En **Equipos y direcciones → Agregar equipos** hay perfiles para máquina de
humo (1 canal), strobo (2 canales), dimmer, LED RGB y RGBW. Si un equipo nuevo
no coincide, se ajusta en **Probar canales** y se guarda como perfil nuevo.

## Para desarrollar

- Sin dependencias obligatorias: solo la biblioteca estándar de Python.
- `python renacer_luces.py --sim` corre sin interfaz.
- `python -m pytest tests` corre las pruebas.
- Cada push a `main` arma `RenacerLightShow.exe` con GitHub Actions.
- El ícono se regenera con `python herramientas/hacer_icono.py` (necesita Pillow y numpy).

Estructura: `luces/engine.py` (motor: estado, fundidos, efectos, escenas),
`luces/dmx_output.py` (salida Open DMX por FTDI), `luces/server.py` (servidor
local), `web/` (interfaz), `perfiles/` (equipos).
