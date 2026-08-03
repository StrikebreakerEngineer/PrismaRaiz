import time

import requests
from dotenv import dotenv_values

from léxico.analyzer import remove_accents

# --- Configuración ---
config = dotenv_values(".env")
RAE_API_KEY = config.get("RAE_API_KEY")
URL = "https://rae-api.com"


def _request_rae(session: requests.Session, word: str):
    # Controla cuántas veces reintentamos si el servidor remoto falla
    server_error_retries = 0 
    
    while True:
        try:
            # Nota: Los encabezados ya están vinculados a la sesión, no es necesario pasarlos aquí
            response = session.get(
                f"{URL}/{word}",
                timeout=15,
            )
            
            # --- Manejo de Límite de Tasa (429) ---
            if response.status_code == 429:
                retry = 60  # Tiempo de espera por defecto si falla la lectura
                try:
                    # Intento defensivo de leer JSON (evita caídas si el servidor envía HTML)
                    data = response.json()
                    retry = data.get("retry_after", 60)
                except requests.exceptions.JSONDecodeError:
                    # Si no es un JSON válido, busca el encabezado HTTP estándar de reintento
                    retry = int(response.headers.get("Retry-After", 60))
                
                print(f"⚠️ Límite de tasa alcanzado. Esperando {retry} segundos...")
                time.sleep(retry)
                continue

            # --- Manejo de Palabra No Encontrada (404) ---
            if response.status_code == 404:
                return None

            # --- Manejo de Éxito (200) y Errores Inesperados ---
            # Lanza una excepción si hay códigos de error no controlados (400, 401, 500, etc.)
            response.raise_for_status() 
            
            data = response.json()
            if not data.get("ok"):
                return None

            return data["data"]

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            # Si es un error del servidor (5xx), espera un momento y vuelve a intentar
            status = getattr(e.response, 'status_code', None)
            if status and status >= 500 and server_error_retries < 3:
                server_error_retries += 1
                wait_time = server_error_retries * 5
                print(f"⚠️ Error del servidor ({status}). Reintentando en {wait_time}s... (Intento {server_error_retries}/3)")
                time.sleep(wait_time)
                continue
            
            # Si es un error de cliente fatal o superamos intentos, escala la excepción
            raise


def get_rae_entry(session: requests.Session, word: str):
    print(f"Buscando {word} en el diccionario RAE")

    try:
        data = _request_rae(session, word)

        if data:
            return data

        simplified = remove_accents(word)

        if simplified != word:
            return _request_rae(session, simplified)

        return None

    except requests.RequestException as error:
        print(f"Error consultando '{word}': {error}")
        return None



def main():
    print(get_rae_entry("ser"))


if __name__ == "__main__":
    main()