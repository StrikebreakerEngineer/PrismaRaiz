import time

import requests
from dotenv import dotenv_values

from léxico.analyzer import remove_accents

# --- Configuración ---
config = dotenv_values(".env")
RAE_API_KEY = config.get("RAE_API_KEY")
URL = "https://rae-api.com/api/words"

# Variable global para rastrear cuándo se hizo la última petición
_last_request_time = 0.0


class DailyQuotaExceeded(Exception):
    """Excepción lanzada cuando se agotan las 5,000 peticiones diarias."""


def _request_rae(session: requests.Session, word: str):
    global _last_request_time
    server_error_retries = 0 
    
    while True:
        # --- CONTROL DE TASA AUTOCONTENIDO (60 req/min -> 1 req/s) ---
        elapsed = time.time() - _last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        
        _last_request_time = time.time()

        try:
            response = session.get(
                f"{URL}/{word}",
                timeout=15,
            )
            
            # --- DETECCIÓN PREVENTIVA DE CUOTA DIARIA ---
            # Leemos las cabeceras provistas por el middleware de la API
            daily_remaining = response.headers.get("X-RateLimit-Daily-Remaining")
            if daily_remaining and daily_remaining.isdigit():
                remaining_int = int(daily_remaining)
                
                # Imprime una advertencia si te estás quedando sin créditos diarios
                if remaining_int <= 50 and remaining_int > 0:
                    print(f"⚠️ [Aviso Quota] Te quedan pocas peticiones hoy: {remaining_int} restantes.")
                
                # Si llega a 0, detenemos la ejecución inmediatamente de forma controlada
                if remaining_int == 0:
                    print("\n🚨 [ALERTA] Se ha alcanzado el límite diario (X-RateLimit-Daily-Remaining = 0).")
                    raise DailyQuotaExceeded("Límite diario agotado.")

            # --- Manejo de Límite de Tasa por Minuto (429) ---
            if response.status_code == 429:
                retry = 5  
                try:
                    data = response.json()
                    retry = data.get("retry_after", 5)
                except requests.exceptions.JSONDecodeError:
                    header_value = response.headers.get("Retry-After")
                    if header_value and header_value.isdigit():
                        retry = int(header_value)
                    else:
                        retry = 5
                
                print(f"⚠️ Límite de tasa alcanzado en el servidor. Esperando {retry} segundos...")
                time.sleep(retry)
                continue

            # --- Manejo de Palabra No Encontrada (404) ---
            if response.status_code == 404:
                return None

            # --- Validar el estado HTTP ANTES de leer el JSON ---
            response.raise_for_status() 
            
            # --- Parseo defensivo de JSON ---
            try:
                data = response.json()
            except requests.exceptions.JSONDecodeError:
                print(f"❌ El servidor no devolvió un JSON válido. Respuesta: {response.text[:100]}")
                return None

            if not data.get("ok"):
                return None

            return data["data"]

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            status = getattr(e.response, 'status_code', None)
            if status and status >= 500 and server_error_retries < 3:
                server_error_retries += 1
                wait_time = server_error_retries * 5
                print(f"⚠️ Error del servidor ({status}). Reintentando en {wait_time}s... (Intento {server_error_retries}/3)")
                time.sleep(wait_time)
                continue
            
            raise


def get_rae_entry(session: requests.Session, word: str):
    print(f"🔍 Buscando '{word}' en el diccionario RAE...")

    try:
        data = _request_rae(session, word)

        # AGREGADO: Confirmación si se encuentra la palabra original
        if data:
            print(f"✅ ¡Éxito! Palabra '{word}' encontrada.")
            return data

        simplified = remove_accents(word)

        if simplified != word:
            print(f"🔄 No encontrada. Intentando variante sin acentos: '{simplified}'...")
            data = _request_rae(session, simplified)
            
            # AGREGADO: Confirmación si se encuentra la palabra simplificada
            if data:
                print(f"✅ ¡Éxito! Variante '{simplified}' encontrada.")
                return data

        print(f"❌ '{word}' no se encuentra en el diccionario.")
        return None

    except requests.RequestException as error:
        print(f"Error consultando '{word}': {error}")
        return None


def main():
    with requests.Session() as session:
        session.headers.update({
            "X-API-Key": RAE_API_KEY
        })

        print(get_rae_entry(session, "ser"))


if __name__ == "__main__":
    main()