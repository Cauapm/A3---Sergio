import os
import json
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
import streamlit as st
from supabase import create_client
import pandas as pd

load_dotenv()

from gerenciador_filas import GerenciadorFilas
from extracao import ExtratorFila
from modelos import NivelPrioridade, StatusCliente

API_PORT = 8502
API_HOST = "localhost"

gerenciador = None
gerenciador_lock = threading.Lock()
system_started = False
system_start_lock = threading.Lock()


def get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    if "supabase.com/dashboard/project/" in url:
        ref = url.rstrip("/").split("/")[-1]
        url = f"https://{ref}.supabase.co"
    return create_client(url, key)


def get_gerenciador():
    global gerenciador
    with gerenciador_lock:
        if gerenciador is None:
            gerenciador = GerenciadorFilas(auto_carregar=True)
        return gerenciador


def calcular_tempo_medio_espera(supabase_client):
    if not supabase_client:
        return None
    try:
        res = supabase_client.table("atendimentos").select("data_chamada,data_finalizado").not_.is_("data_finalizado", "null").execute()
        if not res.data:
            return None
        total_ms = 0
        count = 0
        for row in res.data:
            try:
                inicio = datetime.fromisoformat(row["data_chamada"].replace("Z", "+00:00"))
                fim = datetime.fromisoformat(row["data_finalizado"].replace("Z", "+00:00"))
                total_ms += (fim - inicio).total_seconds() * 1000
                count += 1
            except Exception:
                continue
        if count == 0:
            return None
        return total_ms / count
    except Exception:
        return None


def build_payload():
    g = get_gerenciador()
    g.sincronizar_estado()

    tamanhos = g.tamanhos()
    supabase_client = get_supabase_client()

    total_aguardando = sum(tamanhos.values())
    atendimentos_count = 0
    if supabase_client:
        try:
            res = supabase_client.table("atendimentos").select("id_chamada", count="exact").execute()
            atendimentos_count = res.count or 0
        except Exception:
            pass

    tmed = calcular_tempo_medio_espera(supabase_client)

    senha_atual = None
    if supabase_client:
        try:
            res = supabase_client.table("atendimentos").select("id_chamada,cliente_id,guiche,data_chamada,data_finalizado,clientes_fila!inner(nivel_prioridade,status)").order("data_chamada", desc=True).limit(1).execute()
            if res.data:
                row = res.data[0]
                cliente = row.get("clientes_fila", {})
                status = cliente.get("status", "aguardando")
                senha_atual = {
                    "id": row.get("cliente_id"),
                    "tipo": cliente.get("nivel_prioridade"),
                    "nivel_prioridade": cliente.get("nivel_prioridade"),
                    "guiche": row.get("guiche"),
                    "data_chamada": row.get("data_chamada"),
                    "data_finalizado": row.get("data_finalizado"),
                    "status": status
                }
        except Exception:
            pass

    filas_dict = {"super": [], "padrao": [], "conv": []}
    for key, nivel in [("super", NivelPrioridade.SUPER_PRIORIDADE), ("padrao", NivelPrioridade.PRIORIDADE_PADRAO), ("conv", NivelPrioridade.CONVENCIONAL)]:
        fila = g._fila_para(nivel)
        for i, cliente in enumerate(fila):
            filas_dict[key].append({
                "id": cliente.id,
                "nome": cliente.nome,
                "nivel_prioridade": int(cliente.nivel_prioridade),
                "motivo": cliente.motivo,
                "data_chegada": cliente.data_chegada.isoformat() if cliente.data_chegada else None,
                "status": cliente.status.value
            })

    distribuicao = {
        "super": tamanhos["super"],
        "padrao": tamanhos["padrao"],
        "conv": tamanhos["conv"]
    }

    payload = {
        "systemctl": system_started,
        "conexao": supabase_client is not None,
        "data_hora": datetime.now(timezone.utc).isoformat(),
        "total": total_aguardando,
        "super": tamanhos["super"],
        "padrao": tamanhos["padrao"],
        "conv": tamanhos["conv"],
        "atend": atendimentos_count,
        "tmed": tmed,
        "senha_atual": senha_atual,
        "filas": filas_dict,
        "distribuicao": distribuicao,
        "fase_atual": g.fase_atual(),
        "contadores": g.estado_contadores()
    }
    return payload


class APIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/data":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            payload = build_payload()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        elif parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global system_started
        parsed = urlparse(self.path)
        if parsed.path == "/api/start":
            with system_start_lock:
                if not system_started:
                    get_gerenciador().sincronizar_estado()
                    system_started = True
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "systemctl": system_started}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_api_server():
    server = HTTPServer((API_HOST, API_PORT), APIHandler)
    server.serve_forever()


def main():
    st.set_page_config(page_title="Fila Bancária — Dashboard", layout="wide")

    if "api_server_started" not in st.session_state:
        api_thread = threading.Thread(target=start_api_server, daemon=True)
        api_thread.start()
        st.session_state.api_server_started = True
        time.sleep(0.5)

    api_url = f"http://{API_HOST}:{API_PORT}"

    with open("dashboard.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    html_content = html_content.replace('const API_BASE = \'\';', f'const API_BASE = \'{api_url}\';')

    st.components.v1.html(html_content, height=1000, scrolling=True)


if __name__ == "__main__":
    main()