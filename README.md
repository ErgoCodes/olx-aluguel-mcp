# olx-aluguel-mcp

Servidor MCP para **buscar alquileres en OLX Brasil** y **detectar posibles fraudes** desde Claude.

Lee las páginas públicas de OLX (las mismas que ves en el navegador) y te dice, para cada anuncio:

- **Todos los pagos**: alquiler, condominio, IPTU, total mensual, alquiler "bruto" vs "líquido" (bonificación por pago puntual), seguro incendio, FCI, gastos bancarios, caução, seguro-fiança, tasas de contrato, qué servicios están incluidos (agua, luz, internet…).
- **¿Directo con el dueño?**: particular vs. inmobiliaria, con evidencias (CRECI, nombre de empresa, plan comercial, feed de ZAP…).
- **Contactos que aparecen**: teléfonos, números escritos con palabras, e-mails, links, Instagram, WhatsApp, CRECI; y si el anunciante tiene teléfono registrado/verificado en OLX.
- **Dirección**: barrio, CEP, calle del CEP (ViaCEP), direcciones y referencias que menciona el texto, otros barrios mencionados, enlace al mapa aproximado.
- **Perfil del anunciante**: antigüedad de la cuenta, identidad/teléfono/e-mail verificados por OLX, reputación, ciudad del anunciante, última actividad.
- **Riesgo de fraude (0–100)**: precio vs. mercado de la zona, cuenta nueva, anunciante en otro estado, frases típicas del *golpe do aluguel* (pago antes de visitar, dueño en el exterior, llaves por correo, urgencia, sacar la conversación de OLX…), pocas fotos, etc. Incluye preguntas para el anunciante y un checklist de seguridad.

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `olx_buscar_alquileres` | Búsqueda con filtros (ubicación, tipo, precio, habitaciones, baños, vagas, m², particular/profesional, mobiliado, acepta mascotas, texto, orden, página). Devuelve total mensual, R$/m² y alertas rápidas. Con `analizar_top=N` analiza a fondo los primeros N. |
| `olx_ver_anuncio` | Ficha completa de un anuncio (URL o número). |
| `olx_analizar_riesgo` | Igual que la anterior + comparación de precio con anuncios similares de la zona. |
| `olx_comparar_anuncios` | Tabla comparativa de 2 a 10 anuncios (ordenada por costo total). |
| `olx_precios_mercado` | Mediana, rango P25–P75 y R$/m² de una zona. |

La **ubicación** es la parte de la URL de OLX que va después de `/imoveis/aluguel/`, por ejemplo:

- `estado-pr/regiao-de-curitiba-e-paranagua` → Curitiba y región
- `estado-pr/regiao-de-curitiba-e-paranagua/boa-vista` → zona Boa Vista de Curitiba
- `estado-pr/regiao-de-curitiba-e-paranagua/boa-vista/taruma` → barrio Tarumã

Truco: filtra en olx.com.br como quieras y pásale la URL a `olx_buscar_alquileres` en el parámetro `url`.

## Instalación rápida (Linux)

Copia la carpeta y registra en Claude Desktop el lanzador `run.sh` (la primera vez instala las dependencias solo, en `.venv`, y deja el registro en `install.log`):

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

## Instalación manual

Requisitos: **Python 3.10 o superior** y la app **Claude Desktop**.

1. Descomprime la carpeta, por ejemplo en `C:\mcp\olx-aluguel-mcp` (Windows) o `~/mcp/olx-aluguel-mcp` (Linux/Mac).
2. Abre una terminal en esa carpeta e instala:

   ```bash
   python -m pip install -e .
   ```

   (En Linux/Mac puede ser `python3`. Si tu sistema lo pide, usa un entorno virtual: `python -m venv .venv` y luego `.venv\Scripts\pip install -e .` en Windows o `.venv/bin/pip install -e .` en Linux/Mac.)

3. Comprueba que arranca (se queda esperando; ciérralo con Ctrl+C):

   ```bash
   python -m olx_aluguel_mcp
   ```

4. En Claude Desktop: **Configuración → Desarrollador → Editar configuración** y agrega el servidor a `claude_desktop_config.json`:

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

   Si no usaste entorno virtual, pon la ruta de tu Python (en Windows: `where python`; en Linux/Mac: `which python3`).

5. Reinicia Claude Desktop. Deberías ver las herramientas `olx_*` en el menú de herramientas.

### Si OLX bloquea las consultas

El servidor usa `curl_cffi` (se presenta como Chrome) y espera 1,5 s entre peticiones. Si aun así Cloudflare pide verificación, instala el plan B con navegador real:

```bash
python -m pip install playwright
python -m playwright install chromium
```

Se usa automáticamente cuando aparece la verificación. Para usarlo siempre, agrega `"env": {"OLX_USE_BROWSER": "1"}` en la configuración del servidor.

## Ejemplos de uso (en Claude)

- "Busca apartamentos de 1 o 2 habitaciones en Curitiba hasta R$ 2.000, solo de particulares, y analiza los 5 primeros."
- "Analiza este anuncio: https://pr.olx.com.br/regiao-de-curitiba-e-paranagua/imoveis/…"
- "Compara estos 3 anuncios y dime cuál sale más barato al mes con todos los gastos."
- "¿Cuánto cuesta en promedio un apartamento de 2 habitaciones en el Tarumã?"

## Limitaciones y uso responsable

- El puntaje de fraude es **heurístico**: sirve para priorizar y hacer las preguntas correctas; no garantiza que un anuncio sea seguro o falso. Nunca pagues nada antes de visitar el inmueble y ver la matrícula.
- El **teléfono completo** del anunciante no se extrae: OLX solo lo muestra al pulsar "Ver telefone" en su página, y este servidor respeta eso.
- La dirección de OLX suele ser **aproximada** (la calle/tramo del CEP), salvo que el anunciante publique la dirección completa.
- Depende del HTML de OLX: si OLX cambia su web, habrá que ajustar `parsers.py`. Los tests (`python -m pytest tests`) ayudan a detectarlo.
- Es para **uso personal** y con pocas consultas. Los Términos de Uso de OLX limitan la extracción automatizada; no lo uses para recolectar datos masivamente ni para republicarlos.
