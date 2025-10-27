import pytest
import sys
import os
from unittest.mock import Mock, patch

# Adiciona o diretório raiz ao path para imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from server import app


@pytest.fixture
def client():
    """Fixture para criar cliente de teste Flask"""
    app.config['TESTING'] = True
    app.config['DEBUG'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_pdf_file():
    """Fixture para criar um arquivo PDF simulado"""
    import io
    # PDF válido simulado (cabeçalho PDF + conteúdo)
    pdf_content = b"%PDF-1.4\n%fake pdf content for testing\n1 0 obj\n<<>>\nendobj\n"
    return (io.BytesIO(pdf_content), 'test_document.pdf')


@pytest.fixture
def sample_chat_data():
    """Fixture com dados de exemplo para chat"""
    return {
        'message': 'Olá, preciso de ajuda médica',
        'patient_id': 'patient_123',
        'consultation_id': 'consulta_123'
    }


@pytest.fixture(autouse=True)
def mock_external_dependencies():
    """
    Mock automático para dependências externas que não devem ser chamadas durante testes.
    """
    # Mock para funções do patient_db
    with patch('server.generate_patient_id') as mock_generate_id, \
            patch('server.ensure_patient_exists') as mock_ensure_patient, \
            patch('server.get_patient_consultations') as mock_get_consultations, \
            patch('server.add_consultation_to_patient') as mock_add_consultation, \
            patch('server.add_message_to_consultation_history') as mock_add_history, \
            patch('server.text_filter.remover_nomes') as mock_filter, \
            patch('server.gemini_connection.send_message') as mock_gemini:
        # Configurações padrão dos mocks
        mock_generate_id.return_value = 'mock_patient_id'
        mock_ensure_patient.return_value = {"name": "Mock Patient"}
        mock_get_consultations.return_value = [{"id": "mock_consultation_id", "title": "Mock Consultation"}]
        mock_add_consultation.return_value = 'new_consultation_id'
        mock_filter.return_value = "Mock filtered message"
        mock_gemini.return_value = "Mock AI response"

        yield