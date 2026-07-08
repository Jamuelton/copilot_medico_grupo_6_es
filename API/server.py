import sys
import os
import json
import uuid
from datetime import datetime

from flask import Flask, g, request, jsonify
from flask_cors import CORS
import tempfile
import speech_recognition as sr

# Assuming these imports are correct and available
from backend import gemini_connection
from backend import pdf_reader
from backend import text_filter
from backend.auth_decorators import token_required
from backend.auth_service import (
    AuthError,
    authenticate_user,
    create_access_token,
    get_profile_details,
    is_valid_email,
    normalize_email,
    normalize_profile,
    normalize_profiles,
    sanitize_user,
)
from backend.config import settings

# Importa TODAS as funções do seu patient_db.py
from backend.patient_db import (
    load_database, save_database, generate_patient_id, get_patient_data, 
    get_all_patients_info, ensure_patient_exists, get_patient_chat_history, 
    add_message_to_history, add_consultation_to_patient, get_patient_consultations, 
    get_consultation_chat_history, add_message_to_consultation_history, add_transcription_log_to_patient,
    get_patient_transcription_log
    )
from backend.processador_voz.processador_voz import TranscritorVoz
from backend.audio_service import Diarizador


def get_cors_origins():
    configured_origins = settings.cors_origins.strip()
    if not configured_origins or configured_origins == "*":
        return "*"
    return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]


app = Flask(__name__)
CORS(
    app,
    resources={r"/api/*": {"origins": get_cors_origins()}},
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)

audio_processor = None

try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    # Caminhos para os modelos dentro da pasta backend
    MODEL_PATH = os.path.join(BASE_DIR, "backend", "vosk-model-small-pt-0.3")
    SPK_MODEL_PATH = os.path.join(BASE_DIR, "backend", "vosk-model-spk-0.4")

    print(f"[SERVER] Carregando Modelos de IA...")

    # Inicializa a classe Diarizador (Vosk + Google)
    if os.path.exists(MODEL_PATH) and os.path.exists(SPK_MODEL_PATH):
        audio_processor = Diarizador(
            model_path=MODEL_PATH,
            spk_model_path=SPK_MODEL_PATH
        )
        print("✅ Diarizador Inteligente carregado com sucesso!")
    else:
        print(f"⚠️ Modelos não encontrados em: {MODEL_PATH}")
        print("   -> Baixe os modelos em https://alphacephei.com/vosk/models e extraia na pasta backend.")

except Exception as e:
    print(f"⚠️ AVISO: Falha ao carregar Diarizador: {e}")
    print("   -> O sistema funcionará apenas com Transcrição Simples.")
    audio_processor = None


def _json_error(message, status_code):
    return jsonify({"status": "error", "message": message}), status_code


def _auth_success_response(user, profile, token, expires_in):
    return jsonify({
        "status": "success",
        "token": token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "user": sanitize_user(user),
        "profile": get_profile_details(profile),
        "available_profiles": [
            get_profile_details(user_profile)
            for user_profile in normalize_profiles(user.get("profiles"))
        ],
    }), 200


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _json_error("Corpo JSON invalido.", 400)

    email = normalize_email(data.get("email"))
    password = data.get("password")

    if not email or password is None:
        return _json_error("Email e senha sao obrigatorios.", 400)
    if not is_valid_email(email):
        return _json_error("Email invalido.", 400)
    if not isinstance(password, str) or not password:
        return _json_error("Senha obrigatoria.", 400)

    user = authenticate_user(email, password)
    if not user:
        return _json_error("Email ou senha invalidos", 401)

    profiles = normalize_profiles(user.get("profiles"))
    if not profiles:
        return _json_error("Usuario sem perfil de acesso.", 403)

    requested_profile = normalize_profile(data.get("profile"))
    selected_profile = requested_profile if requested_profile else profiles[0]
    if selected_profile not in profiles:
        return _json_error("Perfil nao permitido para este usuario.", 403)

    try:
        token, expires_in = create_access_token(user, selected_profile)
    except AuthError as exc:
        return _json_error(exc.message, exc.status_code)

    return _auth_success_response(user, selected_profile, token, expires_in)


@app.route('/api/auth/select-profile', methods=['POST'])
@token_required
def select_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _json_error("Corpo JSON invalido.", 400)

    selected_profile = normalize_profile(data.get("profile"))
    if not selected_profile:
        return _json_error("Perfil e obrigatorio.", 400)
    if selected_profile not in normalize_profiles(g.current_user.get("profiles")):
        return _json_error("Perfil nao permitido para este usuario.", 403)

    try:
        token, expires_in = create_access_token(g.current_user, selected_profile)
    except AuthError as exc:
        return _json_error(exc.message, exc.status_code)

    return _auth_success_response(g.current_user, selected_profile, token, expires_in)


@app.route('/api/auth/me', methods=['GET'])
@token_required
def get_authenticated_user():
    profile = getattr(g, "current_profile", "")
    return jsonify({
        "status": "success",
        "user": getattr(g, "current_user_safe", {}),
        "profile": get_profile_details(profile),
        "available_profiles": [
            get_profile_details(user_profile)
            for user_profile in normalize_profiles(g.current_user.get("profiles"))
        ],
    }), 200


@app.route('/api/transcribe_audio', methods=['POST'])
def transcribe_audio_route():
    """
    Recebe áudio, faz Diarização (se disponível) ou Transcrição simples,
    salva no log e retorna o texto para o chat.
    """
    tmp_path = None
    try:
        # 1. Validação Básica
        if 'audio_file' not in request.files:
            return jsonify({"status": "error", "message": "Nenhum arquivo enviado."}), 400

        audio_file = request.files['audio_file']
        patient_id = request.form.get('patient_id')
        consultation_id = request.form.get('consultation_id')
        # Duração estimada vinda do front (pode ser 0)
        duration_input = request.form.get('duration', 0.0, type=float)

        if not patient_id or not consultation_id:
            return jsonify({"status": "error", "message": "IDs obrigatórios."}), 400

        # 2. Salvar arquivo temporário
        file_ext = '.wav'
        if audio_file.filename and '.' in audio_file.filename:
            file_ext = '.' + audio_file.filename.split('.')[-1]

        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
            tmp_path = tmp.name
            audio_file.save(tmp_path)
            print(f"[TRANSCRIÇÃO] Áudio salvo em: {tmp_path}")

        # Variáveis de resultado
        texto_final = ""
        dialogue_structure = None
        final_duration = duration_input

        # 3. Processamento (Tentativa de Diarização Inteligente)
        processed_successfully = False

        if audio_processor:
            try:
                print(f"[TRANSCRIÇÃO] Iniciando Diarização (Vosk + Google)...")
                # Aqui chamamos sua classe Diarizador
                result = audio_processor.processar_audio(tmp_path)

                texto_final = result['full_text']
                dialogue_structure = result['dialogue']  # Estrutura JSON rica (Médico/Paciente)

                # Se a duração veio 0 do front, tentamos estimar (opcional, mas o Vosk não retorna duration total fácil)
                if final_duration == 0 and dialogue_structure:
                    # Pega o fim do último segmento como duração aproximada
                    final_duration = dialogue_structure[-1].get('end', 0) if len(dialogue_structure) > 0 else 0

                processed_successfully = True
                print("[TRANSCRIÇÃO] Diarização concluída com sucesso.")
            except Exception as e:
                print(f"❌ Erro na Diarização: {e}. Tentando fallback simples...")
                processed_successfully = False

        # 4. Fallback (Transcrição Simples) se o Diarizador falhar ou não existir
        if not processed_successfully:
            print(f"[TRANSCRIÇÃO] Usando Transcritor Simples (Legacy)...")
            try:
                transcritor = TranscritorVoz(idioma="pt-BR")
                with sr.AudioFile(tmp_path) as source:
                    audio_data = transcritor.reconhecedor.record(source)
                    # Calcula duração se não tiver
                    if final_duration == 0:
                        final_duration = len(audio_data.frame_data) / audio_data.sample_rate / audio_data.sample_width

                    texto_final = transcritor.transcrever(audio_data)
                    dialogue_structure = None  # Não tem estrutura de médico/paciente
            except Exception as e_simple:
                print(f"❌ Erro fatal também na transcrição simples: {e_simple}")
                raise e_simple

        # 5. Validação de Erro de Áudio (Silêncio/Ruído)
        invalid_phrases = [
            "Não foi possível entender o áudio",
            "Erro na API de reconhecimento"
        ]
        if any(phrase in texto_final for phrase in invalid_phrases):
            return jsonify({
                "status": "success",
                "transcription": texto_final,
                "is_error": True
            }), 200

        # 6. Salvar no Banco (Com o novo campo 'dialogue')
        log_entry = add_transcription_log_to_patient(
            patient_id=patient_id,
            consultation_id=consultation_id,
            text=texto_final,
            duration_seconds=final_duration if final_duration > 0 else 1.0,
            dialogue=dialogue_structure  # <--- O PULO DO GATO ESTÁ AQUI
        )

        return jsonify({
            "status": "success",
            "transcription": texto_final,
            "consultation_id": consultation_id,
            "log_entry": log_entry,  # O frontend vai receber isso e renderizar colorido
            "is_error": False
        }), 200

    except Exception as e:
        print(f"[TRANSCRIÇÃO] Erro 500: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Erro interno: {e}"}), 500
    finally:
        # Limpeza
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

# Rota para obter EXCLUSIVAMENTE o histórico de transcrições de áudio
@app.route('/api/patients/<patient_id>/transcription-log', methods=['GET'])
def get_transcription_log_api(patient_id):
    try:
        logs = get_patient_transcription_log(patient_id) # Função do seu patient_db
        return jsonify({
            "status": "success",
            "logs": logs,
            "count": len(logs)
        }), 200
    except Exception as e:
        print(f"Erro ao buscar logs: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# NOVO ENDPOINT: Verificar existência do Patient ID
@app.route('/api/patient-exists/<patient_id>', methods=['GET'])
def check_patient_exists_api(patient_id):
    """
    Verifica se um paciente com o ID fornecido existe no banco de dados.
    Retorna JSON com 'exists': true/false.
    """
    try:
        patient_data = get_patient_data(patient_id) 
        exists = patient_data is not None
        return jsonify({"status": "success", "exists": exists}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Erro ao verificar existência do paciente: {e}"}), 500

# NOVO ENDPOINT: Criar Paciente
@app.route('/api/patients', methods=['POST'])
def create_patient():
    """
    Cria um novo paciente e retorna seu ID e nome.
    Espera um JSON com 'name' (opcional).
    """
    try:
        data = request.json
        patient_name = data.get('name')

        new_patient_id = generate_patient_id()
        patient_data = ensure_patient_exists(new_patient_id, name=patient_name)
        
        # Adiciona a primeira "consulta" padrão ao criar o paciente
        first_consultation_id = add_consultation_to_patient(new_patient_id, "Primeira Consulta")

        return jsonify({
            "status": "success",
            "patient_id": new_patient_id,
            "patient_name": patient_data.get("name", "Desconhecido"),
            "first_consultation_id": first_consultation_id
        }), 201 # 201 Created

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Erro interno do servidor ao criar paciente: {e}"}), 500


# Endpoint do Chat para usar o histórico da consulta selecionada
@app.route('/api/chat', methods=['POST'])
def handle_chat_message():
    try:
        data = request.json
        if not data or 'message' not in data:
            return jsonify({"status": "error", "message": "Requisição inválida."}), 400

        user_message = data['message']
        patient_id = data.get('patient_id')
        consultation_id = data.get('consultation_id') # ID da consulta atual

        new_patient_id_generated = None

        if not patient_id: # Se não tem patient_id, cria um novo
            patient_id = generate_patient_id()
            new_patient_id_generated = patient_id
            ensure_patient_exists(patient_id, name="Desconhecido")
            # Não é necessário load_database() aqui, pois ensure_patient_exists já salva.

        # Se não tem consultation_id, ou se o paciente é novo, cria uma primeira consulta
        if not consultation_id:
            patient_consultations = get_patient_consultations(patient_id)
            if patient_consultations:
                # Assumindo que a primeira consulta é a desejada. Você pode querer uma lógica de ordenação.
                consultation_id = patient_consultations[0]["id"] 
            else:
                consultation_id = add_consultation_to_patient(patient_id, "Consulta Inicial (Chat)")
                if not consultation_id:
                    raise Exception("Falha ao criar consulta para o paciente.")

        print(f"\nMensagem recebida para Paciente ID {patient_id}, Consulta ID {consultation_id}: {user_message}")

        filtered_user_message = text_filter.remover_nomes(user_message)
        
        # Adiciona a mensagem ao histórico da consulta específica
        add_message_to_consultation_history(patient_id, consultation_id, "user", filtered_user_message if filtered_user_message else user_message)

        # Recuperar o histórico da consulta para enviar ao Gemini
        # A função send_message agora lida com o histórico da consulta
        ai_response_text = gemini_connection.send_message(patient_id, consultation_id, filtered_user_message)
        
        # Adicionar a resposta da IA ao histórico da consulta
        add_message_to_consultation_history(patient_id, consultation_id, "model", ai_response_text)
        
        response_data = {
            "status": "success",
            "ai_response": ai_response_text,
            "consultation_id": consultation_id
        }
        if new_patient_id_generated:
            response_data["patient_id"] = new_patient_id_generated

        return jsonify(response_data), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Erro interno do servidor: {e}"}), 500


# Endpoint de Upload de PDF
@app.route('/api/upload-pdf', methods=['POST'])
def upload_pdf():
    try:
        if 'pdf' not in request.files:
            return jsonify({"status": "error", "message": "Nenhum arquivo enviado."}), 400

        file = request.files['pdf']
        patient_id = request.form.get('patient_id')
        consultation_id = request.form.get('consultation_id') # ID da consulta

        new_patient_id_generated = None

        if not patient_id:
            patient_id = generate_patient_id()
            new_patient_id_generated = patient_id
            ensure_patient_exists(patient_id)
        
        # Assegura que há uma consultation_id
        if not consultation_id:
            patient_consultations = get_patient_consultations(patient_id)
            if patient_consultations:
                consultation_id = patient_consultations[0]["id"]
            else:
                consultation_id = add_consultation_to_patient(patient_id, "Consulta de PDF")
                if not consultation_id:
                    raise Exception("Falha ao criar consulta para o paciente durante upload de PDF.")

        extracted_text = pdf_reader.extract_text_from_pdf(file)
        if not extracted_text.strip():
            return jsonify({"status": "error", "message": "Texto extraído está vazio."}), 400

        filtered_extracted_text = text_filter.remover_nomes(extracted_text)
        
        context_message_for_pdf = f"O seguinte texto foi extraído de um PDF enviado pelo usuário: \"{filtered_extracted_text}\". Por favor, analise-o e responda às perguntas subsequentes ou forneça um resumo, conforme apropriado."
        
        # Adiciona a mensagem ao histórico da consulta
        add_message_to_consultation_history(patient_id, consultation_id, "user", context_message_for_pdf)
        
        # A assinatura correta é send_message(patient_id: str, consultation_id: str, message_text: str)
        ai_response_text = gemini_connection.send_message(patient_id, consultation_id, context_message_for_pdf)
        
        # Adiciona a resposta da IA ao histórico da consulta
        add_message_to_consultation_history(patient_id, consultation_id, "model", ai_response_text)

        response_data = {
            "status": "success",
            "message": "Texto extraído e enviado para a IA com sucesso.",
            "extracted_text_preview": extracted_text[:200] + "...",
            "ai_response": ai_response_text,
            "consultation_id": consultation_id
        }
        if new_patient_id_generated:
            response_data["patient_id"] = new_patient_id_generated
            
        return jsonify(response_data), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Erro interno ao processar o PDF: {e}"}), 500

## Rota `/api/patients/<patient_id>/consultations` para gerenciar consultas
@app.route('/api/patients/<patient_id>/consultations', methods=['GET', 'POST'])
def handle_patient_consultations(patient_id):
    if request.method == 'POST':
        # Lógica para CRIAR uma nova consulta
        try:
            data = request.get_json()
            consultation_title = data.get('title')
            import_consultation_ids = data.get('import_consultation_ids', [])

            if not consultation_title:
                consultation_title = f"Consulta em {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            initial_history = []
            
            if import_consultation_ids and isinstance(import_consultation_ids, list) and len(import_consultation_ids) > 0:
                initial_history.append({
                    "role": "model",
                    "parts": [{"text": f"Históricos importados de consultas anteriores: {', '.join([c_id[:8] + '...' for c_id in import_consultation_ids])}."}],
                    "timestamp": datetime.now().isoformat()
                })

                for old_consultation_id in import_consultation_ids:
                    old_history = get_consultation_chat_history(patient_id, old_consultation_id)
                    if old_history:
                        initial_history.append({
                            "role": "model",
                            "parts": [{"text": f"--- Início do Histórico da Consulta {old_consultation_id[:8]}... ---"}],
                            "timestamp": datetime.now().isoformat()
                        })
                        initial_history.extend(old_history)
                        initial_history.append({
                            "role": "model",
                            "parts": [{"text": f"--- Fim do Histórico da Consulta {old_consultation_id[:8]}... ---"}],
                            "timestamp": datetime.now().isoformat()
                        })
            
            # Chama a função para adicionar a nova consulta com o histórico inicial (se houver)
            new_consultation_id = add_consultation_to_patient(patient_id, consultation_title, initial_history=initial_history)

            if new_consultation_id:
                return jsonify({
                    "status": "success",
                    "message": "Consulta criada com sucesso.",
                    "consultation_id": new_consultation_id,
                    "consultation_title": consultation_title
                }), 201
            else:
                return jsonify({"status": "error", "message": "Falha ao criar nova consulta no banco de dados."}), 500

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"status": "error", "message": f"Erro interno ao criar consulta: {e}"}), 500

    elif request.method == 'GET':
        # Lógica para OBTER a lista de consultas
        try:
            consultations = get_patient_consultations(patient_id)
            return jsonify({"status": "success", "consultations": consultations}), 200
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"status": "error", "message": f"Erro ao recuperar consultas do paciente: {e}"}), 500
        
# NOVO ENDPOINT: Obter Histórico de uma Consulta Específica
@app.route('/api/patients/<patient_id>/consultations/<consultation_id>/history', methods=['GET'])
def get_consultation_history_api(patient_id, consultation_id):
    """
    Retorna o histórico de chat de uma consulta específica.
    """
    try:
        history = get_consultation_chat_history(patient_id, consultation_id)
        if history is not None:
            return jsonify({"status": "success", "history": history}), 200
        else:
            return jsonify({"status": "error", "message": "Histórico da consulta não encontrado."}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Erro ao recuperar histórico da consulta: {e}"}), 500
    
@app.route('/api/all-patients', methods=['GET'])
def get_all_patients():
    """
    Retorna uma lista de todos os pacientes (ID e Nome) para o frontend.
    """
    try:
        patients_info = get_all_patients_info()
        return jsonify({"status": "success", "patients": patients_info}), 200
    except Exception as e:
        import traceback
        traceback.print_exc() 
        return jsonify({"status": "error", "message": f"Erro ao obter lista de pacientes: {e}"}), 500

@app.route('/api/recommendations', methods=['POST'])
def handle_recommendations():
    """
    Endpoint para solicitação de recomendações com base no andamento/histórico da consulta.
    """
    try:

        data = request.get_json()

        # Verifica se o JSON existe
        if not data:
            return jsonify({"error": "Requisição inválida. Corpo JSON esperado."}), 400

        # Verifica se o patient_id e o consultation_id estão presentes no JSON
        patient_id = data.get('patient_id')
        consultation_id = data.get('consultation_id')

        if not patient_id or not consultation_id:
            return jsonify({"error": "paciente_id e consulta_id não encontrados."}), 400

        # Define o caminho para o arquivo do prompt de recomendações
        prompt_file_path = os.path.join(os.path.dirname(__file__), 'recommendations.txt')

        # Verifica se o arquivo existe
        if not os.path.exists(prompt_file_path):
            raise FileNotFoundError(f"Arquivo de prompt não encontrado em: {prompt_file_path}")

        # Lê o conteúdo do arquivo
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            prompt_recomendacao_medica = f.read()

        if not prompt_recomendacao_medica:
            raise ValueError(f"O arquivo de prompt {prompt_file_path} está vazio.")

        print(f"[RECOMENDAÇÃO] Iniciando busca para consulta_id: {consultation_id}")

        # Chama a API Gemini. Ela carrega o histórico (incluindo transcrições) e
        # recebe o prompt de recomendação.
        resposta_ia = gemini_connection.send_message(
            patient_id,
            consultation_id,
            prompt_recomendacao_medica
        )

        # Retornar a recomendação para o frontend
        return jsonify({"status": "success", "recommendation": resposta_ia}), 200

    except Exception as e:
        print(f"Erro catastrófico no endpoint /get_recommendation: {e}")
        return jsonify({"error": f"Erro interno do servidor: {str(e)}"}), 500



if __name__ == '__main__':
    print("Servidor Flask com Gemini e DB de Paciente iniciado.")
    
    # GARANTA que a função add_consultation_to_patient no patient_db.py tem a assinatura:
    # def add_consultation_to_patient(patient_id: str, consultation_title: str = None, consultation_date: str = None, initial_history: list[dict] = None):
    # para que o argumento 'initial_history' seja reconhecido.

    # Garante que o paciente "João Silva" exista
    ensure_patient_exists("paciente_abc", "João Silva")
    
    # --- PRÉ-POPULAÇÃO DE DADOS CORRIGIDA ---
    # Histórico para a primeira consulta pré-populada
    history_consulta_1 = [
        {
            "role": "user",
            "parts": [
                {
                    "text": "Paciente relatou dor de cabeça severa há 2 dias."
                }
            ],
            "timestamp": datetime.now().isoformat()
        },
        {
            "role": "model",
            "parts": [
                {
                    "text": "Qual a intensidade da dor em uma escala de 0 a 10?"
                }
            ],
            "timestamp": datetime.now().isoformat()
        },
        {
            "role": "user",
            "parts": [
                {
                    "text": "Nível 8, latejante."
                }
            ],
            "timestamp": datetime.now().isoformat()
        }
    ]
    
    # Cria a primeira consulta já com o histórico completo
    id_consulta_1 = add_consultation_to_patient(
        "paciente_abc", 
        "Consulta Antiga 1 (Dor de Cabeça)", 
        initial_history=history_consulta_1 # Passando o histórico inicial aqui
    )

    # Histórico para a segunda consulta pré-populada
    history_consulta_2 = [
        {
            "role": "user",
            "parts": [
                {
                    "text": "Febre de 39°C e tosse seca persistente."
                }
            ],
            "timestamp": datetime.now().isoformat()
        },
        {
            "role": "model",
            "parts": [
                {
                    "text": "Há quanto tempo os sintomas estão presentes?"
                }
            ],
            "timestamp": datetime.now().isoformat()
        }
    ]

    # Cria a segunda consulta já com o histórico completo
    id_consulta_2 = add_consultation_to_patient(
        "paciente_abc", 
        "Consulta Antiga 2 (Febre)", 
        initial_history=history_consulta_2 # Passando o histórico inicial aqui
    )
    # --- FIM DA PRÉ-POPULAÇÃO DE DADOS CORRIGIDA ---

    app.run(host='0.0.0.0', port=3001, debug=True)
