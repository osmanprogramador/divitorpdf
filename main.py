"""
DivitorPDF — Separador de PDFs por Funcionário
========================================================
Ferramenta com interface gráfica para dividir PDFs
e renomear cada página com o nome do funcionário.
"""

import json
import os
import re
import subprocess
import threading
import webbrowser
import customtkinter as ctk
from tkinter import filedialog

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

import pdfplumber
from PyPDF2 import PdfReader, PdfWriter


# ─── Design Tokens ──────────────────────────────────────────────────────────
BG_MAIN       = "#0d1117"
BG_CARD       = "#161b22"
BG_INPUT      = "#21262d"
BG_HOVER      = "#292e36"
ACCENT        = "#58a6ff"
ACCENT_HOVER  = "#79c0ff"
ACCENT_DIM    = "#1f6feb"
FG_TEXT        = "#e6edf3"
FG_MUTED      = "#8b949e"
SUCCESS       = "#3fb950"
WARNING       = "#d29922"
ERROR         = "#f85149"
BORDER        = "#30363d"
FONT_FAMILY   = "Segoe UI"

APP_VERSION   = "1.0.0"
GITHUB_OWNER  = "osmanprogramador"
GITHUB_REPO   = "divitorpdf"
GITHUB_API    = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

PROFILES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.json")

# ─── Perfis padrão ──────────────────────────────────────────────────────────

DEFAULT_PROFILE_NAME = "Contracheque (Padrão)"

DEFAULT_PATTERNS = [
    r'Func[\. ]*:\s*(?:\d+\s*[-–]\s*)?(.+)',
    r'Funcion.rio[\.: ]*\s*(?:\d+\s*[-–]\s*)?(.+)',
    r'Nome\s*(?:do\s*Funcion.rio)?[\.: ]*\s*([A-ZÀ-Ú][A-Za-zÀ-ú\s]+)',
    r'Empregado[\.: ]*\s*(.+)',
    r'Colaborador[\.: ]*\s*(.+)',
    r'Trabalhador[\.: ]*\s*(.+)',
    r'Servidor[\.: ]*\s*(.+)',
]

DEFAULT_LABELS = [
    "Func.:", "Funcionário:", "Nome:", "Nome do Funcionário:",
    "Empregado:", "Colaborador:", "Trabalhador:", "Servidor:"
]


def load_profiles() -> dict:
    """Carrega perfis customizados do arquivo JSON."""
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"custom_profiles": {}}


def save_profiles(data: dict):
    """Salva perfis customizados no arquivo JSON."""
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all_profile_names() -> list[str]:
    """Retorna lista de nomes de todos os perfis (padrão + customizados)."""
    data = load_profiles()
    names = [DEFAULT_PROFILE_NAME]
    names.extend(sorted(data.get("custom_profiles", {}).keys()))
    return names


def labels_to_patterns(labels: list[str]) -> list[str]:
    """Converte rótulos simples do usuário em padrões regex."""
    patterns = []
    for label in labels:
        escaped = re.escape(label.strip().rstrip(":"))
        pattern = escaped + r'[\.: ]*\s*(?:\d+\s*[-–]\s*)?(.+)'
        patterns.append(pattern)
    return patterns


# ─── Lógica de extração ─────────────────────────────────────────────────────

def extract_employee_name(page_text: str, custom_patterns: list[str] | None = None) -> str | None:
    """
    Extrai o nome do funcionário/pessoa do texto da página.
    Se custom_patterns for fornecido, usa esses padrões em vez dos padrões padrão.
    """
    if not page_text:
        return None

    lines = page_text.split('\n')
    normalized_text = '\n'.join(' '.join(line.split()) for line in lines)

    patterns = custom_patterns if custom_patterns else DEFAULT_PATTERNS

    for pattern in patterns:
        match = re.search(pattern, normalized_text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            name = re.split(
                r'\s{2,}|\t|Per[ií]odo|CPF|Matr[ií]cula|Cargo|Departamento|'
                r'Admiss[ãa]o|Banco|Conta|Ag[eê]ncia|Setor|Lota[çc][ãa]o|'
                r'CBO|CTPS|PIS|Sal[aá]rio|Fun[çc][ãa]o',
                name
            )[0]
            name = name.strip(' -–.:,\t')
            if len(name) >= 3:
                return sanitize_filename(name)

    return None


def sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos para nome de arquivo."""
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def get_unique_filename(output_dir: str, base_name: str, ext: str = ".pdf") -> str:
    """Retorna um nome de arquivo único, adicionando (2), (3)... se necessário."""
    filepath = os.path.join(output_dir, f"{base_name}{ext}")
    if not os.path.exists(filepath):
        return filepath

    counter = 2
    while True:
        filepath = os.path.join(output_dir, f"{base_name} ({counter}){ext}")
        if not os.path.exists(filepath):
            return filepath
        counter += 1


def split_pdf(pdf_path: str, output_dir: str, progress_callback=None,
              log_callback=None, custom_patterns: list[str] | None = None):
    """
    Divide o PDF em páginas individuais, renomeando cada uma com o nome
    encontrado na página usando os padrões do perfil selecionado.
    """
    if log_callback:
        log_callback(f"📂  Abrindo: {os.path.basename(pdf_path)}", "info")

    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    if log_callback:
        log_callback(f"📄  Total de páginas: {total_pages}", "info")

    os.makedirs(output_dir, exist_ok=True)

    sucesso = 0
    falhas = 0

    with pdfplumber.open(pdf_path) as plumber:
        for i, page in enumerate(reader.pages):
            page_num = i + 1

            try:
                plumber_page = plumber.pages[i]
                text = plumber_page.extract_text() or ""
            except Exception:
                text = ""

            name = extract_employee_name(text, custom_patterns)

            if name:
                output_path = get_unique_filename(output_dir, name)
                if log_callback:
                    log_callback(f"✅  Pág. {page_num}: {name}", "success")
                sucesso += 1
            else:
                fallback_name = f"Pagina_{page_num:03d}"
                output_path = get_unique_filename(output_dir, fallback_name)
                if log_callback:
                    log_callback(f"⚠️  Pág. {page_num}: Nome não encontrado → {fallback_name}", "warning")
                falhas += 1
                if log_callback and text:
                    preview = text[:300].replace('\n', ' | ')
                    log_callback(f"     🔍 Texto: {preview}", "muted")

            writer = PdfWriter()
            writer.add_page(page)
            with open(output_path, "wb") as f:
                writer.write(f)

            if progress_callback:
                progress_callback(page_num, total_pages)

    if log_callback:
        log_callback("─" * 50, "separator")
        log_callback(f"🏁  Concluído — {sucesso} extraídos, {falhas} sem nome.", "info")

    return sucesso, falhas, total_pages


# ─── Interface Gráfica ──────────────────────────────────────────────────────

class DivitorPDFApp:
    def __init__(self):
        # Configurar tema do CustomTkinter
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("DivitorPDF")
        self.root.geometry("800x700")
        self.root.configure(fg_color=BG_MAIN)
        self.root.resizable(True, True)
        self.root.minsize(650, 580)

        # Variáveis
        self.pdf_path = ""
        self.output_dir = ""
        self.is_processing = False
        self.last_output_dir = None

        self._build_ui()
        self._center_window()

        # Verificar atualizações em background
        threading.Thread(target=self._check_for_updates, daemon=True).start()

    def _center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

    def _build_ui(self):
        # ── Container raiz ──
        self.root_frame = ctk.CTkFrame(self.root, fg_color=BG_MAIN, corner_radius=0)
        self.root_frame.pack(fill="both", expand=True, padx=24, pady=20)

        # ── Header (sempre visível) ──
        header = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))

        title_label = ctk.CTkLabel(
            header, text="✂️  DivitorPDF",
            font=(FONT_FAMILY, 26, "bold"), text_color=FG_TEXT
        )
        title_label.pack(side="left")

        self.subtitle = ctk.CTkLabel(
            header, text="Separador de PDFs",
            font=(FONT_FAMILY, 13), text_color=FG_MUTED
        )
        self.subtitle.pack(side="left", padx=(14, 0), pady=(6, 0))

        # Botão Leia-me / Voltar
        self.btn_readme = ctk.CTkButton(
            header, text="ℹ️  Leia-me", width=110, height=32,
            font=(FONT_FAMILY, 12), corner_radius=8,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_MUTED,
            command=self._toggle_readme
        )
        self.btn_readme.pack(side="right")

        # Botão Perfis
        self.btn_profiles = ctk.CTkButton(
            header, text="⚙️  Perfis", width=110, height=32,
            font=(FONT_FAMILY, 12), corner_radius=8,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_MUTED,
            command=self._toggle_profiles
        )
        self.btn_profiles.pack(side="right", padx=(0, 6))

        # ── Frame de conteúdo principal (ferramenta de split) ──
        self.content_frame = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)
        self._current_view = "main"  # main, readme, profiles

        # Alias para manter compatibilidade com result_banner
        self.main_frame = self.content_frame
        main = self.content_frame

        # ── Banner de resultado (oculto por padrão) ──
        self.result_banner = ctk.CTkFrame(main, fg_color=BG_CARD, corner_radius=12,
                                           border_width=1, border_color=BORDER)
        self.result_banner_visible = False

        # ── Seletor de perfil ──
        profile_row = ctk.CTkFrame(main, fg_color="transparent")
        profile_row.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            profile_row, text="🏷️ Perfil de Rótulos",
            font=(FONT_FAMILY, 12, "bold"), text_color=FG_TEXT
        ).pack(side="left")

        self.profile_var = ctk.StringVar(value=DEFAULT_PROFILE_NAME)
        self.profile_dropdown = ctk.CTkOptionMenu(
            profile_row,
            variable=self.profile_var,
            values=get_all_profile_names(),
            font=(FONT_FAMILY, 12),
            dropdown_font=(FONT_FAMILY, 12),
            height=34, corner_radius=8,
            fg_color=BG_INPUT, button_color=BG_HOVER,
            button_hover_color=ACCENT_DIM,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BG_HOVER,
            text_color=FG_TEXT,
            dropdown_text_color=FG_TEXT,
            width=250
        )
        self.profile_dropdown.pack(side="right")

        # ── Drop Zone ──
        self.drop_card = ctk.CTkFrame(
            main, fg_color=BG_CARD, corner_radius=12,
            border_width=2, border_color=BORDER
        )
        self.drop_card.pack(fill="x", pady=(0, 14))

        drop_inner = ctk.CTkFrame(
            self.drop_card, fg_color="transparent", height=110
        )
        drop_inner.pack(fill="x", padx=20, pady=20)
        drop_inner.pack_propagate(False)

        self.drop_icon = ctk.CTkLabel(
            drop_inner, text="📄",
            font=(FONT_FAMILY, 32), text_color=FG_MUTED
        )
        self.drop_icon.pack(pady=(8, 4))

        self.drop_label = ctk.CTkLabel(
            drop_inner, text="Clique ou arraste um PDF aqui",
            font=(FONT_FAMILY, 13), text_color=FG_MUTED
        )
        self.drop_label.pack()

        self.file_label = ctk.CTkLabel(
            drop_inner, text="",
            font=(FONT_FAMILY, 11), text_color=ACCENT
        )
        self.file_label.pack(pady=(2, 0))

        # Tornar a zona clicável
        for widget in [self.drop_card, drop_inner, self.drop_icon, self.drop_label, self.file_label]:
            widget.bind("<Button-1>", lambda e: self._select_pdf())
            widget.configure(cursor="hand2")

        # Drag-and-drop (se disponível)
        if HAS_DND:
            try:
                self.drop_card.drop_target_register(DND_FILES)
                self.drop_card.dnd_bind("<<Drop>>", self._on_drop)
                self.drop_card.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                self.drop_card.dnd_bind("<<DragLeave>>", self._on_drag_leave)
            except Exception:
                pass

        # ── Pasta de saída ──
        out_frame = ctk.CTkFrame(main, fg_color="transparent")
        out_frame.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            out_frame, text="📁 Pasta de Saída",
            font=(FONT_FAMILY, 12, "bold"), text_color=FG_TEXT
        ).pack(anchor="w", pady=(0, 6))

        out_row = ctk.CTkFrame(out_frame, fg_color="transparent")
        out_row.pack(fill="x")

        self.out_entry = ctk.CTkEntry(
            out_row, placeholder_text="Selecione a pasta de saída...",
            font=(FONT_FAMILY, 12), height=40,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=FG_TEXT, placeholder_text_color=FG_MUTED,
            corner_radius=8
        )
        self.out_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            out_row, text="Selecionar", width=110, height=40,
            font=(FONT_FAMILY, 12), corner_radius=8,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_TEXT,
            command=self._select_output
        ).pack(side="right")

        # ── Botões de ação ──
        btn_row = ctk.CTkFrame(main, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 14))

        self.btn_split = ctk.CTkButton(
            btn_row, text="✂️   DIVIDIR PDF",
            font=(FONT_FAMILY, 14, "bold"), height=48,
            corner_radius=10,
            fg_color=ACCENT_DIM, hover_color=ACCENT,
            text_color="#ffffff",
            command=self._start_split
        )
        self.btn_split.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_open_folder = ctk.CTkButton(
            btn_row, text="📂  Abrir Pasta",
            font=(FONT_FAMILY, 13), height=48, width=140,
            corner_radius=10,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_MUTED,
            command=self._open_output_folder,
            state="disabled"
        )
        self.btn_open_folder.pack(side="right")

        # ── Progresso ──
        progress_frame = ctk.CTkFrame(main, fg_color="transparent")
        progress_frame.pack(fill="x", pady=(0, 4))

        self.progress_bar = ctk.CTkProgressBar(
            progress_frame, height=6, corner_radius=3,
            fg_color=BG_INPUT, progress_color=ACCENT_DIM
        )
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            progress_frame, text="",
            font=(FONT_FAMILY, 11), text_color=FG_MUTED
        )
        self.progress_label.pack(anchor="w", pady=(4, 0))

        # ── Log de atividade ──
        self._log_header = ctk.CTkFrame(main, fg_color="transparent")
        self._log_header.pack(fill="x", pady=(6, 6))

        ctk.CTkLabel(
            self._log_header, text="📋 Log de Atividade",
            font=(FONT_FAMILY, 12, "bold"), text_color=FG_TEXT
        ).pack(side="left")

        self.btn_clear_log = ctk.CTkButton(
            self._log_header, text="Limpar", width=70, height=28,
            font=(FONT_FAMILY, 11), corner_radius=6,
            fg_color="transparent", hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_MUTED,
            command=self._clear_log
        )
        self.btn_clear_log.pack(side="right")

        log_card = ctk.CTkFrame(
            main, fg_color=BG_CARD, corner_radius=10,
            border_width=1, border_color=BORDER
        )
        log_card.pack(fill="both", expand=True)

        self.log_text = ctk.CTkTextbox(
            log_card, font=("Consolas", 11),
            fg_color=BG_CARD, text_color=FG_TEXT,
            corner_radius=10, wrap="word",
            scrollbar_button_color=BG_INPUT,
            scrollbar_button_hover_color=BG_HOVER,
            state="disabled"
        )
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Tags de cor
        self.log_text.tag_config("success", foreground=SUCCESS)
        self.log_text.tag_config("warning", foreground=WARNING)
        self.log_text.tag_config("error", foreground=ERROR)
        self.log_text.tag_config("info", foreground=ACCENT)
        self.log_text.tag_config("muted", foreground=FG_MUTED)
        self.log_text.tag_config("separator", foreground=BORDER)

        # ── Banner de atualização (oculto por padrão) ──
        self.update_banner = ctk.CTkFrame(self.root_frame, fg_color=BG_CARD,
                                           corner_radius=10, border_width=1,
                                           border_color=ACCENT_DIM)
        # Não empacotamos agora — será exibido se houver atualização

        # ── Footer (sempre visível) ──
        self.footer = ctk.CTkLabel(
            self.root_frame, text=f"DivitorPDF v{APP_VERSION}  •  Powered by Zonninet",
            font=(FONT_FAMILY, 12), text_color="#484f58"
        )
        self.footer.pack(pady=(8, 0))

        # ── Frame do Leia-me (criado mas não exibido) ──
        self.readme_frame = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        self._build_readme_content()

        # ── Frame de Perfis (criado mas não exibido) ──
        self.profiles_frame = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        self._build_profiles_editor()

    def _build_readme_content(self):
        """Constrói o conteúdo do Leia-me no frame integrado."""
        frame = self.readme_frame

        content = ctk.CTkTextbox(
            frame, font=(FONT_FAMILY, 12),
            fg_color=BG_CARD, text_color=FG_TEXT,
            corner_radius=12, wrap="word",
            scrollbar_button_color=BG_INPUT,
            scrollbar_button_hover_color=BG_HOVER
        )
        content.pack(fill="both", expand=True)

        # Tags — usa _textbox (tk.Text interno) para contornar restrição de font no CTkTextbox
        tb = content._textbox
        tb.tag_configure("title", foreground=ACCENT, font=(FONT_FAMILY, 16, "bold"))
        tb.tag_configure("section", foreground=FG_TEXT, font=(FONT_FAMILY, 14, "bold"))
        tb.tag_configure("body", foreground=FG_TEXT, font=(FONT_FAMILY, 12))
        tb.tag_configure("muted", foreground=FG_MUTED, font=(FONT_FAMILY, 11))
        tb.tag_configure("bullet", foreground=ACCENT, font=(FONT_FAMILY, 12))
        tb.tag_configure("warn", foreground=WARNING, font=(FONT_FAMILY, 12))

        def add(text, tag="body"):
            content.insert("end", text + "\n", tag)

        def sep():
            content.insert("end", "\n")

        add("DivitorPDF v1.0", "title")
        add("Separador de PDFs por Nome", "muted")
        sep()

        add("━━━  O QUE FAZ  ━━━", "section")
        sep()
        add("O DivitorPDF divide um arquivo PDF que contém vários")
        add("PDFs (um por página) em arquivos individuais,")
        add("renomeando cada arquivo automaticamente com o nome do")
        add("funcionário encontrado na página.")
        sep()
        add("  Exemplo:", "muted")
        add("  ENTRADA: contracheques_fev.pdf  (10 páginas)", "muted")
        add("  SAÍDA:   Ana Beatriz Souza.pdf", "muted")
        add("           Bruno Henrique Lima.pdf", "muted")
        add("           Carla Vitória Santos.pdf  ...", "muted")
        sep()

        add("━━━  COMO USAR  ━━━", "section")
        sep()
        add("  1.  Clique na área de drop ou arraste um PDF", "bullet")
        add("  2.  Escolha a pasta de saída (ou use a sugerida)", "bullet")
        add("  3.  Clique em  ✂️ DIVIDIR PDF", "bullet")
        add("  4.  Acompanhe pelo log e barra de progresso", "bullet")
        add("  5.  Clique em  📂 Abrir Pasta  para ver os arquivos", "bullet")
        sep()

        add("━━━  RÓTULOS RECONHECIDOS  ━━━", "section")
        sep()
        add("O programa procura estes rótulos no texto da página:")
        sep()
        add("  •  Func.: 012437 - NOME", "bullet")
        add("  •  Func.: NOME", "bullet")
        add("  •  Funcionário: 012437 - NOME", "bullet")
        add("  •  Funcionário: NOME", "bullet")
        add("  •  Nome: NOME", "bullet")
        add("  •  Nome do Funcionário: NOME", "bullet")
        add("  •  Empregado: NOME", "bullet")
        add("  •  Colaborador: NOME", "bullet")
        add("  •  Trabalhador: NOME", "bullet")
        add("  •  Servidor: NOME", "bullet")
        sep()
        add("Se nenhum for encontrado, o arquivo é salvo como")
        add("Pagina_001.pdf, Pagina_002.pdf, etc.")
        sep()

        add("━━━  LIMITES  ━━━", "section")
        sep()
        add("  •  Sem limite fixo de páginas", "bullet")
        add("  •  PDFs grandes podem levar mais tempo", "bullet")
        add("  •  Depende da memória RAM disponível", "bullet")
        sep()

        add("━━━  LIMITAÇÕES  ━━━", "section")
        sep()
        add("  ⚠  PDF precisa ter texto selecionável", "warn")
        add("     PDFs que são apenas imagens escaneadas")
        add("     não funcionam. O contracheque precisa ter")
        add("     texto copiável (gerado por sistema digital).")
        sep()
        add("  ⚠  Apenas rótulos listados acima", "warn")
        add("     Outros formatos podem não ser reconhecidos.")
        sep()
        add("  ⚠  Nomes duplicados", "warn")
        add("     Se dois funcionários tiverem o mesmo nome,")
        add("     será adicionado (2), (3), etc.")
        sep()
        add("  ⚠  Idioma: Português", "warn")
        add("     Projetado para PDFs em PT-BR.")
        sep()

        content.configure(state="disabled")

    def _switch_view(self, target: str):
        """Troca a view ativa: 'main', 'readme' ou 'profiles'."""
        # Esconder view atual
        if self._current_view == "main":
            self.content_frame.pack_forget()
        elif self._current_view == "readme":
            self.readme_frame.pack_forget()
        elif self._current_view == "profiles":
            self.profiles_frame.pack_forget()

        # Mostrar view alvo
        if target == "main":
            self.content_frame.pack(fill="both", expand=True, before=self.footer)
            self.btn_readme.configure(text="ℹ️  Leia-me")
            self.btn_profiles.configure(text="⚙️  Perfis")
            self.subtitle.configure(text="Separador de PDFs")
        elif target == "readme":
            self.readme_frame.pack(fill="both", expand=True, before=self.footer)
            self.btn_readme.configure(text="←  Voltar")
            self.btn_profiles.configure(text="⚙️  Perfis")
            self.subtitle.configure(text="Leia-me")
        elif target == "profiles":
            self._refresh_profiles_list()
            self.profiles_frame.pack(fill="both", expand=True, before=self.footer)
            self.btn_profiles.configure(text="←  Voltar")
            self.btn_readme.configure(text="ℹ️  Leia-me")
            self.subtitle.configure(text="Gerenciar Perfis")

        self._current_view = target

    def _toggle_readme(self):
        """Alterna entre a view principal e o Leia-me."""
        if self._current_view == "readme":
            self._switch_view("main")
        else:
            self._switch_view("readme")

    def _toggle_profiles(self):
        """Alterna entre a view principal e o editor de perfis."""
        if self._current_view == "profiles":
            self._switch_view("main")
        else:
            self._switch_view("profiles")

    def _build_profiles_editor(self):
        """Constrói o editor de perfis integrado."""
        frame = self.profiles_frame

        # ── Seção: Criar novo perfil ──
        create_card = ctk.CTkFrame(frame, fg_color=BG_CARD, corner_radius=12,
                                    border_width=1, border_color=BORDER)
        create_card.pack(fill="x", pady=(0, 14))

        create_inner = ctk.CTkFrame(create_card, fg_color="transparent")
        create_inner.pack(fill="x", padx=20, pady=16)

        ctk.CTkLabel(
            create_inner, text="➕  Criar Novo Perfil",
            font=(FONT_FAMILY, 15, "bold"), text_color=FG_TEXT
        ).pack(anchor="w", pady=(0, 12))

        # Nome do perfil
        name_row = ctk.CTkFrame(create_inner, fg_color="transparent")
        name_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            name_row, text="Nome do Perfil:",
            font=(FONT_FAMILY, 12), text_color=FG_MUTED
        ).pack(side="left", padx=(0, 8))

        self.profile_name_entry = ctk.CTkEntry(
            name_row, placeholder_text="Ex: Informe de Rendimento",
            font=(FONT_FAMILY, 12), height=36,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=FG_TEXT, placeholder_text_color=FG_MUTED,
            corner_radius=8
        )
        self.profile_name_entry.pack(side="left", fill="x", expand=True)

        # Rótulos
        ctk.CTkLabel(
            create_inner, text="Rótulos de busca (um por linha):",
            font=(FONT_FAMILY, 12), text_color=FG_MUTED
        ).pack(anchor="w", pady=(4, 4))

        labels_hint = ctk.CTkLabel(
            create_inner,
            text="💡 Escreva os rótulos que aparecem antes do nome no documento. Ex: Beneficiário:, Paciente:, Cliente:",
            font=(FONT_FAMILY, 10), text_color=FG_MUTED, wraplength=600, anchor="w"
        )
        labels_hint.pack(anchor="w", pady=(0, 6))

        self.labels_textbox = ctk.CTkTextbox(
            create_inner, font=(FONT_FAMILY, 12), height=120,
            fg_color=BG_INPUT, text_color=FG_TEXT,
            corner_radius=8, wrap="word",
            scrollbar_button_color=BG_HOVER,
            scrollbar_button_hover_color=ACCENT_DIM
        )
        self.labels_textbox.pack(fill="x", pady=(0, 12))

        # Botão salvar
        ctk.CTkButton(
            create_inner, text="💾  Salvar Perfil",
            font=(FONT_FAMILY, 13, "bold"), height=40,
            corner_radius=8,
            fg_color=ACCENT_DIM, hover_color=ACCENT,
            text_color="#ffffff",
            command=self._save_new_profile
        ).pack(fill="x")

        # ── Seção: Perfis existentes ──
        ctk.CTkLabel(
            frame, text="📋  Perfis Salvos",
            font=(FONT_FAMILY, 15, "bold"), text_color=FG_TEXT
        ).pack(anchor="w", pady=(6, 8))

        self.profiles_list_frame = ctk.CTkScrollableFrame(
            frame, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
            scrollbar_button_color=BG_INPUT,
            scrollbar_button_hover_color=BG_HOVER
        )
        self.profiles_list_frame.pack(fill="both", expand=True)

    def _refresh_profiles_list(self):
        """Atualiza a lista de perfis exibida no editor."""
        # Limpar lista atual
        for widget in self.profiles_list_frame.winfo_children():
            widget.destroy()

        # Perfil padrão (não editável)
        self._add_profile_card(DEFAULT_PROFILE_NAME, DEFAULT_LABELS, is_default=True)

        # Perfis customizados
        data = load_profiles()
        for name, info in sorted(data.get("custom_profiles", {}).items()):
            self._add_profile_card(name, info.get("labels", []), is_default=False)

        if not data.get("custom_profiles"):
            ctk.CTkLabel(
                self.profiles_list_frame,
                text="Nenhum perfil customizado criado ainda.",
                font=(FONT_FAMILY, 12), text_color=FG_MUTED
            ).pack(pady=20)

    def _add_profile_card(self, name: str, labels: list[str], is_default: bool):
        """Adiciona um card de perfil na lista."""
        card = ctk.CTkFrame(self.profiles_list_frame, fg_color=BG_INPUT, corner_radius=8)
        card.pack(fill="x", padx=8, pady=4)

        card_inner = ctk.CTkFrame(card, fg_color="transparent")
        card_inner.pack(fill="x", padx=12, pady=10)

        # Nome
        icon = "🔒" if is_default else "📝"
        ctk.CTkLabel(
            card_inner, text=f"{icon}  {name}",
            font=(FONT_FAMILY, 13, "bold"), text_color=FG_TEXT
        ).pack(side="left")

        # Botão excluir (apenas para customizados)
        if not is_default:
            ctk.CTkButton(
                card_inner, text="✕", width=30, height=28,
                font=(FONT_FAMILY, 13, "bold"), corner_radius=6,
                fg_color=BG_CARD, hover_color=ERROR,
                border_width=1, border_color=BORDER,
                text_color=FG_MUTED,
                command=lambda n=name: self._delete_profile(n)
            ).pack(side="right")

        # Rótulos
        labels_text = ", ".join(labels[:6])
        if len(labels) > 6:
            labels_text += f" ... (+{len(labels) - 6})"
        ctk.CTkLabel(
            card, text=f"   Rótulos: {labels_text}",
            font=(FONT_FAMILY, 11), text_color=FG_MUTED, anchor="w"
        ).pack(fill="x", padx=12, pady=(0, 8))

    def _save_new_profile(self):
        """Salva um novo perfil customizado."""
        name = self.profile_name_entry.get().strip()
        labels_raw = self.labels_textbox.get("1.0", "end").strip()

        if not name:
            self._log("⚠️  Insira um nome para o perfil.", "warning")
            return

        if name == DEFAULT_PROFILE_NAME:
            self._log("⚠️  Não é possível sobrescrever o perfil padrão.", "warning")
            return

        # Parsear rótulos (um por linha, ignorar vazios)
        labels = [l.strip() for l in labels_raw.split("\n") if l.strip()]

        if not labels:
            self._log("⚠️  Adicione pelo menos um rótulo.", "warning")
            return

        # Salvar
        data = load_profiles()
        data["custom_profiles"][name] = {"labels": labels}
        save_profiles(data)

        # Atualizar dropdown
        self._refresh_profile_dropdown()

        # Limpar campos
        self.profile_name_entry.delete(0, "end")
        self.labels_textbox.delete("1.0", "end")

        # Atualizar lista
        self._refresh_profiles_list()

        self._log(f"✅  Perfil '{name}' salvo com {len(labels)} rótulo(s).", "success")

    def _delete_profile(self, name: str):
        """Exclui um perfil customizado."""
        data = load_profiles()
        if name in data.get("custom_profiles", {}):
            del data["custom_profiles"][name]
            save_profiles(data)

            # Se o perfil excluído era o selecionado, voltar ao padrão
            if self.profile_var.get() == name:
                self.profile_var.set(DEFAULT_PROFILE_NAME)

            self._refresh_profile_dropdown()
            self._refresh_profiles_list()
            self._log(f"🗑️  Perfil '{name}' excluído.", "info")

    def _refresh_profile_dropdown(self):
        """Atualiza as opções do dropdown de perfis."""
        names = get_all_profile_names()
        self.profile_dropdown.configure(values=names)
        if self.profile_var.get() not in names:
            self.profile_var.set(DEFAULT_PROFILE_NAME)

    def _get_active_patterns(self) -> list[str] | None:
        """Retorna os padrões regex do perfil ativo. None = usar padrão."""
        selected = self.profile_var.get()
        if selected == DEFAULT_PROFILE_NAME:
            return None  # usa DEFAULT_PATTERNS interno

        data = load_profiles()
        profile = data.get("custom_profiles", {}).get(selected)
        if profile and profile.get("labels"):
            return labels_to_patterns(profile["labels"])
        return None

    # ── Eventos ──

    def _select_pdf(self):
        path = filedialog.askopenfilename(
            title="Selecionar PDF",
            filetypes=[("Arquivos PDF", "*.pdf"), ("Todos", "*.*")]
        )
        if path:
            self.pdf_path = path
            filename = os.path.basename(path)
            self.drop_label.configure(text="Arquivo selecionado:")
            self.file_label.configure(text=filename)
            self.drop_icon.configure(text="✅")
            self.drop_card.configure(border_color=ACCENT_DIM)

            if not self.output_dir:
                default_out = os.path.join(os.path.dirname(path), "PDFs_Separados")
                self.output_dir = default_out
                self.out_entry.delete(0, "end")
                self.out_entry.insert(0, default_out)

    def _select_output(self):
        path = filedialog.askdirectory(title="Selecionar Pasta de Saída")
        if path:
            self.output_dir = path
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, path)

    def _on_drop(self, event):
        path = event.data.strip('{}')
        if path.lower().endswith('.pdf'):
            self.pdf_path = path
            filename = os.path.basename(path)
            self.drop_label.configure(text="Arquivo selecionado:")
            self.file_label.configure(text=filename)
            self.drop_icon.configure(text="✅")
            self.drop_card.configure(border_color=ACCENT_DIM)

            if not self.output_dir:
                default_out = os.path.join(os.path.dirname(path), "PDFs_Separados")
                self.output_dir = default_out
                self.out_entry.delete(0, "end")
                self.out_entry.insert(0, default_out)
        else:
            self.drop_label.configure(text="Formato inválido — use .pdf")
            self.drop_icon.configure(text="❌")
            self.drop_card.configure(border_color=ERROR)

    def _on_drag_enter(self, event):
        self.drop_card.configure(border_color=ACCENT)

    def _on_drag_leave(self, event):
        self.drop_card.configure(border_color=BORDER)

    def _open_output_folder(self):
        if self.last_output_dir and os.path.isdir(self.last_output_dir):
            os.startfile(self.last_output_dir)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _log(self, message: str, tag: str = None):
        """Adiciona mensagem ao log (thread-safe)."""
        def _append():
            self.log_text.configure(state="normal")
            if tag:
                self.log_text.insert("end", message + "\n", tag)
            else:
                self.log_text.insert("end", message + "\n")
            self.log_text.configure(state="disabled")
            self.log_text.see("end")
        self.root.after(0, _append)

    def _update_progress(self, current: int, total: int):
        """Atualiza barra de progresso (thread-safe)."""
        def _update():
            pct = current / total
            self.progress_bar.set(pct)
            self.progress_label.configure(text=f"Página {current} de {total}  •  {pct * 100:.0f}%")
            self.btn_split.configure(text=f"⏳  Processando {current}/{total}...")
        self.root.after(0, _update)

    def _start_split(self):
        if self.is_processing:
            return

        pdf = self.pdf_path
        output = self.out_entry.get().strip()

        if not pdf:
            self._show_inline_alert("Selecione um arquivo PDF.", "warning")
            return
        if not os.path.isfile(pdf):
            self._show_inline_alert(f"Arquivo não encontrado: {pdf}", "error")
            return
        if not output:
            self._show_inline_alert("Selecione a pasta de saída.", "warning")
            return

        # Esconder banner anterior
        self._dismiss_result_banner()

        self.output_dir = output

        # Limpar e resetar
        self._clear_log()
        self.progress_bar.set(0)
        self.progress_label.configure(text="")

        self.is_processing = True
        self.btn_split.configure(
            text="⏳  Processando...",
            fg_color=BG_INPUT, hover_color=BG_INPUT,
            state="disabled"
        )
        self.btn_open_folder.configure(state="disabled")

        patterns = self._get_active_patterns()
        profile_name = self.profile_var.get()
        self._log(f"🏷️  Perfil: {profile_name}", "info")

        thread = threading.Thread(
            target=self._run_split, args=(pdf, output, patterns), daemon=True
        )
        thread.start()

    def _run_split(self, pdf_path: str, output_dir: str, custom_patterns=None):
        try:
            sucesso, falhas, total = split_pdf(
                pdf_path, output_dir,
                progress_callback=self._update_progress,
                log_callback=self._log,
                custom_patterns=custom_patterns
            )

            def _show_result():
                self.is_processing = False
                self.last_output_dir = output_dir
                self.btn_split.configure(
                    text="✂️   DIVIDIR PDF",
                    fg_color=ACCENT_DIM, hover_color=ACCENT,
                    state="normal"
                )
                self.btn_open_folder.configure(
                    state="normal", text_color=FG_TEXT,
                    fg_color=BG_INPUT
                )

                # Mostrar banner de resultado integrado na janela
                self._show_result_banner(sucesso, falhas, total, output_dir)

            self.root.after(0, _show_result)

        except Exception as e:
            def _show_error():
                self.is_processing = False
                self.btn_split.configure(
                    text="✂️   DIVIDIR PDF",
                    fg_color=ACCENT_DIM, hover_color=ACCENT,
                    state="normal"
                )
                self._log(f"❌ ERRO: {str(e)}", "error")
            self.root.after(0, _show_error)

    # ── Auto-update ──

    def _check_for_updates(self):
        """Verifica se há atualização disponível no GitHub (em background)."""
        try:
            import urllib.request
            req = urllib.request.Request(GITHUB_API, headers={"User-Agent": "DivitorPDF"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())

            latest_tag = data.get("tag_name", "").lstrip("v")
            if not latest_tag:
                return

            # Comparar versões
            if self._version_newer(latest_tag, APP_VERSION):
                download_url = data.get("html_url", "")
                self.root.after(0, lambda: self._show_update_banner(latest_tag, download_url))
        except Exception:
            pass  # Silencioso se não tiver internet

    def _version_newer(self, remote: str, local: str) -> bool:
        """Compara versões semânticas (ex: '1.2.0' > '1.1.0')."""
        try:
            r = [int(x) for x in remote.split(".")]
            l = [int(x) for x in local.split(".")]
            return r > l
        except ValueError:
            return remote != local

    def _show_update_banner(self, version: str, url: str):
        """Mostra banner de atualização disponível."""
        banner = self.update_banner
        banner.pack(fill="x", pady=(8, 0), before=self.footer)

        inner = ctk.CTkFrame(banner, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=10)

        ctk.CTkLabel(
            inner, text=f"🔄  Nova versão disponível: v{version}",
            font=(FONT_FAMILY, 12, "bold"), text_color=ACCENT
        ).pack(side="left")

        ctk.CTkButton(
            inner, text="Baixar Atualização", width=150, height=30,
            font=(FONT_FAMILY, 11, "bold"), corner_radius=6,
            fg_color=ACCENT_DIM, hover_color=ACCENT,
            text_color="#ffffff",
            command=lambda: webbrowser.open(url)
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            inner, text="✕", width=28, height=28,
            font=(FONT_FAMILY, 12), corner_radius=6,
            fg_color="transparent", hover_color=BG_HOVER,
            text_color=FG_MUTED,
            command=lambda: banner.pack_forget()
        ).pack(side="right")

    def run(self):
        self.root.mainloop()


# ─── Ponto de entrada ───────────────────────────────────────────────────────

if __name__ == "__main__":
    app = DivitorPDFApp()
    app.run()
