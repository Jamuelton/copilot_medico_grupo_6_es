import pytest
import json
from unittest.mock import patch, MagicMock


class TestChatEndpoint:
    """Testes para a rota /api/chat"""

    def test_chat_success_with_existing_patient_and_consultation(self, client):
        """Testa chat bem-sucedido com patient_id e consultation_id existentes"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            # Configurar mocks
            mock_filter.return_value = "Mensagem filtrada do usuário"
            mock_gemini.return_value = "Resposta da IA para a mensagem"
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123", "title": "Consulta Teste"}]

            # Dados da requisição
            data = {
                'message': 'Olá, tenho dor de cabeça',
                'patient_id': 'patient_123',
                'consultation_id': 'consulta_123'
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            # Verificações
            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['status'] == 'success'
            assert json_data['ai_response'] == 'Resposta da IA para a mensagem'
            assert json_data['consultation_id'] == 'consulta_123'
            assert 'patient_id' not in json_data  # Não deve gerar novo patient_id

            # Verificar se as funções foram chamadas corretamente
            mock_filter.assert_called_once_with('Olá, tenho dor de cabeça')
            mock_gemini.assert_called_once()
            mock_ensure_patient.assert_not_called()  # Patient já existe

    def test_chat_success_new_patient_auto_generated(self, client):
        """Testa chat criando novo paciente automaticamente"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.generate_patient_id') as mock_generate_id, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_consultation_to_patient') as mock_add_consultation, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            # Configurar mocks
            mock_filter.return_value = "Mensagem filtrada"
            mock_gemini.return_value = "Resposta da IA"
            mock_generate_id.return_value = 'new_patient_456'
            mock_get_consultations.return_value = []  # Nenhuma consulta existente
            mock_add_consultation.return_value = 'new_consultation_789'
            mock_ensure_patient.return_value = {"name": "Novo Paciente"}

            # Dados da requisição sem patient_id
            data = {
                'message': 'Preciso de ajuda médica'
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            # Verificações
            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['status'] == 'success'
            assert json_data['patient_id'] == 'new_patient_456'
            assert json_data['consultation_id'] == 'new_consultation_789'

            # Verificar se o paciente foi criado
            mock_generate_id.assert_called_once()
            mock_ensure_patient.assert_called_once_with('new_patient_456', name="Desconhecido")
            mock_add_consultation.assert_called_once()

    def test_chat_no_message_provided(self, client):
        """Testa requisição sem mensagem"""
        data = {
            'patient_id': 'patient_123'
            # message omitido
        }

        response = client.post(
            '/api/chat',
            json=data,
            content_type='application/json'
        )

        assert response.status_code == 400
        json_data = response.get_json()
        assert json_data['status'] == 'error'
        assert 'Requisição inválida' in json_data['message']

    def test_chat_empty_message(self, client):
        """Testa requisição com mensagem vazia"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            mock_filter.return_value = ""  # Mensagem vazia filtrada
            mock_gemini.return_value = "Resposta para mensagem vazia"
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123"}]

            data = {
                'message': '',
                'patient_id': 'patient_123'
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            # Seu código atual permite mensagens vazias, então espera 200
            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['status'] == 'success'

    def test_chat_no_json_data(self, client):
        """Testa requisição sem dados JSON válidos"""
        # Enviar dados inválidos (não JSON)
        response = client.post(
            '/api/chat',
            data="invalid data",  # Dados não JSON
            content_type='text/plain'  # Content-type errado
        )

        # O Flask geralmente retorna 400 para JSON inválido
        # Mas pode retornar 500 se causar exceção
        assert response.status_code in [400, 500, 415]

        # Se retornar JSON, verificar estrutura
        if response.content_type == 'application/json':
            json_data = response.get_json()
            assert 'status' in json_data

    def test_chat_gemini_exception(self, client):
        """Testa exceção durante comunicação com Gemini"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            mock_filter.return_value = "Mensagem filtrada"
            mock_gemini.side_effect = Exception("Erro de conexão com API Gemini")
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123"}]

            data = {
                'message': 'Mensagem de teste',
                'patient_id': 'patient_123',
                'consultation_id': 'consulta_123'
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            assert response.status_code == 500
            json_data = response.get_json()
            assert json_data['status'] == 'error'
            assert 'Erro interno do servidor' in json_data['message']

    def test_chat_consultation_creation_failure(self, client):
        """Testa falha na criação de consulta para novo paciente"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.generate_patient_id') as mock_generate_id, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_consultation_to_patient') as mock_add_consultation:
            mock_filter.return_value = "Mensagem filtrada"
            mock_generate_id.return_value = 'new_patient_456'
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = []  # Nenhuma consulta existente
            mock_add_consultation.return_value = None  # Falha na criação

            data = {
                'message': 'Mensagem de teste'
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            assert response.status_code == 500
            json_data = response.get_json()
            assert json_data['status'] == 'error'

    def test_chat_text_filter_applied(self, client):
        """Testa se o filtro de nomes é aplicado corretamente"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            # Mensagem com nome que deve ser filtrado
            original_message = "Meu nome é João Silva e tenho dor de cabeça"
            filtered_message = "Meu nome é [NOME_REMOVIDO] e tenho dor de cabeça"

            mock_filter.return_value = filtered_message
            mock_gemini.return_value = "Resposta da IA"
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123"}]

            data = {
                'message': original_message,
                'patient_id': 'patient_123',
                'consultation_id': 'consulta_123'
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            assert response.status_code == 200
            # Verificar se o filtro foi chamado com a mensagem correta
            mock_filter.assert_called_once_with(original_message)
            # Verificar se o Gemini recebeu a mensagem filtrada
            call_args = mock_gemini.call_args[0]
            assert call_args[2] == filtered_message  # message_text parameter

    def test_chat_with_only_patient_id_no_consultation(self, client):
        """Testa chat com patient_id mas sem consultation_id"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            mock_filter.return_value = "Mensagem filtrada"
            mock_gemini.return_value = "Resposta IA"
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "primeira_consulta"}]

            data = {
                'message': 'Mensagem de teste',
                'patient_id': 'patient_123'
                # consultation_id omitido
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['status'] == 'success'
            assert json_data['consultation_id'] == 'primeira_consulta'

    def test_chat_history_updated_correctly(self, client):
        """Testa se o histórico da consulta é atualizado corretamente"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            mock_filter.return_value = "Mensagem filtrada do usuário"
            mock_gemini.return_value = "Resposta da IA para o usuário"
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123"}]

            data = {
                'message': 'Mensagem original do usuário',
                'patient_id': 'patient_123',
                'consultation_id': 'consulta_123'
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            # Verificar se o histórico foi atualizado duas vezes (usuário e modelo)
            assert mock_add_history.call_count == 2

            # Primeira chamada: mensagem do usuário filtrada
            first_call = mock_add_history.call_args_list[0]
            assert first_call[0][0] == 'patient_123'  # patient_id
            assert first_call[0][1] == 'consulta_123'  # consultation_id
            assert first_call[0][2] == 'user'  # role
            assert first_call[0][3] == 'Mensagem filtrada do usuário'  # message filtrada

            # Segunda chamada: resposta do modelo
            second_call = mock_add_history.call_args_list[1]
            assert second_call[0][0] == 'patient_123'  # patient_id
            assert second_call[0][1] == 'consulta_123'  # consultation_id
            assert second_call[0][2] == 'model'  # role
            assert second_call[0][3] == 'Resposta da IA para o usuário'  # message

    def test_chat_filter_returns_none_uses_original_message(self, client):
        """Testa quando o filtro retorna None e usa mensagem original"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            mock_filter.return_value = None  # Filtro retorna None
            mock_gemini.return_value = "Resposta da IA"
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123"}]

            original_message = "Mensagem original sem nomes"

            data = {
                'message': original_message,
                'patient_id': 'patient_123',
                'consultation_id': 'consulta_123'
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            assert response.status_code == 200
            # Verificar que a mensagem original foi usada quando filtro retornou None
            first_call = mock_add_history.call_args_list[0]
            assert first_call[0][3] == original_message  # Mensagem original

    def test_chat_with_existing_patient_but_no_consultations(self, client):
        """Testa chat com paciente existente mas sem consultas"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_consultation_to_patient') as mock_add_consultation, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            mock_filter.return_value = "Mensagem filtrada"
            mock_gemini.return_value = "Resposta da IA"
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = []  # Nenhuma consulta existente
            mock_add_consultation.return_value = 'nova_consulta_456'

            data = {
                'message': 'Mensagem de teste',
                'patient_id': 'patient_123'
                # consultation_id omitido
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['status'] == 'success'
            assert json_data['consultation_id'] == 'nova_consulta_456'

            # Verificar que uma nova consulta foi criada
            mock_add_consultation.assert_called_once()

    def test_chat_message_content_preserved(self, client):
        """Testa se o conteúdo da mensagem é preservado corretamente"""
        with patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            medical_message = "Estou com febre de 38°C, tosse seca e dor no corpo há 3 dias"
            mock_filter.return_value = medical_message  # Nada para filtrar
            mock_gemini.return_value = "Recomendo repouso e hidratação"
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123"}]

            data = {
                'message': medical_message,
                'patient_id': 'patient_123',
                'consultation_id': 'consulta_123'
            }

            response = client.post(
                '/api/chat',
                json=data,
                content_type='application/json'
            )

            assert response.status_code == 200
            # Verificar se a mensagem médica foi preservada
            mock_gemini.assert_called_once_with('patient_123', 'consulta_123', medical_message)