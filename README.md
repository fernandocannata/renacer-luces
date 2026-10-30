# Renacer Luces

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
   - `RenacerLuces.exe` (no necesita nada más), o
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
| A / Esc | Seleccionar todo / nada |

## Desde el celular

En **Show y ajustes**, activá *Permitir controlar desde otros equipos*, cerrá y
volvé a abrir el programa. En el celular, conectado a la misma Wi-Fi, abrí la
dirección que aparece ahí.

## Dónde se guarda todo

En `Documentos\Renacer Luces`: los shows (`shows\`), tus perfiles de equipos
(`perfiles\`) y los ajustes. El show se guarda solo cada pocos segundos.

## Sumar equipos

En **Equipos y direcciones → Agregar equipos** hay perfiles para máquina de
humo (1 canal), strobo (2 canales), dimmer, LED RGB y RGBW. Si un equipo nuevo
no coincide, se ajusta en **Probar canales** y se guarda como perfil nuevo.

## Para desarrollar

- Sin dependencias obligatorias: solo la biblioteca estándar de Python.
- `python renacer_luces.py --sim` corre sin interfaz.
- `python -m pytest tests` corre las pruebas.
- Cada push a `main` arma `RenacerLuces.exe` con GitHub Actions.

Estructura: `luces/engine.py` (motor: estado, fundidos, efectos, escenas),
`luces/dmx_output.py` (salida Open DMX por FTDI), `luces/server.py` (servidor
local), `web/` (interfaz), `perfiles/` (equipos).
