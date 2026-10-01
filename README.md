# olx-aluguel-mcp

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![MCP](https://img.shields.io/badge/MCP-server-8A2BE2)
![Licencia MIT](https://img.shields.io/badge/licencia-MIT-green)
![Solo lectura](https://img.shields.io/badge/acceso-solo%20lectura-lightgrey)

Servidor [MCP](https://modelcontextprotocol.io) para **buscar alquileres en OLX Brasil** y **detectar posibles fraudes** desde Claude.

Lee las páginas públicas de OLX (las mismas que ves en el navegador, sin iniciar sesión) y, para cada anuncio, te dice cuánto pagarás de verdad, si es directo con el dueño y qué tan sospechoso es.

## Contenido

- [Qué analiza](#qué-analiza)
- [Herramientas](#herramientas)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Ejemplos de uso](#ejemplos-de-uso)
- [Solución de problemas](#solución-de-problemas)
- [Desarrollo](#desarrollo)
- [Limitaciones y uso responsable](#limitaciones-y-uso-responsable)

## Qué analiza

| Área | Detalle |
|---|---|
| **Todos los pagos** | Alquiler, condominio, IPTU, total mensual, alquiler "bruto" vs "líquido" (bonificación por pago puntual), seguro incendio, FCI, gastos bancarios, caução, seguro-fiança, tasas de contrato y qué servicios están incluidos (agua, luz, internet…). |
| **¿Directo con el dueño?** | Particular vs. inmobiliaria, con evidencias: CRECI, nombre de empresa, plan comercial, feed de ZAP… |
| **Contactos que aparecen** | Teléfonos (también escritos con palabras), e-mails, links, Instagram, WhatsApp y CRECI; y si el anunciante tiene teléfono registrado/verificado en OLX. |
| **Dirección** | Barrio, CEP, calle del CEP (vía ViaCEP), direcciones y referencias del texto, otros barrios mencionados y enlace al mapa aproximado. |
| **Perfil del anunciante** | Antigüedad de la cuenta, identidad/teléfono/e-mail verificados por OLX, reputación, ciudad del anunciante y última actividad. |
| **Riesgo de fraude (0–100)** | Precio vs. mercado de la zona, cuenta nueva, anunciante en otro estado, frases típicas del *golpe do aluguel* (pago antes de visitar, dueño en el exterior, llaves por correo, urgencia, sacar la conversación de OLX…), pocas fotos, etc. Incluye preguntas para el anunciante y un checklist de seguridad. |

El nivel de riesgo es **BAJO** (< 25), **MEDIO** (25–49) o **ALTO** (≥ 50).

## Herramientas

Todas son de solo lectura y aceptan `formato`: `markdown` (por defecto, legible) o `json` (estructurado).

| Herramienta | Qué hace |
|---|---|
| `olx_buscar_alquileres` | Búsqueda con filtros (ubicación, tipo, precio, habitaciones, baños, vagas, m², particular/profesional, características, condominio, texto, orden, página). Devuelve total mensual, R$/m² y alertas rápidas. Con `analizar_top=N` (máx. 10) analiza a fondo los primeros N, a ~3 s por anuncio. |
| `olx_ver_anuncio` | Ficha completa de un anuncio (URL o número). |
| `olx_analizar_riesgo` | Lo mismo que la anterior, más la comparación de precio con anuncios similares de la zona (`comparar_mercado`, 1–2 consultas extra). |
| `olx_comparar_anuncios` | Tabla comparativa de 2 a 10 anuncios, ordenada por costo total mensual. |
| `olx_precios_mercado` | Mediana, rango P25–P75 y R$/m² de una zona, a partir de hasta 3 páginas (50 anuncios c/u). |

### Filtros de `olx_buscar_alquileres`

| Parámetro | Valores |
|---|---|
| `ubicacion` | Ruta de OLX (ver más abajo). Por defecto, Curitiba y región. |
| `tipo` | `todos`, `apartamentos`, `casas`, `habitaciones` |
| `precio_min` / `precio_max` | R$; con `precio_incluye_condominio=true` el filtro aplica a alquiler + condominio |
| `habitaciones`, `banos`, `garajes` | Listas, p. ej. `[1, 2]` (en habitaciones, `5` = 5 o más) |
| `area_min` / `area_max` | m² |
| `anunciante` | `todos`, `particular` (≈ directo con el dueño), `profesional` |
| `caracteristicas` | `academia`, `aquecimento`, `ar_condicionado`, `area_servico`, `armarios_cozinha`, `armarios_quarto`, `banheiro_no_quarto`, `churrasqueira`, `internet`, `mobiliado`, `piscina`, `porteiro_24h` |
| `condominio` | `academia`, `area_murada`, `condominio_fechado`, `elevador`, `aceita_pet`, `piscina`, `portao_eletronico`, `portaria`, `salao_festas`, `seguranca_24h` |
| `texto` | Texto libre en portugués, p. ej. `mobiliado`, `próximo PUC` |
| `ordenar` | `relevancia`, `recientes` (por defecto), `menor_precio`, `mayor_precio` |
| `pagina`, `limite` | Página (50 por página) y máximo de anuncios a devolver (1–50) |
| `url` | Alternativa: una URL de búsqueda de OLX ya filtrada (ignora los demás filtros) |

### Cómo indicar la ubicación

`ubicacion` es la parte de la URL de OLX que va después de `/imoveis/aluguel/`:

| Valor | Zona |
|---|---|
| `estado-pr/regiao-de-curitiba-e-paranagua` | Curitiba y región |
| `estado-pr/regiao-de-curitiba-e-paranagua/boa-vista` | Zona Boa Vista de Curitiba |
| `estado-pr/regiao-de-curitiba-e-paranagua/boa-vista/taruma` | Barrio Tarumã |
| `estado-sp/sao-paulo-e-regiao` | São Paulo y región |

**Truco:** filtra en olx.com.br como quieras y pásale la URL resultante a `olx_buscar_alquileres` en el parámetro `url`.

## Instalación

Requisitos: **Python 3.10 o superior** y un cliente MCP como **Claude Desktop**.

### Opción A: lanzador automático (Linux)

Descarga el repositorio y registra `run.sh` en Claude Desktop. La primera vez instala las dependencias solo, en `.venv` (con `uv` si está disponible; si no, con `venv` + `pip`), y deja el registro en `install.log`.

```bash
git clone https://github.com/ErgoCodes/olx-aluguel-mcp.git
```

En Claude Desktop: **Configuración → Desarrollador → Editar configuración**, y dentro de `mcpServers` agrega:

```json
{
  "mcpServers": {
    "olx-aluguel": {
      "command": "bash",
      "args": ["/RUTA/A/olx-aluguel-mcp/run.sh"]
    }
  }
}
```

Reinicia Claude Desktop por completo. La primera ejecución puede tardar uno o dos minutos mientras instala; si no aparecen las herramientas `olx_*`, revisa `install.log`.

### Opción B: instalación manual (Windows, Linux y Mac)

1. Clona el repositorio, por ejemplo en `C:\mcp\olx-aluguel-mcp` (Windows) o `~/mcp/olx-aluguel-mcp` (Linux/Mac).
2. Crea un entorno virtual e instala el paquete desde esa carpeta:

   ```bash
   python -m venv .venv
   .venv/bin/pip install -e .            # Linux / Mac
   .venv\Scripts\pip install -e .        # Windows
   ```

   (En Linux/Mac puede ser `python3` en lugar de `python`.)

3. Comprueba que arranca. Se queda esperando; ciérralo con Ctrl+C:

   ```bash
   .venv/bin/python -m olx_aluguel_mcp
   ```

4. Registra el servidor en `claude_desktop_config.json`:

   **Windows**
   ```json
   {
     "mcpServers": {
       "olx-aluguel": {
         "command": "C:\\mcp\\olx-aluguel-mcp\\.venv\\Scripts\\python.exe",
         "args": ["-m", "olx_aluguel_mcp"]
       }
     }
   }
   ```

   **Linux / Mac**
   ```json
   {
     "mcpServers": {
       "olx-aluguel": {
         "command": "/RUTA/A/olx-aluguel-mcp/.venv/bin/python",
         "args": ["-m", "olx_aluguel_mcp"]
       }
     }
   }
   ```

5. Reinicia Claude Desktop. Deberías ver las herramientas `olx_*` en el menú de herramientas.

> El paquete también instala el comando `olx-aluguel-mcp`, que sirve como `command` en cualquier cliente MCP compatible con transporte stdio.

## Configuración

| Variable de entorno | Efecto |
|---|---|
| `OLX_USE_BROWSER` | `1`, `true` o `yes` fuerza el uso de Chromium (Playwright) en todas las consultas, en vez de usarlo solo cuando OLX pide verificación. |

Se define en el bloque `env` del servidor:

```json
"olx-aluguel": {
  "command": "bash",
  "args": ["/RUTA/A/olx-aluguel-mcp/run.sh"],
  "env": { "OLX_USE_BROWSER": "1" }
}
```

Otros valores fijos del cliente: pausa de **1,5 s** entre peticiones, caché de **10 minutos** y tiempo máximo de **25 s** por petición.

## Ejemplos de uso

- "Busca apartamentos de 1 o 2 habitaciones en Curitiba hasta R$ 2.000, solo de particulares, y analiza los 5 primeros."
- "Analiza este anuncio: https://pr.olx.com.br/regiao-de-curitiba-e-paranagua/imoveis/…"
- "Compara estos 3 anuncios y dime cuál sale más barato al mes con todos los gastos."
- "¿Cuánto cuesta en promedio un apartamento de 2 habitaciones en el Tarumã?"
- "Busca casas que acepten mascotas, con churrasqueira, ordenadas de menor a mayor precio."

## Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| No aparecen las herramientas `olx_*` | Reinicia Claude Desktop por completo y revisa `install.log` (Opción A). |
| `ensurepip is not available` | Falta el módulo venv: `sudo apt install python3-venv`, y reinicia Claude Desktop. |
| La instalación quedó a medias | Borra `.venv` y `.install_failed`, o ejecuta `bash install.sh` a mano para ver el error. |
| OLX bloquea las consultas (Cloudflare) | Instala el plan B con navegador real (abajo). Si ya lo tienes, espera unos minutos y haz menos consultas. |
| "No hay suficientes anuncios" en `olx_precios_mercado` | La zona tiene muy pocos anuncios: usa una ubicación más amplia o sube `paginas`. |

### Plan B: navegador real

El servidor usa `curl_cffi` (se presenta como Chrome) y espera 1,5 s entre peticiones. Si aun así Cloudflare pide verificación, instala Playwright en el mismo entorno virtual:

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
```

Se usa automáticamente cuando aparece la verificación. Para usarlo siempre, define `OLX_USE_BROWSER=1`.

## Desarrollo

```
src/olx_aluguel_mcp/
├── server.py      # herramientas MCP y formato de salida
├── client.py      # cliente HTTP: URLs, límite de frecuencia, caché, plan B con navegador
├── parsers.py     # extracción de datos del HTML de OLX
└── analysis.py    # costos, contactos, dirección, dueño vs. inmobiliaria, riesgo de fraude
tests/
├── test_all.py        # pruebas (sin red, con páginas guardadas)
├── make_fixtures.py   # regenera las páginas de ejemplo
└── fixtures/
```

```bash
python tests/test_all.py        # o: python -m pytest tests
```

Las pruebas no hacen peticiones a OLX: usan HTML guardado con el mismo formato de las páginas reales. Si OLX cambia su web, fallarán o habrá que ajustar `parsers.py`.

## Limitaciones y uso responsable

- El puntaje de fraude es **heurístico**: sirve para priorizar y hacer las preguntas correctas; no garantiza que un anuncio sea seguro o falso. Nunca pagues nada antes de visitar el inmueble y ver la matrícula.
- El **teléfono completo** del anunciante no se extrae: OLX solo lo muestra al pulsar "Ver telefone" en su página, y este servidor respeta eso.
- La dirección de OLX suele ser **aproximada** (la calle o tramo del CEP), salvo que el anunciante publique la dirección completa.
- Los precios de `olx_precios_mercado` son precios pedidos, no de cierre; se excluyen valores < R$ 250 y > R$ 60.000 (OLX a veces clasifica mal ventas o alquileres por día).
- Depende del HTML de OLX: si cambia su web, habrá que ajustar `parsers.py`.
- Es para **uso personal** y con pocas consultas. Los Términos de Uso de OLX limitan la extracción automatizada: no lo uses para recolectar datos masivamente ni para republicarlos.

## Licencia

[MIT](LICENSE)
