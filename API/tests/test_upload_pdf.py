import pytest
import io
from unittest.mock import patch, MagicMock


class TestUploadPDF:
    """Testes para a rota /api/upload-pdf"""

    def test_upload_pdf_success_with_existing_patient_and_consultation(self, client, sample_pdf_file):
        """Testa upload de PDF bem-sucedido com patient_id e consultation_id existentes"""
        with patch('server.pdf_reader.extract_text_from_pdf') as mock_extract, \
                patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            # Configurar mocks
            mock_extract.return_value = "Texto extraído do PDF com conteúdo médico relevante."
            mock_filter.return_value = "Texto filtrado do PDF com conteúdo médico relevante."
            mock_gemini.return_value = "Análise do PDF: Documento médico processado com sucesso."
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123", "title": "Consulta Teste"}]

            # Fazer requisição
            data = {
                'pdf': sample_pdf_file,
                'patient_id': 'patient_123',
                'consultation_id': 'consulta_123'
            }

            response = client.post(
                '/api/upload-pdf',
                data=data,
                content_type='multipart/form-data'
            )

            # Verificações
            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['status'] == 'success'
            assert json_data['message'] == 'Texto extraído e enviado para a IA com sucesso.'
            assert 'extracted_text_preview' in json_data
            assert 'Texto extraído do PDF' in json_data['extracted_text_preview']
            assert json_data['ai_response'] == 'Análise do PDF: Documento médico processado com sucesso.'
            assert json_data['consultation_id'] == 'consulta_123'
            assert 'patient_id' not in json_data  # Não deve gerar novo patient_id

            # Verificar se as funções foram chamadas corretamente
            mock_extract.assert_called_once()
            mock_filter.assert_called_once_with("Texto extraído do PDF com conteúdo médico relevante.")
            mock_gemini.assert_called_once()
            mock_ensure_patient.assert_not_called()  # Patient já existe

    def test_upload_pdf_success_new_patient_auto_generated(self, client, sample_pdf_file):
        """Testa upload de PDF criando novo paciente automaticamente"""
        with patch('server.pdf_reader.extract_text_from_pdf') as mock_extract, \
                patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.generate_patient_id') as mock_generate_id, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_consultation_to_patient') as mock_add_consultation, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            # Configurar mocks
            mock_extract.return_value = "Texto extraído do PDF"
            mock_filter.return_value = "Texto filtrado do PDF"
            mock_gemini.return_value = "Resposta da IA"
            mock_generate_id.return_value = 'new_patient_456'
            mock_get_consultations.return_value = []  # Nenhuma consulta existente
            mock_add_consultation.return_value = 'new_consultation_789'
            mock_ensure_patient.return_value = {"name": "Novo Paciente"}

            # Fazer requisição sem patient_id
            data = {'pdf': sample_pdf_file}

            response = client.post(
                '/api/upload-pdf',
                data=data,
                content_type='multipart/form-data'
            )

            # Verificações
            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['status'] == 'success'
            assert json_data['patient_id'] == 'new_patient_456'
            assert json_data['consultation_id'] == 'new_consultation_789'

            # Verificar se o paciente foi criado
            mock_generate_id.assert_called_once()
            mock_ensure_patient.assert_called_once_with('new_patient_456')
            mock_add_consultation.assert_called_once()

    def test_upload_pdf_no_file_provided(self, client):
        """Testa requisição sem arquivo PDF"""
        response = client.post('/api/upload-pdf')

        assert response.status_code == 400
        json_data = response.get_json()
        assert json_data['status'] == 'error'
        assert 'Nenhum arquivo enviado' in json_data['message']

    def test_upload_pdf_empty_extracted_text(self, client, sample_pdf_file):
        """Testa upload de PDF com texto extraído vazio"""
        with patch('server.pdf_reader.extract_text_from_pdf') as mock_extract, \
                patch('server.ensure_patient_exists') as mock_ensure_patient:
            mock_extract.return_value = "   "  # Texto vazio
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}

            data = {
                'pdf': sample_pdf_file,
                'patient_id': 'patient_123'
            }

            response = client.post(
                '/api/upload-pdf',
                data=data,
                content_type='multipart/form-data'
            )

            assert response.status_code == 400
            json_data = response.get_json()
            assert json_data['status'] == 'error'
            assert 'Texto extraído está vazio' in json_data['message']

    def test_upload_pdf_pdf_reader_exception(self, client, sample_pdf_file):
        """Testa exceção durante extração de texto do PDF"""
        with patch('server.pdf_reader.extract_text_from_pdf') as mock_extract, \
                patch('server.ensure_patient_exists') as mock_ensure_patient:
            mock_extract.side_effect = Exception("Erro na leitura do PDF - arquivo corrompido")
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}

            data = {
                'pdf': sample_pdf_file,
                'patient_id': 'patient_123'
            }

            response = client.post(
                '/api/upload-pdf',
                data=data,
                content_type='multipart/form-data'
            )

            assert response.status_code == 500
            json_data = response.get_json()
            assert json_data['status'] == 'error'
            assert 'Erro interno ao processar o PDF' in json_data['message']

    def test_upload_pdf_gemini_exception(self, client, sample_pdf_file):
        """Testa exceção durante comunicação com Gemini"""
        with patch('server.pdf_reader.extract_text_from_pdf') as mock_extract, \
                patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            mock_extract.return_value = "Texto extraído do PDF"
            mock_filter.return_value = "Texto filtrado do PDF"
            mock_gemini.side_effect = Exception("Erro de conexão com API Gemini")
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123"}]

            data = {
                'pdf': sample_pdf_file,
                'patient_id': 'patient_123'
            }

            response = client.post(
                '/api/upload-pdf',
                data=data,
                content_type='multipart/form-data'
            )

            assert response.status_code == 500
            json_data = response.get_json()
            assert json_data['status'] == 'error'
            assert 'Erro interno ao processar o PDF' in json_data['message']

    def test_upload_pdf_consultation_creation_failure(self, client, sample_pdf_file):
        """Testa falha na criação de consulta para novo paciente"""
        with patch('server.pdf_reader.extract_text_from_pdf') as mock_extract, \
                patch('server.generate_patient_id') as mock_generate_id, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_consultation_to_patient') as mock_add_consultation:
            mock_extract.return_value = "Texto extraído do PDF"
            mock_generate_id.return_value = 'new_patient_456'
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = []  # Nenhuma consulta existente
            mock_add_consultation.return_value = None  # Falha na criação

            data = {'pdf': sample_pdf_file}

            response = client.post(
                '/api/upload-pdf',
                data=data,
                content_type='multipart/form-data'
            )

            assert response.status_code == 500
            json_data = response.get_json()
            assert json_data['status'] == 'error'

    def test_upload_pdf_text_filter_applied(self, client, sample_pdf_file):
        """Testa se o filtro de nomes é aplicado corretamente"""
        with patch('server.pdf_reader.extract_text_from_pdf') as mock_extract, \
                patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            # Texto com nome que deve ser filtrado
            original_text = "Paciente João Silva apresenta sintomas de gripe."
            filtered_text = "Paciente [NOME_REMOVIDO] apresenta sintomas de gripe."

            mock_extract.return_value = original_text
            mock_filter.return_value = filtered_text
            mock_gemini.return_value = "Análise realizada com sucesso."
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123"}]

            data = {
                'pdf': sample_pdf_file,
                'patient_id': 'patient_123',
                'consultation_id': 'consulta_123'
            }

            response = client.post(
                '/api/upload-pdf',
                data=data,
                content_type='multipart/form-data'
            )

            assert response.status_code == 200
            # Verificar se o filtro foi chamado com o texto correto
            mock_filter.assert_called_once_with(original_text)
            # Verificar se o Gemini recebeu o texto filtrado
            call_args = mock_gemini.call_args[0]
            assert filtered_text in call_args[2]  # message_text parameter

    def test_upload_pdf_with_only_patient_id_no_consultation(self, client, sample_pdf_file):
        """Testa upload com patient_id mas sem consultation_id"""
        with patch('server.pdf_reader.extract_text_from_pdf') as mock_extract, \
                patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            mock_extract.return_value = "Texto do PDF"
            mock_filter.return_value = "Texto filtrado"
            mock_gemini.return_value = "Resposta IA"
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "primeira_consulta"}]

            data = {
                'pdf': sample_pdf_file,
                'patient_id': 'patient_123'
                # consultation_id omitido
            }

            response = client.post(
                '/api/upload-pdf',
                data=data,
                content_type='multipart/form-data'
            )

            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['status'] == 'success'
            assert json_data['consultation_id'] == 'primeira_consulta'

    def test_upload_pdf_context_message_format(self, client, sample_pdf_file):
        """Testa se a mensagem de contexto para o Gemini está formatada corretamente"""
        with patch('server.pdf_reader.extract_text_from_pdf') as mock_extract, \
                patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            extracted_text = "Relatório médico completo do paciente."
            filtered_text = "Relatório médico completo do paciente."

            mock_extract.return_value = extracted_text
            mock_filter.return_value = filtered_text
            mock_gemini.return_value = "Análise realizada."
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123"}]

            data = {
                'pdf': sample_pdf_file,
                'patient_id': 'patient_123',
                'consultation_id': 'consulta_123'
            }

            response = client.post(
                '/api/upload-pdf',
                data=data,
                content_type='multipart/form-data'
            )

            # Verificar se a mensagem para o Gemini contém o texto extraído
            expected_context_message = f'O seguinte texto foi extraído de um PDF enviado pelo usuário: "{filtered_text}". Por favor, analise-o e responda às perguntas subsequentes ou forneça um resumo, conforme apropriado.'

            mock_gemini.assert_called_once()
            call_args = mock_gemini.call_args[0]
            assert call_args[2] == expected_context_message  # message_text parameter

    def test_upload_pdf_history_updated_correctly(self, client, sample_pdf_file):
        """Testa se o histórico da consulta é atualizado corretamente"""
        with patch('server.pdf_reader.extract_text_from_pdf') as mock_extract, \
                patch('server.text_filter.remover_nomes') as mock_filter, \
                patch('server.gemini_connection.send_message') as mock_gemini, \
                patch('server.ensure_patient_exists') as mock_ensure_patient, \
                patch('server.get_patient_consultations') as mock_get_consultations, \
                patch('server.add_message_to_consultation_history') as mock_add_history:
            mock_extract.return_value = "Texto do PDF"
            mock_filter.return_value = "Texto filtrado"
            mock_gemini.return_value = "Resposta da IA"
            mock_ensure_patient.return_value = {"name": "Paciente Teste"}
            mock_get_consultations.return_value = [{"id": "consulta_123"}]

            data = {
                'pdf': sample_pdf_file,
                'patient_id': 'patient_123',
                'consultation_id': 'consulta_123'
            }

            response = client.post(
                '/api/upload-pdf',
                data=data,
                content_type='multipart/form-data'
            )

            # Verificar se o histórico foi atualizado duas vezes (usuário e modelo)
            assert mock_add_history.call_count == 2

            # Primeira chamada: mensagem do usuário com contexto do PDF
            first_call = mock_add_history.call_args_list[0]
            assert first_call[0][0] == 'patient_123'  # patient_id
            assert first_call[0][1] == 'consulta_123'  # consultation_id
            assert first_call[0][2] == 'user'  # role
            assert 'PDF' in first_call[0][3]  # message (contém "PDF" na mensagem)

            # Segunda chamada: resposta do modelo
            second_call = mock_add_history.call_args_list[1]
            assert second_call[0][0] == 'patient_123'  # patient_id
            assert second_call[0][1] == 'consulta_123'  # consultation_id
            assert second_call[0][2] == 'model'  # role
            assert second_call[0][3] == 'Resposta da IA'  # message