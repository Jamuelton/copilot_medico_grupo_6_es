import {
  useState,
  useEffect,
  useCallback,
  useRef,
  Key,
  ReactNode,
} from "react";
import "./App.css";
import Chat from "./modules/Chat/chat";
import {
  executeArbitraryScriptOnActiveTab,
  executeScriptOnActiveTab,
} from "./utils/utils";
import {
  FirstAidIcon,
  UserCirclePlusIcon,
} from "@phosphor-icons/react";

const SERVER_URL = "http://localhost:3001";

const storage = {
  get: (keys: string[], callback: (result: any) => void) => {
    if (typeof chrome !== "undefined" && chrome.storage?.local) {
      chrome.storage.local.get(keys, callback);
    } else {
      const result: any = {};
      keys.forEach((key) => {
        result[key] = localStorage.getItem(key);
      });
      callback(result);
    }
  },

  set: (items: Record<string, any>, callback?: () => void) => {
    if (typeof chrome !== "undefined" && chrome.storage?.local) {
      chrome.storage.local.set(items, callback);
    } else {
      Object.entries(items).forEach(([key, value]) => {
        localStorage.setItem(key, String(value ?? ""));
      });
      if (callback) callback();
    }
  },
};

// --- Tipos ---
type Message = {
  id: Key;
  text: ReactNode;
  sender: "user" | "bot";
  timestamp: string;
};

type PatientListItem = {
  id: string;
  name: string;
};

type ConsultationListItem = {
  id: string;
  title: string;
  date: string;
};

// --- Componente Principal App ---
function App() {
  const [patientId, setPatientId] = useState<string | null>(null);
  const [patientName, setPatientName] = useState<string | null>(null);
  const [consultationId, setConsultationId] = useState<string | null>(null);
  const [_, setConsultationTitle] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [allPatients, setAllPatients] = useState<PatientListItem[]>([]);
  const [showNewPatientModal, setShowNewPatientModal] = useState(false);
  const [newPatientName, setNewPatientName] = useState("");
  const [debugMode, setDebugMode] = useState(false);
  const [selectorInput, setSelectorInput] = useState("");
  const [selectorResult, setSelectorResult] = useState("");

  const [patientConsultations, setPatientConsultations] = useState<
    ConsultationListItem[]
  >([]);
  const [selectedConsultationIdsToImport, setSelectedConsultationIdsToImport] =
    useState<string[]>([]);
  const [showImportHistoryModal, setShowImportHistoryModal] = useState(false);

  // --- Estados para controle de gravação ---
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [isPaused, setIsPaused] = useState<boolean>(false);
  const [showRecordingHistory, setShowRecordingHistory] = useState<boolean>(false);
  const [hasRecordedAudio, setHasRecordedAudio] = useState<boolean>(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioBlobRef = useRef<Blob | null>(null);
  const recordingStartTimeRef = useRef<number>(0);
  const recordingDurationRef = useRef<number>(0);
  const [transcriptionLog, setTranscriptionLog] = useState<any[]>([]); // Histórico separado
  const [elapsedTime, setElapsedTime] = useState<number>(0); // Cronômetro visual
  const [viewingLog, setViewingLog] = useState<any | null>(null); // Armazena o log que está sendo lido

  // --- Funções de Carregamento e Persistência ---


  const loadPatientDataFromStorage = useCallback(() => {
    if (
    typeof chrome !== "undefined" &&
    chrome.storage &&
    chrome.storage.local
  ) {
    storage.get(
      ["patientId", "patientName", "consultationId", "consultationTitle"],
      (result) => {
        if (result.patientId) {
          setPatientId(result.patientId);
          setPatientName(result.patientName || null);
          setConsultationId(result.consultationId || null);
          setConsultationTitle(result.consultationTitle || null);
        }
      }
    );
  } else {
    const savedPatientId = localStorage.getItem("patientId");
    const savedPatientName = localStorage.getItem("patientName");
    const savedConsultationId = localStorage.getItem("consultationId");
    const savedConsultationTitle = localStorage.getItem("consultationTitle");

    if (savedPatientId) {
      setPatientId(savedPatientId);
      setPatientName(savedPatientName);
      setConsultationId(savedConsultationId);
      setConsultationTitle(savedConsultationTitle);
    }
  }
}, []);
  


  const loadConsultationHistory = useCallback(
    async (pId: string, cId: string) => {
      setIsLoading(true);
      try {
        const response = await fetch(
          `${SERVER_URL}/api/patients/${pId}/consultations/${cId}/history`
        );
        const data = await response.json();
        if (data.status === "success") {
          const loadedMessages: Message[] = data.history.map(
            (msg: any, index: number) => ({
              id: `${msg.timestamp}-${index}-${Math.random()}`,
              text: msg.parts && msg.parts.length > 0 ? msg.parts[0].text : "",
              sender: msg.role === "user" ? "user" : "bot",
              timestamp: msg.timestamp,
            })
          );
          setMessages(loadedMessages);
        } else {
          console.error(
            "Erro ao carregar histórico da consulta:",
            data.message
          );
          setMessages([
            {
              id: Date.now(),
              text: `Erro ao carregar histórico: ${data.message}`,
              sender: "bot",
              timestamp: new Date().toISOString(),
            },
          ]);
        }
      } catch (error: any) {
        console.error("Erro de rede ao carregar histórico:", error);
        setMessages([
          {
            id: Date.now(),
            text: `Erro de rede ao carregar histórico: ${error.message}`,
            sender: "bot",
            timestamp: new Date().toISOString(),
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const fetchAllPatients = useCallback(async () => {
    try {
      const response = await fetch(`${SERVER_URL}/api/all-patients`);
      const data = await response.json();
      if (data.status === "success") {
        setAllPatients(data.patients);
      } else {
        console.error("Erro ao buscar todos os pacientes:", data.message);
      }
    } catch (error) {
      console.error("Erro de rede ao buscar todos os pacientes:", error);
    }
  }, []);

  const fetchPatientConsultations = useCallback(async (pId: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `${SERVER_URL}/api/patients/${pId}/consultations`
      );
      const data = await response.json();
      if (data.status === "success") {
        const sortedConsultations = data.consultations.sort(
          (a: ConsultationListItem, b: ConsultationListItem) =>
            new Date(b.date).getTime() - new Date(a.date).getTime()
        );
        setPatientConsultations(sortedConsultations);
      } else {
        console.error("Erro ao carregar consultas:", data.message);
        setPatientConsultations([
          {
            id: Date.now().toString(),
            title: `Erro ao carregar consultas: ${data.message}`,
            date: new Date().toISOString(),
          },
        ]);
      }
    } catch (error: any) {
      console.error("Erro na requisição de consultas:", error);
      setPatientConsultations([
        {
          id: Date.now().toString(),
          title: `Erro de rede ao carregar consultas: ${error.message}`,
          date: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Carrega dados do paciente e todas as listas de pacientes na inicialização
  useEffect(() => {
    loadPatientDataFromStorage();
    fetchAllPatients();
  }, [loadPatientDataFromStorage, fetchAllPatients]);

  // Carrega o histórico da consulta quando patientId ou consultationId mudam
  useEffect(() => {
    if (patientId && consultationId) {
      loadConsultationHistory(patientId, consultationId);
    } else {
      setMessages([
        {
          id: Date.now(),
          text: "Bem-vindo! Selecione ou crie um paciente para começar.",
          sender: "bot",
          timestamp: new Date().toISOString(),
        },
      ]);
    }
  }, [patientId, consultationId]);

  // Carrega as consultas do paciente quando o patientId muda
  useEffect(() => {
    if (patientId) {
      fetchPatientConsultations(patientId);
    } else {
      setPatientConsultations([]);
    }
  }, [patientId]);

  // --- Handlers de Ação ---

  const handleSendMessage = useCallback(
    async (messageText: string) => {
      if (!messageText.trim() || !patientId || !consultationId) return;

      const userMessage: Message = {
        id: Date.now(),
        text: messageText,
        sender: "user",
        timestamp: new Date().toISOString(),
      };
      setMessages((prevMessages) => [...prevMessages, userMessage]);
      setIsLoading(true);

      try {
        const response = await fetch(`${SERVER_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: messageText,
            patient_id: patientId,
            consultation_id: consultationId,
          }),
        });

        const data = await response.json();
        if (data.status === "success") {
          if (patientId && consultationId) {
            await loadConsultationHistory(patientId, consultationId);
          }

          if (data.patient_id && data.patient_id !== patientId) {
            setPatientId(data.patient_id);
            storage.set({ patientId: data.patient_id });
          }
          if (data.consultation_id && data.consultation_id !== consultationId) {
            setConsultationId(data.consultation_id);
            storage.set({ consultationId: data.consultation_id });
          }
        } else {
          setMessages((prevMessages) => [
            ...prevMessages,
            {
              id: Date.now(),
              text: `Erro: ${data.message}`,
              sender: "bot",
              timestamp: new Date().toISOString(),
            },
          ]);
        }
      } catch (error: any) {
        console.error("Erro de rede:", error);
        setMessages((prevMessages) => [
          ...prevMessages,
          {
            id: Date.now(),
            text: `Erro de conexão: ${error.message}`,
            sender: "bot",
            timestamp: new Date().toISOString(),
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [patientId, consultationId, loadConsultationHistory]
  );

  const handleUploadPdf = useCallback(
    async (file: File) => {
      if (!file || !patientId || !consultationId) return;

      const formData = new FormData();
      formData.append("pdf", file);
      formData.append("patient_id", patientId);
      formData.append("consultation_id", consultationId);

      setIsLoading(true);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          text: `Analisando PDF "${file.name}"...`,
          sender: "bot",
          timestamp: new Date().toISOString(),
        },
      ]);

      try {
        const response = await fetch(`${SERVER_URL}/api/upload-pdf`, {
          method: "POST",
          body: formData,
        });

        const data = await response.json();
        if (data.status === "success") {
          if (patientId && consultationId) {
            await loadConsultationHistory(patientId, consultationId);
          }

          if (data.patient_id && data.patient_id !== patientId) {
            setPatientId(data.patient_id);
            storage.set({ patientId: data.patient_id });
          }
          if (data.consultation_id && data.consultation_id !== consultationId) {
            setConsultationId(data.consultation_id);
            storage.set({ consultationId: data.consultation_id });
          }
        } else {
          setMessages((prevMessages) => [
            ...prevMessages,
            {
              id: Date.now(),
              text: `Erro ao processar PDF: ${data.message}`,
              sender: "bot",
              timestamp: new Date().toISOString(),
            },
          ]);
        }
      } catch (error: any) {
        console.error("Erro de rede no upload de PDF:", error);
        setMessages((prevMessages) => [
          ...prevMessages,
          {
            id: Date.now(),
            text: `Erro de conexão ao enviar PDF: ${error.message}`,
            sender: "bot",
            timestamp: new Date().toISOString(),
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [patientId, consultationId, loadConsultationHistory]
  );

  const handleCreateNewPatient = useCallback(async () => {
    if (!newPatientName.trim()) {
      alert("Por favor, insira um nome para o paciente.");
      return;
    }
    setIsLoading(true);
    try {
      const response = await fetch(`${SERVER_URL}/api/patients`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newPatientName }),
      });
      const data = await response.json();

      if (data.status === "success") {
        const newPId = data.patient_id;
        const newPName = data.patient_name;
        const newCId = data.first_consultation_id;

        storage.set(
          {
            patientId: newPId,
            patientName: newPName,
            consultationId: newCId,
            consultationTitle: "Primeira Consulta",
          },
          () => {
            console.log(
              "Setting patientId to:",
              newPId,
              "and consultationId to:",
              newCId
            );
            setPatientId(newPId);
            setPatientName(newPName);
            setConsultationId(newCId);
            setConsultationTitle("Primeira Consulta");
            loadConsultationHistory(newPId, newCId);
            fetchAllPatients();
          }
        );
        setShowNewPatientModal(false);
        setNewPatientName("");
      } else {
        alert(`Erro ao criar paciente: ${data.message}`);
      }
    } catch (error: any) {
      console.error("Erro ao criar paciente:", error);
      alert(`Erro de rede ao criar paciente: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [newPatientName, fetchAllPatients, loadConsultationHistory]);

  const handleSelectPatient = useCallback(
    async (pId: string, pName: string) => {
      setIsLoading(true);
      try {
        const consultationsResponse = await fetch(
          `${SERVER_URL}/api/patients/${pId}/consultations`
        );
        const consultationsData = await consultationsResponse.json();

        let selectedConsultationToLoad: string | null = null;
        let selectedConsultationTitleToLoad: string | null = null;

        if (
          consultationsData.status === "success" &&
          consultationsData.consultations.length > 0
        ) {
          const sortedConsults = consultationsData.consultations.sort(
            (a: ConsultationListItem, b: ConsultationListItem) =>
              new Date(b.date).getTime() - new Date(a.date).getTime()
          );
          selectedConsultationToLoad = sortedConsults[0].id;
          selectedConsultationTitleToLoad = sortedConsults[0].title;
        } else {
          const createConsultationResponse = await fetch(
            `${SERVER_URL}/api/patients/${pId}/consultations`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                title: `Consulta Padrão - ${new Date().toLocaleDateString(
                  "pt-BR"
                )}`,
              }),
            }
          );
          const createConsultationData =
            await createConsultationResponse.json();
          if (createConsultationData.status === "success") {
            selectedConsultationToLoad = createConsultationData.consultation_id;
            selectedConsultationTitleToLoad =
              createConsultationData.consultation_title;
          } else {
            throw new Error(
              `Falha ao criar consulta para paciente selecionado: ${createConsultationData.message}`
            );
          }
        }

        if (selectedConsultationToLoad) {
          storage.set(
            {
              patientId: pId,
              patientName: pName,
              consultationId: selectedConsultationToLoad,
              consultationTitle: selectedConsultationTitleToLoad,
            },
            () => {
              setPatientId(pId);
              setPatientName(pName);
              setConsultationId(selectedConsultationToLoad);
              setConsultationTitle(selectedConsultationTitleToLoad);
              loadConsultationHistory(pId, selectedConsultationToLoad);
              setMessages((prev) => [
                ...prev,
                {
                  id: Date.now(),
                  text: `Paciente "${pName}" (${pId.substring(
                    0,
                    8
                  )}...) selecionado. Consulta "${selectedConsultationTitleToLoad}" carregada.`,
                  sender: "bot",
                  timestamp: new Date().toISOString(),
                },
              ]);
            }
          );
        }
      } catch (error: any) {
        console.error("Erro ao selecionar paciente:", error);
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now(),
            text: `Erro ao selecionar paciente: ${error.message}`,
            sender: "bot",
            timestamp: new Date().toISOString(),
          },
        ]);
      } finally {
        setIsLoading(false);
        setIsSidebarOpen(false);
      }
    },
    [loadConsultationHistory]
  );

  const handleSelectConsultation = useCallback(
    async (cId: string, cTitle: string) => {
      if (!patientId) {
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now(),
            text: "Nenhum paciente selecionado. Por favor, selecione um paciente primeiro.",
            sender: "bot",
            timestamp: new Date().toISOString(),
          },
        ]);
        return;
      }
      setIsLoading(true);
      storage.set(
        { consultationId: cId, consultationTitle: cTitle },
        () => {
          setConsultationId(cId);
          setConsultationTitle(cTitle);
          loadConsultationHistory(patientId, cId);
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              text: `Consulta "${cTitle}" (${cId.substring(
                0,
                8
              )}...) carregada.`,
              sender: "bot",
              timestamp: new Date().toISOString(),
            },
          ]);
        }
      );
      setIsSidebarOpen(false);
    },
    [patientId, loadConsultationHistory]
  );

  const handleCreateNewConsultation = useCallback(async () => {
    if (!patientId) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          text: "Por favor, selecione ou crie um paciente primeiro.",
          sender: "bot",
          timestamp: new Date().toISOString(),
        },
      ]);
      return;
    }

    setIsLoading(true);
    try {
      const newConsultationTitle = `Consulta em ${new Date().toLocaleDateString(
        "pt-BR"
      )} ${new Date().toLocaleTimeString("pt-BR")}`;
      const response = await fetch(
        `${SERVER_URL}/api/patients/${patientId}/consultations`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            title: newConsultationTitle,
            import_consultation_ids: selectedConsultationIdsToImport,
          }),
        }
      );
      const data = await response.json();

      if (data.status === "success") {
        const newConsultId = data.consultation_id;
        const newConsultTitle = data.consultation_title;

        storage.set(
          {
            consultationId: newConsultId,
            consultationTitle: newConsultTitle,
            patientId: patientId,
          },
          () => {
            setConsultationId(newConsultId);
            setConsultationTitle(newConsultTitle);
            loadConsultationHistory(patientId, newConsultId);
            setMessages((prev) => [
              ...prev,
              {
                id: Date.now(),
                text: `Nova consulta "${newConsultTitle}" criada e selecionada.`,
                sender: "bot",
                timestamp: new Date().toISOString(),
              },
            ]);

            setSelectedConsultationIdsToImport([]);
            fetchPatientConsultations(patientId);
          }
        );
      } else {
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now(),
            text: `Erro ao criar nova consulta: ${data.message}`,
            sender: "bot",
            timestamp: new Date().toISOString(),
          },
        ]);
      }
    } catch (error: any) {
      console.error("Erro ao criar nova consulta:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          text: `Erro de rede ao criar nova consulta: ${error.message}`,
          sender: "bot",
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsLoading(false);
      setShowImportHistoryModal(false);
    }
  }, [
    patientId,
    selectedConsultationIdsToImport,
    loadConsultationHistory,
    fetchPatientConsultations,
  ]);

  const handleSendExtractedDataToServer = useCallback(
    async (extractedData: Record<string, string | string[]>) => {
      if (!patientId || !consultationId) {
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now(),
            text: "Por favor, selecione ou crie um paciente e uma consulta primeiro.",
            sender: "bot",
            timestamp: new Date().toISOString(),
          },
        ]);
        return;
      }

      setIsLoading(true);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          text: "Enviando dados extraídos para análise...",
          sender: "bot",
          timestamp: new Date().toISOString(),
        },
      ]);

      try {
        const response = await fetch(`${SERVER_URL}/api/extracted-data`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            patient_id: patientId,
            consultation_id: consultationId,
            extracted_data: extractedData,
          }),
        });

        const data = await response.json();
        if (data.status === "success") {
          if (patientId && consultationId) {
            await loadConsultationHistory(patientId, consultationId);
          }
        } else {
          setMessages((prevMessages) => [
            ...prevMessages,
            {
              id: Date.now(),
              text: `Erro ao enviar dados extraídos: ${data.message}`,
              sender: "bot",
              timestamp: new Date().toISOString(),
            },
          ]);
        }
      } catch (error: any) {
        console.error("Erro de rede ao enviar dados extraídos:", error);
        setMessages((prevMessages) => [
          ...prevMessages,
          {
            id: Date.now(),
            text: `Erro de conexão ao enviar dados extraídos: ${error.message}`,
            sender: "bot",
            timestamp: new Date().toISOString(),
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [patientId, consultationId, loadConsultationHistory]
  );

  const handleExtractAndSend = useCallback(async () => {
    if (!patientId || !consultationId) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          text: "Por favor, selecione um paciente e uma consulta primeiro para extrair dados.",
          sender: "bot",
          timestamp: new Date().toISOString(),
        },
      ]);
      return;
    }

    setMessages((prev) => [
      ...prev,
      {
        id: Date.now(),
        text: "Extraindo dados da página...",
        sender: "bot",
        timestamp: new Date().toISOString(),
      },
    ]);
    setIsLoading(true);

    try {
      const editableNotesSelector = ".editable-notes";
      const createInputsSelector = ".create-input";

      const extractedContent = await executeArbitraryScriptOnActiveTab(
        (notesSel: string, inputsSel: string) => {
          const extractText = (selector: string) => {
            const element = document.querySelector(selector);
            return element ? element.textContent?.trim() || "" : "";
          };

          const extractInputs = (selector: string) => {
            const elements = Array.from(
              document.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>(
                selector
              )
            );
            return elements.map(
              (el) =>
                `${el.name || el.id || el.placeholder || "Campo"}: ${
                  el.value || ""
                }`
            );
          };

          const editableNotes = extractText(notesSel);
          const createInputs = extractInputs(inputsSel);

          return { editableNotes, createInputs };
        },
        editableNotesSelector,
        createInputsSelector
      );

      if (extractedContent) {
        await handleSendExtractedDataToServer(extractedContent);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now(),
            text: "Nenhum conteúdo relevante extraído da página.",
            sender: "bot",
            timestamp: new Date().toISOString(),
          },
        ]);
      }
    } catch (error: any) {
      console.error("Erro ao extrair dados da página:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          text: `Erro ao extrair dados: ${error.message}`,
          sender: "bot",
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [patientId, consultationId, handleSendExtractedDataToServer]);

  const handleDebugSelector = useCallback(async () => {
    if (!selectorInput.trim()) {
      setSelectorResult("Por favor, insira um seletor CSS.");
      return;
    }

    try {
      const result = await executeScriptOnActiveTab(selectorInput, 0);
      setSelectorResult(
        result || "Nenhum elemento encontrado com este seletor."
      );
    } catch (error: any) {
      setSelectorResult(`Erro ao executar seletor: ${error.message}`);
    }
  }, [selectorInput]);

// --- EFEITO 1: LIMPEZA DE ESTADO ---
useEffect(() => {
  return () => {
    console.log("🔄 Trocando de contexto/consulta. Limpando gravador...");

    // 1. Para o Hardware
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
    }

    // 2. Reseta Referências
    streamRef.current = null;
    mediaRecorderRef.current = null;
    chunksRef.current = [];
    audioBlobRef.current = null;
    recordingDurationRef.current = 0;

    // 3. Reseta Estados Visuais
    setIsRecording(false);
    setIsPaused(false);
    setIsProcessing(false);
    setHasRecordedAudio(false);
    setElapsedTime(0); // Zera o relógio visual
  };
}, [consultationId]);

// --- EFEITO 2: CARREGAR HISTÓRICO DE TRANSCRIÇÕES ---
useEffect(() => {
  if (patientId) {
    fetch(`${SERVER_URL}/api/patients/${patientId}/transcription-log`)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setTranscriptionLog(data.logs);
        }
      })
      .catch(err => console.error("Erro ao carregar log de transcrições:", err));
  } else {
    setTranscriptionLog([]);
  }
}, [patientId]);

// --- EFEITO 3: CRONÔMETRO VISUAL (Atualiza a cada segundo) ---
useEffect(() => {
  let interval: any;

  if (isRecording && !isPaused) {
    interval = setInterval(() => {
      // Calcula o tempo total: acumulado anterior + tempo da sessão atual
      const currentSessionTime = (Date.now() - recordingStartTimeRef.current) / 1000;
      setElapsedTime(recordingDurationRef.current + currentSessionTime);
    }, 1000);
  }

  return () => clearInterval(interval);
}, [isRecording, isPaused]);


// --- FUNÇÕES AUXILIARES ---

// NOVA FUNÇÃO: Estiliza os balões do chat baseado no ID/Role do falante
const getBubbleStyle = (roleKey: string | undefined) => {
  // Ajuste aqui se sua chave for 'doctor' ou 'Médico'
  const isDoctor = roleKey === 'doctor' || roleKey === 'Médico';

  return {
    alignSelf: isDoctor ? "flex-start" : "flex-end", // Médico na esquerda
    backgroundColor: isDoctor ? "#2c3e50" : "#27ae60", // Cores distintas
    color: "#fff",
    padding: "10px 14px",
    borderRadius: "12px",
    // Borda arredondada diferenciada ("bico" do balão)
    borderTopLeftRadius: isDoctor ? "0" : "12px",
    borderTopRightRadius: isDoctor ? "12px" : "0",
    maxWidth: "85%",
    boxShadow: "0 2px 4px rgba(0,0,0,0.2)"
  };
};

const formatDuration = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60); // Math.floor garante que não mostre decimais
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const audioBufferToWavBlob = useCallback((audioBuffer: AudioBuffer) => {
  const numOfChan = audioBuffer.numberOfChannels;
  const length = audioBuffer.length * numOfChan * 2 + 44;
  const buffer = new ArrayBuffer(length);
  const view = new DataView(buffer);
  const channels: Float32Array[] = [];
  for (let i = 0; i < numOfChan; i++) {
    channels.push(audioBuffer.getChannelData(i));
  }
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + audioBuffer.length * numOfChan * 2, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numOfChan, true);
  view.setUint32(24, audioBuffer.sampleRate, true);
  view.setUint32(28, audioBuffer.sampleRate * numOfChan * 2, true);
  view.setUint16(32, numOfChan * 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, audioBuffer.length * numOfChan * 2, true);
  let offset = 44;
  for (let i = 0; i < audioBuffer.length; i++) {
    for (let channel = 0; channel < numOfChan; channel++) {
      let sample = Math.max(-1, Math.min(1, channels[channel][i]));
      sample = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      view.setInt16(offset, sample, true);
      offset += 2;
    }
  }
  return new Blob([view], { type: "audio/wav" });
}, []);

const writeString = (view: DataView, offset: number, str: string) => {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
};

// --- Envio do áudio para o servidor ---
const sendAudioToServer = useCallback(async (wavBlob: Blob, duration: number) => {
  try {
    if (!patientId || !consultationId) {
        console.error("IDs ausentes para envio de áudio.");
        return;
    }

    const form = new FormData();
    const file = new File([wavBlob], "recording.wav", { type: "audio/wav" });
    form.append("audio_file", file);
    form.append("patient_id", patientId);
    form.append("consultation_id", consultationId);
    form.append("duration", duration.toString());

    const resp = await fetch(`${SERVER_URL}/api/transcribe_audio`, {
      method: "POST",
      body: form,
    });

    if (!resp.ok) throw new Error(`Erro no servidor: ${resp.statusText}`);

    const data = await resp.json();

    const invalidPhrases = [
        "Não foi possível entender o áudio",
        "Não foi possível entender o áudio.",
        "Erro na API de reconhecimento de fala"
    ];

    if (data && data.transcription && !data.is_error) {
        const texto = String(data.transcription).trim();
        const ehErro = invalidPhrases.some(phrase => texto.includes(phrase));

        if (!ehErro && texto.length > 0) {
          // Atualiza lista visual de logs
          if (data.log_entry) {
             setTranscriptionLog(prev => [data.log_entry, ...prev]);
          }
          // Envia transcrição para o fluxo de chat
          await handleSendMessage(texto);
        } else {
          setMessages(prev => [...prev, {
            id: Date.now(),
            text: "❌ Não foi possível transcrever o áudio. Tente falar mais claro.",
            sender: "bot",
            timestamp: new Date().toISOString()
          }]);
        }
    }
  } catch (err) {
    console.error("Erro ao enviar áudio:", err);
    setMessages(prev => [...prev, {
      id: Date.now(),
      text: "❌ Erro ao enviar áudio. Verifique sua conexão.",
      sender: "bot",
      timestamp: new Date().toISOString()
    }]);
  }
}, [handleSendMessage, patientId, consultationId]);


// --- Processamento de Áudio ---
const processAndSendAudio = useCallback(async (blob: Blob, duration: number) => {
  if (blob.size < 1000) {
    console.log("Áudio muito curto, ignorando...");
    return;
  }
  try {
    const arrayBuffer = await blob.arrayBuffer();
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
    const audioCtx = new AudioCtx();
    const decodedBuffer = await audioCtx.decodeAudioData(arrayBuffer);
    const wavBlob = audioBufferToWavBlob(decodedBuffer);

    await sendAudioToServer(wavBlob, duration);

    if (audioCtx.state !== 'closed') await audioCtx.close();
  } catch (err) {
    console.error("Erro ao processar áudio:", err);
    throw err;
  }
}, [audioBufferToWavBlob, sendAudioToServer]);


// --- Função para iniciar gravação (Com DELAY Anti-Alucinação) ---
const startAudioRecording = useCallback(async () => {
  try {
    if (isProcessing || isRecording || isPaused) return;
    if (!consultationId) return;

    console.log("🎤 Preparando gravação automática...");

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;

    const mediaRecorder = new MediaRecorder(stream);
    mediaRecorderRef.current = mediaRecorder;
    chunksRef.current = [];
    audioBlobRef.current = null;

    // Reseta contadores antes de começar
    setElapsedTime(0);
    recordingStartTimeRef.current = Date.now();
    recordingDurationRef.current = 0;

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      console.log("⏹️ Gravação parada");

      const finalDuration = recordingDurationRef.current;
      const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
      audioBlobRef.current = blob;

      if (blob.size > 1000) {
        setHasRecordedAudio(true);
        console.log(`✅ Áudio gravado. Duração: ${formatDuration(finalDuration)}`);

        setIsProcessing(true);
        try {
          await processAndSendAudio(blob, finalDuration);
        } catch (error) {
          console.error("Erro ao processar:", error);
        } finally {
          setIsProcessing(false);
        }
      } else {
        console.log("Áudio muito curto...");
        setHasRecordedAudio(false);
        audioBlobRef.current = null;
      }

      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      chunksRef.current = [];
    };

    // --- CORREÇÃO DE ALUCINAÇÃO: Pequeno delay de 200ms ---
    setTimeout(() => {
        if (mediaRecorder.state === "inactive") {
            mediaRecorder.start();
            setIsRecording(true);
            setIsPaused(false);
            setHasRecordedAudio(false);

            // Define o tempo inicial real AGORA, após o delay
            recordingStartTimeRef.current = Date.now();
            recordingDurationRef.current = 0;
            setElapsedTime(0);
        }
    }, 200);

  } catch (error: any) {
    console.error("Erro ao iniciar gravação:", error);
    let errorMessage = "Erro ao acessar o microfone.";
    if (error.name === "NotAllowedError") errorMessage = "Permissão de microfone negada.";
    setMessages(prev => [...prev, { id: Date.now(), text: errorMessage, sender: "bot", timestamp: new Date().toISOString() }]);
  }
}, [isProcessing, isRecording, isPaused, processAndSendAudio, consultationId]);


// --- Função para pausar gravação ---
const togglePauseRecording  = useCallback(() => {
  if (mediaRecorderRef.current && isRecording && !isPaused) {
    // PAUSAR
    mediaRecorderRef.current.pause();
    setIsRecording(false);
    setIsPaused(true);
    // Congela a duração acumulada até agora
    recordingDurationRef.current += (Date.now() - recordingStartTimeRef.current) / 1000;
    console.log("⏸️ Gravação pausada");

  } else if (mediaRecorderRef.current && !isRecording && isPaused) {
    // RETOMAR
    mediaRecorderRef.current.resume();
    setIsRecording(true);
    setIsPaused(false);
    // Reinicia o "ponto de partida" do segmento atual
    recordingStartTimeRef.current = Date.now();
    console.log("▶️ Gravação retomada");
  }
}, [isRecording, isPaused]);


// --- Função para parar gravação ---
const stopAudioRecording = useCallback(() => {
  if (mediaRecorderRef.current && (isRecording || isPaused)) {
    // Se estava gravando, soma o último segmento
    if (!isPaused) {
       recordingDurationRef.current += (Date.now() - recordingStartTimeRef.current) / 1000;
    }
    // Para forçado o relógio visual no valor final
    setElapsedTime(recordingDurationRef.current);

    mediaRecorderRef.current.stop();
    setIsRecording(false);
    setIsPaused(false);
    console.log("⏹️ Gravação finalizada manualmente");
  }
}, [isRecording, isPaused]);


// --- Função para ver histórico ---
const toggleRecordingHistory = useCallback(() => {
  setShowRecordingHistory(prev => !prev);
}, []);


useEffect(() => {
  // --- Auto-Start ---
  if (consultationId && !isRecording && !isProcessing && !isPaused && !viewingLog) {
    const timer = setTimeout(() => {
      startAudioRecording();
    }, 1000);
    return () => clearTimeout(timer);
  }
}, [consultationId, isRecording, isProcessing, isPaused, startAudioRecording, viewingLog]);

  // --- Renderização ---

  return (
    <div className="App">
      <header className="App-header">
        <h1>Copilot Médico</h1>
        <FirstAidIcon weight="fill" size={32} />
      </header>

      {/* Sidebar */}
      <div
        className={`sidebar ${isSidebarOpen ? "open" : ""}`}
        style={{ borderBottom: "1px solid #ccc" }}
      >
        <h2>Pacientes</h2>

        <div className="new-patient-div">
          <select
            className="patient-select"
            value={patientId || ""}
            onChange={(e) => {
              const selectedPatient = allPatients.find(
                (p) => p.id === e.target.value
              );
              if (selectedPatient) {
                handleSelectPatient(selectedPatient.id, selectedPatient.name);
              } else {
                setPatientId(null);
                setPatientName(null);
                setConsultationId(null);
                setConsultationTitle(null);
                setMessages([
                  {
                    id: Date.now(),
                    text: "Nenhum paciente selecionado.",
                    sender: "bot",
                    timestamp: new Date().toISOString(),
                  },
                ]);
              }
            }}
            disabled={isLoading}
          >
            <option value="">Selecione um Paciente</option>
            {allPatients.map((patient) => (
              <option key={patient.id} value={patient.id}>
                {patient.name} ({patient.id.substring(0, 8)}...)
              </option>
            ))}
          </select>

          <div className="patient-controls">
            <button
              className="btn-green small"
              onClick={() => setShowNewPatientModal(true)}
              disabled={isLoading}
            >
              <UserCirclePlusIcon size={21} weight="fill" />
            </button>
          </div>
        </div>

        {patientId && (
          <>
            <h2>Paciente: {patientName || patientId.substring(0, 8)}</h2>
            <div className="consultation-controls">
              <button
                className="btn-white"
                onClick={() => setShowImportHistoryModal(true)}
                disabled={isLoading}
                style={{ marginRight: "5px" }}
              >
                Importar Consulta
              </button>
              <button
                className="btn-green"
                onClick={() => {
                  setSelectedConsultationIdsToImport([]);
                  handleCreateNewConsultation();
                }}
                disabled={isLoading}
              >
                Nova Consulta
              </button>
            </div>

            <select
              className="patient-select"
              value={consultationId || ""}
              onChange={(e) => {
                const selectedConsultation = patientConsultations.find(
                  (c) => c.id === e.target.value
                );
                if (selectedConsultation) {
                  handleSelectConsultation(
                    selectedConsultation.id,
                    selectedConsultation.title
                  );
                } else {
                  setConsultationId(null);
                  setConsultationTitle(null);
                  setMessages([
                    {
                      id: Date.now(),
                      text: "Nenhuma consulta selecionada para o paciente atual.",
                      sender: "bot",
                      timestamp: new Date().toISOString(),
                    },
                  ]);
                }
              }}
              disabled={isLoading || patientConsultations.length === 0}
            >
              <option value="">Selecione uma Consulta</option>
              {patientConsultations.map((consultation) => (
                <option key={consultation.id} value={consultation.id}>
                  {consultation.title} ({consultation.id.substring(0, 8)}...)
                </option>
              ))}
            </select>
          </>
        )}
      </div>

{consultationId && (
  <div style={{
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    marginTop: "10px",
    padding: "0 10px",
    position: "relative" // Importante para transições se quiser animar depois
  }}>

    {/* === MODO LEITURA (Arquivo Aberto) === */}
    {viewingLog ? (
      <div style={{
        backgroundColor: "#2d2d2d", // Fundo escuro tipo editor
        border: "1px solid #444",
        borderRadius: "8px",
        padding: "15px",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        minHeight: "400px", // AUMENTADO PARA MELHOR VISUALIZAÇÃO
        maxHeight: "600px",
        animation: "fadeIn 0.2s" // Simples efeito visual
      }}>
        {/* Cabeçalho do Arquivo */}
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: "1px solid #555",
          paddingBottom: "10px",
          marginBottom: "5px"
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "24px" }}>📄</span>
            <div>
              <div style={{ color: "#fff", fontWeight: "bold", fontSize: "0.9em" }}>
                Transcrição de {new Date(viewingLog.timestamp).toLocaleDateString()}
              </div>
              <div style={{ color: "#aaa", fontSize: "0.8em" }}>
                Horário: {new Date(viewingLog.timestamp).toLocaleTimeString()} • Duração: {viewingLog.duration}
              </div>
            </div>
          </div>

          <button
            onClick={() => setViewingLog(null)}
            style={{
              background: "transparent",
              border: "1px solid #666",
              color: "#fff",
              borderRadius: "4px",
              cursor: "pointer",
              padding: "5px 10px",
              fontSize: "0.8em"
            }}
          >
            ❌ Fechar Arquivo
          </button>
        </div>

        {/* Conteúdo do Texto ou CHAT DIARIZADO */}
        <div style={{
          flex: 1,
          overflowY: "auto",
          padding: "10px",
          backgroundColor: "#1a1a1a", // Fundo ligeiramente diferente para o chat
          borderRadius: "4px",
          border: "1px solid #333",
          display: "flex",
          flexDirection: "column",
          gap: "10px"
        }}>

          {/* Verifica se é um log moderno com diarização */}
          {viewingLog.dialogue && Array.isArray(viewingLog.dialogue) ? (
             viewingLog.dialogue.map((turn: any, idx: number) => (
                <div key={idx} style={getBubbleStyle(turn.role_key || (turn.role === 'Médico' ? 'doctor' : 'patient'))}>
                   <div style={{
                      fontSize: "0.75em",
                      color: "rgba(255,255,255,0.7)",
                      marginBottom: "4px",
                      fontWeight: "bold",
                      textTransform: "uppercase"
                   }}>
                      {turn.role}
                   </div>
                   <div style={{ lineHeight: "1.4" }}>
                      {turn.text}
                   </div>
                </div>
             ))
          ) : (
            // Fallback para logs antigos (Texto corrido)
            <div style={{
              whiteSpace: "pre-wrap",
              color: "#e0e0e0",
              lineHeight: "1.5",
              fontSize: "0.95em"
            }}>
              {viewingLog.text || viewingLog.text_summary}
            </div>
          )}

        </div>

        <div style={{ textAlign: "right", fontSize: "0.75em", color: "#666" }}>
          ID Ref: {viewingLog.consultation_id}
        </div>
      </div>
    ) : (

      /* === MODO GRAVAÇÃO E LISTA (Padrão) === */
      <>
        {/* Controles de Gravação (Só aparecem se não estiver lendo) */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "10px" }}>
          <button
            onClick={togglePauseRecording}
            disabled={(!isRecording && !isPaused) || isProcessing}
            style={{
              padding: "10px 15px",
              backgroundColor: isRecording ? "#FFA500" : isPaused ? "#4CAF50" : "#cccccc",
              color: "white", border: "none", borderRadius: "4px",
              cursor: (isRecording || isPaused) ? "pointer" : "not-allowed",
              flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "5px"
            }}
          >
            {isRecording ? "⏸️ Pausar" : isPaused ? "▶️ Retomar" : "⏸️ Pausar/Retomar"}
          </button>

          <button
            onClick={stopAudioRecording}
            disabled={(!isRecording && !isPaused) || isProcessing}
            style={{
              padding: "10px 15px", backgroundColor: "#e66060", color: "white",
              border: "none", borderRadius: "4px", cursor: "pointer", flex: 1
            }}
          >
            ⏹️ Parar
          </button>

          <button
            onClick={toggleRecordingHistory}
            style={{
              padding: "10px 15px", backgroundColor: showRecordingHistory ? "#1976D2" : "#2196F3", color: "white",
              border: "none", borderRadius: "4px", cursor: "pointer"
            }}
          >
            {showRecordingHistory ? "📂 Ocultar Arq." : "📂 Transcrições"} ({transcriptionLog.length})
          </button>
        </div>

        {/* Status Messages */}
        <div style={{ textAlign: "center" }}>
          {isProcessing && <div style={{ color: "orange", fontWeight: "bold" }}>⏳ Processando...</div>}
          {isRecording && <div style={{ color: "#e66060", fontWeight: "bold" }}>● Gravando... ({formatDuration(elapsedTime)})</div>}
          {isPaused && <div style={{ color: "#FFA500", fontWeight: "bold" }}>⏸️ Pausado</div>}
          {hasRecordedAudio && !isRecording && !isPaused && <div style={{ color: "#4CAF50", fontWeight: "bold" }}>✓ Arquivo salvo</div>}
        </div>

        {/* Painel de Arquivos (Lista de Ícones) */}
        {showRecordingHistory && (
          <div style={{
            border: "1px solid #ddd", borderRadius: "4px", padding: "10px",
            backgroundColor: "#5e5e5eff", maxHeight: "250px", overflowY: "auto"
          }}>
            <h4 style={{ margin: "0 0 10px 0", borderBottom: "1px solid #777", paddingBottom: "5px", color: "#fff" }}>
                 Arquivos de Transcrição
            </h4>

            {transcriptionLog.length === 0 ? (
              <p style={{ margin: 0, color: "#ccc", fontStyle: "italic" }}>Nenhum arquivo encontrado.</p>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "10px" }}>
                {transcriptionLog.map((log) => (
                  <div
                    key={log.id}
                    onClick={() => {
                        // Ao clicar no arquivo:
                        // 1. Se estiver gravando, PAUSA para o usuário ler em paz
                        if (isRecording) togglePauseRecording();
                        // 2. Abre o modo leitura
                        setViewingLog(log);
                    }}
                    style={{
                      backgroundColor: "rgba(255,255,255,0.1)",
                      border: "1px solid #666",
                      borderRadius: "6px",
                      padding: "10px",
                      cursor: "pointer",
                      transition: "background 0.2s",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      textAlign: "center",
                      gap: "5px"
                    }}
                    onMouseOver={(e) => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.2)"}
                    onMouseOut={(e) => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.1)"}
                  >
                    {/* Ícone de Arquivo */}
                    <div style={{ fontSize: "2rem" }}>📄</div>

                    <div style={{ color: "#fff", fontWeight: "bold", fontSize: "0.85em" }}>
                      {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>

                    <div style={{ color: "#bbb", fontSize: "0.75em" }}>
                      {new Date(log.timestamp).toLocaleDateString()}
                    </div>

                    <div style={{
                        backgroundColor: "#4CAF50", color: "white",
                        borderRadius: "10px", padding: "2px 8px",
                        fontSize: "0.7em", marginTop: "2px"
                    }}>
                      {log.duration}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </>
    )}
  </div>
)}
      {/* Main Chat Area */}
      <div className="chat-container">
        <Chat
          messages={messages}
          isLoading={isLoading}
          onSendMessage={handleSendMessage}
          onUploadPdf={handleUploadPdf}
        />
      </div>

      <div>
        {/* Debug Mode Toggle */}
        <div style={{ marginTop: "10px", textAlign: "center" }}>
          <label>
            <input
              type="checkbox"
              checked={debugMode}
              onChange={(e) => setDebugMode(e.target.checked)}
            />
            Modo Debug
          </label>
        </div>
        {/* Debug Controls */}
        {debugMode && (
          <div
            style={{
              borderTop: "1px solid #eee",
              marginTop: "10px",
              paddingTop: "10px",
            }}
          >
            <h3>Debug Seletor CSS</h3>
            <input
              type="text"
              placeholder="Ex: .some-class div > span"
              value={selectorInput}
              onChange={(e) => setSelectorInput(e.target.value)}
              style={{ width: "calc(100% - 70px)", marginRight: "5px" }}
            />
            <button onClick={handleDebugSelector}>Testar</button>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
                maxHeight: "150px",
                overflowY: "auto",
                border: "1px solid #ddd",
                padding: "5px",
                background: "#f9f9f9",
                marginTop: "5px",
              }}
            >
              {selectorResult}
            </pre>
          </div>
        )}
        {/* Botão de Extrair Dados da Página */}
        <button
          onClick={handleExtractAndSend}
          disabled={isLoading || !patientId || !consultationId}
          style={{ marginTop: "10px", padding: "10px", width: "100%" }}
        >
          Extrair Dados da Página
        </button>
      </div>

      {/* Modal para Criar Novo Paciente */}
      {showNewPatientModal && (
        <div className="modal">
          <div className="new-patient-modal">
            <h3>Criar Novo Paciente</h3>
            <input
              type="text"
              placeholder="Nome do Paciente"
              value={newPatientName}
              onChange={(e) => setNewPatientName(e.target.value)}
              style={{
                width: "calc(100% - 20px)",
                marginBottom: "10px",
                padding: "8px",
              }}
            />
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: "10px",
              }}
            >
              <button
                onClick={() => setShowNewPatientModal(false)}
                style={{
                  padding: "8px 15px",
                  cursor: "pointer",
                  backgroundColor: "#D9D9D9",
                }}
              >
                Cancelar
              </button>
              <button
                onClick={handleCreateNewPatient}
                disabled={isLoading}
                style={{
                  padding: "8px 15px",
                  cursor: "pointer",
                  backgroundColor: "#336B29",
                  color: "white",
                }}
              >
                Criar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal para seleção de históricos de consulta para importação */}
      {showImportHistoryModal && patientId && (
        <div className="modal">
          <div className="history-import-modal">
            <h3 style={{ marginTop: "0" }}>
              Selecionar Históricos para Nova Consulta
            </h3>
            <p>
              Marque os históricos de consultas anteriores que você deseja
              importar para a nova conversa.
            </p>

            {patientConsultations.length === 0 ? (
              <p>Nenhuma consulta anterior encontrada para este paciente.</p>
            ) : (
              <div style={{ marginBottom: "15px" }}>
                {patientConsultations.map(
                  (consultation) =>
                    consultation.id !== consultationId && (
                      <div
                        key={consultation.id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          marginBottom: "8px",
                        }}
                      >
                        <input
                          type="checkbox"
                          id={`consultation-${consultation.id}`}
                          checked={selectedConsultationIdsToImport.includes(
                            consultation.id
                          )}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedConsultationIdsToImport((prev) => [
                                ...prev,
                                consultation.id,
                              ]);
                            } else {
                              setSelectedConsultationIdsToImport((prev) =>
                                prev.filter((id) => id !== consultation.id)
                              );
                            }
                          }}
                          style={{ marginRight: "10px" }}
                        />
                        <label
                          htmlFor={`consultation-${consultation.id}`}
                          style={{ flexGrow: 1, cursor: "pointer" }}
                        >
                          <strong>{consultation.title}</strong>
                          <br />
                          <small>
                            ID: {consultation.id.substring(0, 8)}... - Criada
                            em:{" "}
                            {new Date(consultation.date).toLocaleDateString(
                              "pt-BR"
                            )}
                          </small>
                        </label>
                      </div>
                    )
                )}
              </div>
            )}

            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: "10px",
              }}
            >
              <button
                onClick={() => {
                  setSelectedConsultationIdsToImport([]);
                  setShowImportHistoryModal(false);
                }}
                style={{
                  padding: "8px 15px",
                  cursor: "pointer",
                  backgroundColor: "#D9D9D9",
                }}
              >
                Cancelar
              </button>
              <button
                onClick={() => {
                  handleCreateNewConsultation();
                }}
                disabled={isLoading}
                style={{
                  padding: "8px 15px",
                  cursor: "pointer",
                  backgroundColor: "#336B29",
                  color: "white",
                }}
              >
                Criar Nova Consulta com Histórico(s)
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;