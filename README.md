# Co-pilot Médico

**Co-pilot Médico**

## Arquitetura integrada planejada

Este repositório é o repositório oficial de trabalho do Copilot Médico. A integração planejada deve manter a extensão Chrome existente e adicionar, em uma etapa futura, a aplicação web React ao mesmo repositório, usando um backend Flask compartilhado.

Estrutura alvo:

```textS
copilot_medico_grupo_2_es/
├── API/
│   └── backend Flask compartilhado
├── front/
│   ├── copmed-extension/
│   │   └── extensão Chrome existente
│   └── copmed-web/
│       └── futura aplicação web React
├── docker-compose.yml
└── README.md
```

Separação dos módulos:

- `API/`: backend Flask compartilhado. Deve concentrar as rotas e serviços usados tanto pela extensão Chrome quanto pela futura aplicação web.
- `front/copmed-extension/`: frontend da extensão Chrome atual. Esta estrutura deve ser preservada durante a integração.
- `front/copmed-web/`: local planejado para a aplicação web React. Esta pasta ainda não foi criada nesta etapa.
- `docker-compose.yml`: orquestração local do projeto. Atualmente contempla backend e extensão; poderá receber o serviço web quando a aplicação React for integrada.

A extensão Chrome e a futura aplicação web devem consumir o mesmo backend em `API/`, evitando duplicação de regras de negócio e mantendo um ponto único para integrações com IA, dados de pacientes, processamento de PDFs e áudio.

### Repositório de referência

O repositório `italobaracho/copilot-medico-atualizado` foi analisado apenas como referência. Ele possui uma aplicação web React/Vite no nível raiz, além de melhorias de backend em `API/`.

Partes que podem ser avaliadas para reaproveitamento futuro:

- frontend web React/Vite: `src/`, `public/`, `package.json`, `vite.config.js` e componentes como telas de login, home, pacientes, atendimentos, análise de IA e agendamentos;
- camada de comunicação web com a API: arquivo `src/api.js`;
- estilos, tema e assets da interface web: `src/App.css`, `src/index.css`, `src/theme.js` e `src/assets/`;
- melhorias de backend a serem comparadas com cuidado antes de qualquer merge: autenticação, agendamentos, dependências extras e ajustes de `docker-compose.yml`.

Nenhum arquivo do repositório de referência foi copiado nesta etapa. A integração funcional, a criação da aplicação web dentro de `front/copmed-web/`, alterações no backend e ajustes na extensão devem ser tratados em tasks futuras.

## Requisitos

### Backend

- **Tecnologias**:
  - Python (3.11.2)
  - Flask (3.0.3)
  - API Gemini
  - spaCy
  - PyPDF2
  - SpeachRecognition
  - Vosk

### Frontend

- **Tecnologias**:
  - JavaScript (v18.12.1)
  - Extensão Chrome ("manifest_version" : 3)
  - Node
  - React

### Funcionalidades
  - Acesso a dados do prontuário eletrônico da Amplimed em tempo real
  - Upload de PDFs referentes a exames, medicações e casos do paciente
  - Assistente de IA: É possível fazer perguntas à inteligência artificial e enviar arquivos com poucos cliques
  - Histórico de interações: A aplicação salva o histórico de interações por paciente, que pode ser consultado posteriormente
  - Anonimato: a IA filtra os dados removendo o nome do paciente
  - Extrai as informações mais importantes dos exames
  - Faz a transcrição de áudios gravados
  - Faz a diarização através de uma lógica ping-pong, onde a primeira pessoa que falar é definida como médico e a outra pessoa que falar será o paciente
  - Armazena as transcrições em um log de transcrições para cada paciente

#### Backend

1. Navegue até o diretório `API`
```bash
cd API
```
2. Instale as bibliotecas necessárias através do requirements.txt
```bash
pip install requirements.txt
```

3. Gere uma chave API do gemini no site e criar uma nova váriavel de usuário com o nome ( GEMINI_API_KEY) e coloque-a a key no Valor da variável.

#### Frontend

1. Navegue para o diretório `front/copmed-extension`:

   ```bash
   cd front/copmed-extension
   ```

2. Instale as dependências do Node.js:

   ```bash
   npm install
   ```

3. Compile o código para gerar a extensão:

   ```bash
   npm run build
   ```

4. Após a compilação, utilize a pasta `dist` como a extensão para o Chrome.

---

## Usando a Extensão no Chrome

### Passo a Passo para Carregar a Extensão no Modo Desenvolvedor

1. Abra o Chrome e acesse a página de extensões:

   - No navegador, clique em **Menu (três pontos no canto superior direito) > Mais ferramentas > Extensões**, ou simplesmente acesse `chrome://extensions` na barra de endereço.

2. Ative o **Modo Desenvolvedor**:

   - Na parte superior direita da página de extensões, ative o botão de **Modo desenvolvedor**.

3. Carregue a extensão:

   - Clique no botão **Carregar sem compactação** (ou **Load unpacked**).
   - Navegue até o diretório `dist` gerado no passo anterior e selecione-o.

4. Inicie o servidor:
   No diretório API:

   Instalar Flask-Cors antes de iniciar o SERVER.PY

   ```bash
   pip install Flask-Cors
   ```

   ```bash
   python server.py
   ```

5. Teste a extensão:
   - A extensão deve aparecer na sua barra de ferramentas. Clique nela para começar a usar!

## Usando a funcionalidade de áudio
### passo a passo para utilizar a funcionalidade de áudio
1. Abra a extensão na barra de tarefas:
   - Na barra de tarefas clique no ícone de extensões, ao ver a extensão do copilot clique em Mais opções (três pontos ao lado da extensão) e acesse *conferir permissões da web*
2. Ative o microfone:
   - Na permissão de microfone altere de Perguntar(padrão) para Permitir
3. Teste a funcionalidade de áudio:
   - Agora quando você iniciar uma nova consulta, você poderá utilizar a extensão poderá acessar seu microfone e gravar o áudio ao abrir uma nova consulta
4. Modo Teste Sozinho:
   - Caso você queira testar a diarização da transcrição de áudio sozinho vá para o arquivo `audio_service.py` e lá faça a seguinte mudança:
   ```python
   MODO_TESTE_SOZINHO = True
   ```
5. Testar com mais de uma pessoa:
   - Caso queira testar a diarização da transcrição de áudio com mais de uma pessoa basta ir em `audio_service.py` e fazer a seguinte mudança:
   ```python
   MODO_TESTE_SOZINHO = False
   ```
# Executando com Docker

1. Crie .env com GEMINI_API_KEY.
2. Na raiz do projeto:
   docker-compose up --build
3. Backend disponível em http://localhost:3001


---
