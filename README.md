# olx-aluguel-mcp

An MCP server that lets Claude **search rentals on OLX Brazil** and **flag likely rental scams** before you send anyone money.

## Why I built it

When I moved to Brazil I had to find an apartment in a city I didn't know, in a language I was still learning, on a marketplace where the *golpe do aluguel* (rental scam) is common. Every listing hid a different set of costs, and I couldn't tell a private owner from an agency, or a real ad from a fake one.

So I turned the checklist I was doing by hand into a tool.

## What it tells you about each listing

- **Every cost**: rent, condo fee, IPTU, the real monthly total, "gross" vs. "net" rent (punctuality discounts), fire insurance, FCI, bank fees, deposit (*caução*), *seguro-fiança*, contract fees, and which utilities are included.
- **Owner or agency?** With evidence: CRECI license, company name, commercial plan, ZAP feed.
- **Contacts found in the text**: phone numbers (including numbers spelled out in words), emails, links, Instagram, WhatsApp, and whether OLX verified the advertiser's phone.
- **Address**: neighborhood, CEP and the street it maps to (via ViaCEP), places mentioned in the description, and an approximate map link.
- **Advertiser profile**: account age, OLX identity/phone/email verification, reputation, advertiser's city, last activity.
- **Scam risk score (0–100)**: price vs. the local market, brand-new account, advertiser in another state, typical scam phrases (pay before visiting, owner abroad, keys by mail, urgency, moving the chat off OLX), too few photos, and more. It also gives you questions to ask the advertiser and a safety checklist.

## Tools

| Tool | What it does |
|---|---|
| `olx_buscar_alquileres` | Search with filters (location, type, price, bedrooms, bathrooms, parking, m², private/professional, furnished, pets, text, sort, page). Returns monthly total, R$/m² and quick alerts. With `analizar_top=N` it deep-analyzes the first N results. |
| `olx_ver_anuncio` | Full breakdown of a single listing (URL or ID). |
| `olx_analizar_riesgo` | Same as above, plus a price comparison against similar listings in the area. |
| `olx_comparar_anuncios` | Side-by-side table of 2–10 listings, sorted by total monthly cost. |
| `olx_precios_mercado` | Median, P25–P75 range and R$/m² for an area. |

The **location** is the part of the OLX URL after `/imoveis/aluguel/`, for example:

- `estado-pr/regiao-de-curitiba-e-paranagua` → Curitiba and region
- `estado-pr/regiao-de-curitiba-e-paranagua/boa-vista` → Boa Vista district
- `estado-pr/regiao-de-curitiba-e-paranagua/boa-vista/taruma` → Tarumã neighborhood

Tip: filter on olx.com.br however you like and pass that URL to `olx_buscar_alquileres` in the `url` parameter.

## How it works

- **No official API**, so it reads the same public pages you see in the browser. Requests go through `curl_cffi` (presenting as Chrome) with a 1.5 s delay between calls.
- **Fallback to a real browser**: if Cloudflare asks for verification, it switches to Playwright + Chromium automatically.
- **The score is explainable, not a black box**: every point comes from a named red or green flag, and the response lists them, so you can see *why* a listing looks risky.
- **Tests against real saved pages**: `tests/fixtures` holds an agency listing, a scam listing and a search page. When OLX changes its HTML, the tests break before the tool silently returns wrong data.

## Quick install (Linux)

Register the `run.sh` launcher in Claude Desktop. On first run it installs its dependencies into `.venv` and logs to `install.log`:

```json
{
  "mcpServers": {
    "olx-aluguel": {
      "command": "bash",
      "args": ["/PATH/TO/olx-aluguel-mcp/run.sh"]
    }
  }
}
```

## Manual install

Requirements: **Python 3.10+** and **Claude Desktop**.

1. Put the folder somewhere, e.g. `C:\mcp\olx-aluguel-mcp` (Windows) or `~/mcp/olx-aluguel-mcp` (Linux/Mac).
2. Install it from that folder:

   ```bash
   python -m pip install -e .
   ```

   (Use `python3` on Linux/Mac if needed. If your system requires a virtual environment: `python -m venv .venv`, then `.venv\Scripts\pip install -e .` on Windows or `.venv/bin/pip install -e .` on Linux/Mac.)

3. Check that it starts (it will wait for input; stop it with Ctrl+C):

   ```bash
   python -m olx_aluguel_mcp
   ```

4. In Claude Desktop go to **Settings → Developer → Edit config** and add the server to `claude_desktop_config.json`:

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
         "command": "/PATH/TO/olx-aluguel-mcp/.venv/bin/python",
         "args": ["-m", "olx_aluguel_mcp"]
       }
     }
   }
   ```

   Without a virtual environment, use the path to your Python (`where python` on Windows, `which python3` on Linux/Mac).

5. Restart Claude Desktop. The `olx_*` tools should appear in the tools menu.

### If OLX blocks requests

Install the real-browser fallback:

```bash
python -m pip install playwright
python -m playwright install chromium
```

It kicks in automatically when a verification page appears. To always use it, add `"env": {"OLX_USE_BROWSER": "1"}` to the server config.

## Example prompts

- "Find 1–2 bedroom apartments in Curitiba up to R$ 2,000, private owners only, and analyze the top 5."
- "Analyze this listing: https://pr.olx.com.br/regiao-de-curitiba-e-paranagua/imoveis/…"
- "Compare these 3 listings and tell me which one is cheapest per month with every fee included."
- "What does a 2-bedroom apartment cost on average in Tarumã?"

> The tool's output is in Spanish, its author's first language.

## Limitations and responsible use

- The scam score is a **heuristic**: it helps you prioritize and ask the right questions. It doesn't prove a listing is safe or fake. Never pay anything before visiting the property and checking the *matrícula*.
- The advertiser's **full phone number** is not extracted. OLX only shows it after clicking "Ver telefone", and this server respects that.
- OLX addresses are usually **approximate** (the CEP's street segment) unless the advertiser publishes the full address.
- It depends on OLX's HTML: if the site changes, `parsers.py` needs updating. Run `python -m pytest tests` to catch it.
- **Personal use, low volume.** OLX's Terms of Use restrict automated extraction. Don't use it to harvest data at scale or republish it.

## License

MIT
