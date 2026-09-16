import json
import subprocess
import time
from urllib.parse import quote


BASE_HOST = "https://dle.rae.es"
AUTH_HEADER = "Basic cDY4MkpnaFMzOmFHRlVkQ2lFNDM0"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def curl_get(url):
    cmd = [
        "curl",
        "-s",
        "-L",
        "-H", f"Authorization: {AUTH_HEADER}",
        "-H", f"User-Agent: {USER_AGENT}",
        "-H", "Accept: application/json, text/plain, */*",
        "-H", "Accept-Language: es-ES,es;q=0.9",
        "--compressed",
        url,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    if result.returncode != 0:
        print("Curl error:")
        print(result.stderr)
        return None

    return result.stdout


def buscar(consulta):
    consulta_codificada = quote(consulta, safe="")
    url = f"{BASE_HOST}/data/search?w={consulta_codificada}"

    print(f"\nConsulta: {consulta!r}")
    print(f"URL:      {url}")

    raw = curl_get(url)

    if not raw:
        print("RESPUESTA VACÍA")
        return None

    try:
        datos = json.loads(raw)
    except json.JSONDecodeError:
        print("RESPUESTA NO JSON:")
        print(raw[:500])
        return None

    # Detectar Cloudflare 520
    if datos.get("cloudflare_error"):
        print("CLOUDFLARE ERROR")
        print(f"  status: {datos.get('status')}")
        print(f"  error:  {datos.get('error_code')}")
        print(f"  ray:    {datos.get('ray_id')}")
        return None

    resultados = datos.get("res", [])

    print(f"RESULTADOS: {len(resultados)}")
    print(f"APPROX:    {datos.get('approx')}")

    for resultado in resultados:
        print(
            f"  {resultado['id']:10} "
            f"{resultado.get('header', '')}"
        )

    return datos


if __name__ == "__main__":

    consultas = [
        "ser",
        "pero",
        "casa",
        "hablar",
        "a",
        "ab",
        "zzzzzzzzzz",
    ]

    for consulta in consultas:
        buscar(consulta)
        time.sleep(2)