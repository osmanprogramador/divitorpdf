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
from PIL import Image


# ─── Design Tokens ──────────────────────────────────────────────────────────
FONT_FAMILY   = "Segoe UI"

THEMES = {
    "dark": {
        "BG_MAIN":      "#0d1117",
        "BG_CARD":      "#161b22",
        "BG_INPUT":     "#21262d",
        "BG_HOVER":     "#292e36",
        "ACCENT":       "#58a6ff",
        "ACCENT_HOVER": "#79c0ff",
        "ACCENT_DIM":   "#1f6feb",
        "FG_TEXT":      "#e6edf3",
        "FG_MUTED":     "#8b949e",
        "SUCCESS":      "#3fb950",
        "WARNING":      "#d29922",
        "ERROR":        "#f85149",
        "BORDER":       "#30363d",
    },
    "light": {
        "BG_MAIN":      "#f0f2f5",
        "BG_CARD":      "#ffffff",
        "BG_INPUT":     "#e8ecf0",
        "BG_HOVER":     "#dde1e7",
        "ACCENT":       "#0969da",
        "ACCENT_HOVER": "#0550ae",
        "ACCENT_DIM":   "#0969da",
        "FG_TEXT":      "#1c2128",
        "FG_MUTED":     "#57606a",
        "SUCCESS":      "#1a7f37",
        "WARNING":      "#9a6700",
        "ERROR":        "#cf222e",
        "BORDER":       "#c8ccd0",
    }
}

_ACTIVE_THEME = "dark"

def _t(key):
    """Retorna o valor do token de cor ativo."""
    return THEMES[_ACTIVE_THEME][key]

# ── Atalhos globais (compatibilidade) ──
BG_MAIN       = THEMES["dark"]["BG_MAIN"]
BG_CARD       = THEMES["dark"]["BG_CARD"]
BG_INPUT      = THEMES["dark"]["BG_INPUT"]
BG_HOVER      = THEMES["dark"]["BG_HOVER"]
ACCENT        = THEMES["dark"]["ACCENT"]
ACCENT_HOVER  = THEMES["dark"]["ACCENT_HOVER"]
ACCENT_DIM    = THEMES["dark"]["ACCENT_DIM"]
FG_TEXT       = THEMES["dark"]["FG_TEXT"]
FG_MUTED      = THEMES["dark"]["FG_MUTED"]
SUCCESS       = THEMES["dark"]["SUCCESS"]
WARNING       = THEMES["dark"]["WARNING"]
ERROR         = THEMES["dark"]["ERROR"]
BORDER        = THEMES["dark"]["BORDER"]

APP_VERSION   = "1.0.0"
GITHUB_OWNER  = "osmanprogramador"
GITHUB_REPO   = "divitorpdf"
GITHUB_API    = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
import sys

def _base_path():
    """Retorna caminho base — compatível com PyInstaller."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

PROFILES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.json")
ICON_FILE        = os.path.join(_base_path(), "icons", "divitor_icon.ico")
LOGO_FILE_DARK   = os.path.join(_base_path(), "icons", "divitor_icon_256.png")
LOGO_FILE_LIGHT  = os.path.join(_base_path(), "icons", "divitor_logo_horizontal.png")

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

# Configurações iniciais do perfil padrão
DEFAULT_PROFILE_DATA = {
    "labels": DEFAULT_LABELS,
    "period_regex": r'Per[ií]odo[:\s]+(\d{2})/(\d{4})',
    "dept_regex": r'Depto\.[:\s]*\d+\s*[-–]\s*(.+)',
    "period_label": "Período:",
    "dept_label": "Depto.:",
    "naming": {
        "active": True,
        "template": "{PERIODO}_{PREFIXO}_{DEPTO}_{SETOR}_{TIPO}_{NOME}",
        "prefix": "EMPRESA_RH",
        "sector": "ADM",
        "doc_type": "DEMONSTRATIVOS"
    }
}



def load_profiles() -> dict:
    """Carrega perfis customizados do arquivo JSON."""
    profiles_data = {"profiles": {DEFAULT_PROFILE_NAME: DEFAULT_PROFILE_DATA}, "dept_mapping": {}}
    
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                # Migração/Compatibilidade
                if "profiles" in saved_data:
                    profiles_data["profiles"].update(saved_data["profiles"])
                elif "custom_profiles" in saved_data:
                    # Converter do formato antigo
                    for name, info in saved_data["custom_profiles"].items():
                        new_info = DEFAULT_PROFILE_DATA.copy()
                        new_info["labels"] = info.get("labels", [])
                        profiles_data["profiles"][name] = new_info
                
                if "dept_mapping" in saved_data:
                    profiles_data["dept_mapping"] = saved_data["dept_mapping"]
                elif "naming_config" in saved_data and "dept_mapping" in saved_data["naming_config"]:
                    profiles_data["dept_mapping"] = saved_data["naming_config"]["dept_mapping"]
                    
        except (json.JSONDecodeError, IOError):
            pass
            
    return profiles_data


def save_profiles(data: dict):
    """Salva perfis e mapeamentos no arquivo JSON."""
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all_profile_names() -> list[str]:
    """Retorna lista de nomes de todos os perfis."""
    data = load_profiles()
    return sorted(data.get("profiles", {}).keys())


def labels_to_patterns(labels: list[str]) -> list[str]:
    """Converte rótulos simples do usuário em padrões regex."""
    patterns = []
    for label in labels:
        escaped = re.escape(label.strip().rstrip(":"))
        pattern = escaped + r'[\.: ]*\s*(?:\d+\s*[-–]\s*)?(.+)'
        patterns.append(pattern)
    return patterns


# ─── Lógica de extração ─────────────────────────────────────────────────────

def extract_period(page_text: str, pattern: str = None) -> str:
    """Extrai o período usando o padrão fornecido pelo perfil."""
    if not page_text:
        return "PERIODO"
    
    pattern = pattern or r'Per[ií]odo[:\s]+(\d{2})/(\d{4})'
    
    # Se for o padrão MM/AAAA, converter para AAAAMM
    if '(\\d{2})/(\\d{4})' in pattern or r'(\d{2})/(\d{4})' in pattern:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            mes, ano = match.groups()
            return f"{mes}{ano}"
            
    # Busca genérica pelo padrão do perfil
    match = re.search(pattern, page_text, re.IGNORECASE)
    if match:
        return match.group(1) if match.groups() else match.group(0)
        
    # Fallback genérico de ano se falhar
    match_gen = re.search(r'\b(20\d{2})\b', page_text)
    if match_gen:
        return match_gen.group(1)

    return "PERIODO"


def extract_department(page_text: str, pattern: str = None) -> str:
    """Extrai o nome do departamento usando o padrão do perfil."""
    if not page_text or not pattern:
        return "DEPTO"
    
    match = re.search(pattern, page_text, re.IGNORECASE)
    if match:
        dept = match.group(1).strip()
        # Cortar se houver delimitadores comuns de outras colunas
        dept = re.split(r'\s{2,}|\t|Admiss[ãa]o|CPF|Matr[ií]cula', dept, flags=re.IGNORECASE)[0].strip()
        return dept
    return "DEPTO"


def get_dept_sigla(dept_name: str, mapping: dict) -> str:
    """Retorna a sigla do departamento baseada no mapeamento ou nas 3 primeiras letras."""
    if not dept_name or dept_name == "DEPTO":
        return "DEPTO"
    
    # Busca exata no mapeamento
    for full_name, sigla in mapping.items():
        if full_name.upper() in dept_name.upper():
            return sigla
            
    # Fallback: Primeiras 3 letras ou palavras
    words = dept_name.split()
    if len(words) >= 2:
        return f"{words[0][:3].upper()}_{words[1][:3].upper()}"
    return dept_name[:3].upper()



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
              log_callback=None, profile_data: dict = None,
              dept_mapping: dict = None):
    """
    Divide o PDF e renomear individualmente com base no perfil.
    """
    if log_callback:
        log_callback(f"📂  Abrindo: {os.path.basename(pdf_path)}", "info")

    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    if log_callback:
        log_callback(f"📄  Total de páginas: {total_pages}", "info")

    os.makedirs(output_dir, exist_ok=True)
    
    profile_data = profile_data or DEFAULT_PROFILE_DATA
    dept_mapping = dept_mapping or {}
    
    naming_config = profile_data.get("naming", {})
    use_naming = naming_config.get("active", False)
    period_regex = profile_data.get("period_regex")
    dept_regex = profile_data.get("dept_regex")
    custom_patterns = labels_to_patterns(profile_data.get("labels", []))

    if use_naming and log_callback:
        log_callback("📛  Nomenclatura personalizada ATIVADA", "info")

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

            # Extração de dados
            name = extract_employee_name(text, custom_patterns)
            
            if use_naming:
                period = extract_period(text, period_regex)
                dept = extract_department(text, dept_regex)
                dept_sig = get_dept_sigla(dept, dept_mapping)
                
                prefix   = naming_config.get("prefix", "").strip()
                sector   = naming_config.get("sector", "").strip()
                doc_type = naming_config.get("doc_type", "").strip()

                # Monta o nome automaticamente — partes vazias são ignoradas
                parts = [p for p in [period, prefix, sector, dept_sig, doc_type, name or "Desconhecido"] if p]
                final_name = "_".join(parts)
                
                final_name = sanitize_filename(final_name)
            else:
                final_name = name

            if name:
                output_path = get_unique_filename(output_dir, final_name)
                if log_callback:
                    log_callback(f"✅  Pág. {page_num}: {name}", "success")
                sucesso += 1
            else:
                if use_naming:
                    fallback_base = f"{extract_period(text, period_regex)}_FALHA_{page_num:03d}"
                else:
                    fallback_base = f"Pagina_{page_num:03d}"
                    
                output_path = get_unique_filename(output_dir, fallback_base)
                if log_callback:
                    log_callback(f"⚠️  Pág. {page_num}: Nome não encontrado", "warning")
                falhas += 1

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
        self._current_theme = "dark"
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        
        # Inicializar Drag and Drop se disponível
        if HAS_DND:
            try:
                self.root.tk.call('package', 'require', 'tkdnd')
            except Exception:
                # Se falhar ao carregar a extensão Tcl, desativa o DND globalmente
                import __main__
                if hasattr(__main__, 'HAS_DND'):
                    __main__.HAS_DND = False
                # Fallback local para esta instância
                nonlocal_has_dnd = False
                # No entanto, HAS_DND é global no módulo, vamos tentar atualizar lá
                globals()['HAS_DND'] = False
        self.root.title("DivitorPDF")
        self.root.geometry("960x780")
        self.root.configure(fg_color=BG_MAIN)
        self.root.resizable(True, True)
        self.root.minsize(800, 680)

        # Ícone da janela
        if os.path.exists(ICON_FILE):
            try:
                self.root.iconbitmap(ICON_FILE)
            except Exception:
                pass

        # Variáveis
        self.pdf_path = ""
        self.output_dir = ""
        self.is_processing = False
        self.last_output_dir = None

        # Variáveis Divisão Simples
        self.s_pdf_path = ""
        self.s_output_dir = ""

        # Estado de navegação
        self._current_page = "split_rename"
        self._in_readme = False
        self.result_banner_visible = False

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
        header.pack(fill="x", pady=(0, 14))

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left")

        # ── Logo: ícone quadrado + texto (ambos os temas) ──
        try:
            _icon_pil = Image.open(LOGO_FILE_DARK)
            _icon_ctk = ctk.CTkImage(light_image=_icon_pil, dark_image=_icon_pil, size=(40, 40))
            self.logo_label = ctk.CTkLabel(title_frame, image=_icon_ctk, text="")
            self._icon_ctk_ref = _icon_ctk
            self.logo_label.pack(side="left", padx=(0, 10))
        except Exception:
            self.logo_label = None

        self.title_label = ctk.CTkLabel(title_frame, text="DivitorPDF",
                                         font=(FONT_FAMILY, 24, "bold"), text_color=FG_TEXT)
        self.title_label.pack(side="left")

        self.subtitle = ctk.CTkLabel(title_frame, text="Dividir e Renomear",
                                      font=(FONT_FAMILY, 12), text_color=FG_MUTED)
        self.subtitle.pack(side="left", padx=(12, 0))

        # Navegação no Header
        nav = ctk.CTkFrame(header, fg_color="transparent")
        nav.pack(side="right")

        self.btn_nav_rename = ctk.CTkButton(
            nav, text="📝  Renomear", width=110, height=36,
            font=(FONT_FAMILY, 12, "bold"), corner_radius=8,
            fg_color=BG_HOVER, hover_color=BG_HOVER, # Inicia ativo (padrão)
            border_width=1, border_color=BORDER,
            text_color=ACCENT,
            command=lambda: self._toggle_page("split_rename")
        )
        self.btn_nav_rename.pack(side="left", padx=4)

        self.btn_nav_simple = ctk.CTkButton(
            nav, text="✂️  Simples", width=100, height=36,
            font=(FONT_FAMILY, 12, "bold"), corner_radius=8,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_TEXT,
            command=lambda: self._toggle_page("split_simple")
        )
        self.btn_nav_simple.pack(side="left", padx=4)

        self.btn_nav_merge = ctk.CTkButton(
            nav, text="📎  Juntar", width=90, height=36,
            font=(FONT_FAMILY, 12, "bold"), corner_radius=8,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_TEXT,
            command=lambda: self._toggle_page("merge")
        )
        self.btn_nav_merge.pack(side="left", padx=4)

        self.btn_nav_profiles = ctk.CTkButton(
            nav, text="🏷️  Perfis", width=90, height=36,
            font=(FONT_FAMILY, 12, "bold"), corner_radius=8,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_TEXT,
            command=lambda: self._toggle_page("profiles")
        )
        self.btn_nav_profiles.pack(side="left", padx=4)

        self.btn_readme = ctk.CTkButton(
            nav, text="ℹ️  Leia-me", width=90, height=36,
            font=(FONT_FAMILY, 11, "bold"), corner_radius=8,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_TEXT,
            command=self._toggle_readme
        )
        self.btn_readme.pack(side="left", padx=(4, 0))

        self.btn_theme = ctk.CTkButton(
            nav, text="Tema ●", width=80, height=36,
            font=(FONT_FAMILY, 11, "bold"), corner_radius=8,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_TEXT,
            command=self._toggle_theme
        )
        self.btn_theme.pack(side="left", padx=(4, 0))

        # ── Área de Conteúdo (Dinâmica) ──
        self.content_area = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        self.content_area.pack(fill="both", expand=True)

        self._pages = {}

        # ── Página: Dividir e Renomear (Principal) ──
        self.split_rename_frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self._pages["split_rename"] = self.split_rename_frame
        self._build_split_rename_page()

        # ── Banner de atualização (oculto por padrão) ──
        self.update_banner = ctk.CTkFrame(self.root_frame, fg_color=BG_CARD,
                                           corner_radius=10, border_width=1,
                                           border_color=ACCENT_DIM)

        # ── Footer (sempre visível) ──
        self.footer_row = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        self.footer_row.pack(fill="x", pady=(8, 0))

        self.footer = ctk.CTkLabel(
            self.footer_row, text=f"DivitorPDF v{APP_VERSION}  •  Powered by Zonninet",
            font=(FONT_FAMILY, 12), text_color=FG_MUTED
        )
        self.footer.pack(side="left")

        ctk.CTkButton(
            self.footer_row, text="❤️  Doar", width=80, height=26,
            font=(FONT_FAMILY, 11), corner_radius=6,
            fg_color="#4a1c1c", hover_color="#6b2b2b",
            border_width=1, border_color="#d63a3a",
            text_color="#f85149",
            command=lambda: webbrowser.open("https://link.mercadopago.com.br/divitorpdf")
        ).pack(side="right")

        # ── Outras Frames (Carregadas em background) ──

        # ── Página: Dividir Simples ──
        self.split_simple_frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self._pages["split_simple"] = self.split_simple_frame
        self._build_page_simple_split()

        self._build_page_merge()

        self.profiles_frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self._pages["profiles"] = self.profiles_frame
        self._build_profiles_editor()

        # ── Página padrão ──
        self.readme_frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self._build_readme_content()

        self.split_rename_frame.pack(fill="both", expand=True)

    def _build_split_rename_page(self):
        """Constrói a interface principal de divisão e renomeio (Centered)."""
        main = self.split_rename_frame

        # ── Perfil de Rótulos (Dropdown inline) ──
        profile_row = ctk.CTkFrame(main, fg_color="transparent")
        profile_row.pack(fill="x", pady=(0, 12))

        self._prof_lbl = ctk.CTkLabel(
            profile_row, text="🏷️   Perfil de Rótulos",
            font=(FONT_FAMILY, 12, "bold"), text_color=FG_TEXT
        )
        self._prof_lbl.pack(side="left")

        self.profile_var = ctk.StringVar(value=DEFAULT_PROFILE_NAME)
        _initial_profiles = get_all_profile_names() or [DEFAULT_PROFILE_NAME]
        self.profile_dropdown = ctk.CTkOptionMenu(
            profile_row, variable=self.profile_var,
            values=_initial_profiles,
            width=220, height=36, corner_radius=8,
            fg_color=BG_INPUT, button_color=BG_INPUT,
            button_hover_color=BG_HOVER, dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BG_HOVER, text_color=FG_TEXT,
            font=(FONT_FAMILY, 12)
        )
        self.profile_dropdown.pack(side="right")

        # ── Drop Zone (Card Central) ──
        self.drop_card = ctk.CTkFrame(
            main, fg_color=BG_CARD, corner_radius=12,
            border_width=2, border_color=BORDER
        )
        self.drop_card.pack(fill="x", pady=(0, 14))

        inner_drop = ctk.CTkFrame(self.drop_card, fg_color="transparent", height=140)
        inner_drop.pack(fill="x", padx=20, pady=20)
        inner_drop.pack_propagate(False)

        self.drop_icon = ctk.CTkLabel(
            inner_drop, text="📄", font=(FONT_FAMILY, 42), text_color=FG_MUTED
        )
        self.drop_icon.pack(pady=(10, 5))

        self.drop_label = ctk.CTkLabel(
            inner_drop, text="Clique ou arraste um PDF aqui",
            font=(FONT_FAMILY, 13), text_color=FG_MUTED
        )
        self.drop_label.pack()

        self.file_label = ctk.CTkLabel(
            inner_drop, text="", font=(FONT_FAMILY, 11), text_color=ACCENT
        )
        self.file_label.pack()

        # Bindings
        for widget in [self.drop_card, inner_drop, self.drop_icon, self.drop_label, self.file_label]:
            widget.bind("<Button-1>", lambda e: self._select_pdf())
            widget.configure(cursor="hand2")

        if HAS_DND:
            self.drop_card.drop_target_register(DND_FILES)
            self.drop_card.dnd_bind('<<Drop>>', self._on_drop)
            self.drop_card.dnd_bind('<<DragEnter>>', self._on_drag_enter)
            self.drop_card.dnd_bind('<<DragLeave>>', self._on_drag_leave)

        # ── Pasta de Saída ──
        out_row = ctk.CTkFrame(main, fg_color="transparent")
        out_row.pack(fill="x", pady=(0, 14))

        self._out_lbl = ctk.CTkLabel(
            out_row, text="📁  Pasta de Saída",
            font=(FONT_FAMILY, 12, "bold"), text_color=FG_TEXT
        )
        self._out_lbl.pack(anchor="w", pady=(0, 6))

        field_row = ctk.CTkFrame(out_row, fg_color="transparent")
        field_row.pack(fill="x")

        self.out_entry = ctk.CTkEntry(
            field_row, placeholder_text="Selecione onde os arquivos serão salvos...",
            font=(FONT_FAMILY, 12), height=40,
            fg_color=BG_INPUT, border_color=BORDER, text_color=FG_TEXT,
            placeholder_text_color=FG_MUTED, corner_radius=8
        )
        self.out_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_select_out = ctk.CTkButton(
            field_row, text="Selecionar", width=110, height=40,
            font=(FONT_FAMILY, 12, "bold"), corner_radius=8,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER, text_color=FG_TEXT,
            command=self._select_output
        )
        self.btn_select_out.pack(side="right")

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

        # ── Banner de resultado (oculto inicialmente) ──
        self.result_banner = ctk.CTkFrame(
            main, fg_color=BG_CARD, corner_radius=10,
            border_width=2, border_color=BORDER
        )
        # Não empacotado agora — _show_result_banner faz pack(before=_log_header)

        # ── Log de atividade ──
        self._log_header = ctk.CTkFrame(main, fg_color="transparent")
        self._log_header.pack(fill="x", pady=(6, 6))


        self._log_title_label = ctk.CTkLabel(
            self._log_header, text="📋 Log de Atividade",
            font=(FONT_FAMILY, 12, "bold"), text_color=FG_TEXT
        )
        self._log_title_label.pack(side="left")

        self.btn_clear_log = ctk.CTkButton(
            self._log_header, text="Limpar", width=70, height=28,
            font=(FONT_FAMILY, 11), corner_radius=6,
            fg_color="transparent", hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=FG_MUTED,
            command=self._clear_log
        )
        self.btn_clear_log.pack(side="right")

        self.log_card = ctk.CTkFrame(
            main, fg_color=BG_CARD, corner_radius=10,
            border_width=1, border_color=BORDER
        )
        self.log_card.pack(fill="both", expand=True)

        self.log_text = ctk.CTkTextbox(
            self.log_card, font=("Consolas", 11),
            fg_color=BG_CARD, text_color=FG_TEXT,
            corner_radius=10, wrap="word",
            scrollbar_button_color=BG_INPUT,
            scrollbar_button_hover_color=BG_HOVER,
            state="disabled"
        )
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

    def _start_split(self):
        """Inicia o processo de divisão em uma thread separada."""
        if self.is_processing:
            return

        pdf = self.pdf_path
        out = self.out_entry.get().strip()
        prof_name = self.profile_var.get()
        
        if not pdf:
            self._log("⚠️  Selecione um arquivo PDF primeiro.", "warning")
            return
        if not out:
            self._log("⚠️  Selecione uma pasta de saída.", "warning")
            return

        # Carregar perfil selecionado
        profiles = list_profiles()
        current_profile = next((p for p in profiles if p["name"] == prof_name), DEFAULT_PROFILE_DATA)
        
        # Desabilitar UI
        self.btn_split.configure(text="⏳ Processando...", state="disabled")
        self.btn_open_folder.configure(state="disabled")
        self.is_processing = True
        self.progress_bar.set(0)
        self.progress_label.configure(text="Iniciando extração...")
        
        # Iniciar thread
        threading.Thread(
            target=self._run_split,
            args=(pdf, out, current_profile),
            daemon=True
        ).start()

    def _toggle_page(self, target: str):
        """Alterna entre páginas a partir do header."""
        if hasattr(self, '_in_readme') and self._in_readme:
            self.readme_frame.pack_forget()
            self._in_readme = False
            self.btn_readme.configure(text="ℹ️  Leia-me", fg_color=BG_INPUT)
            self._current_page = ""  # força a página alvo ser exibida

        # Se já estiver nela, não faz nada
        if self._current_page == target:
            return

        # Esconde todas
        for page in self._pages.values():
            page.pack_forget()
        
        # Mostra a alvo
        self._pages[target].pack(fill="both", expand=True)
        self._current_page = target

        # Atualiza cores e estados dos botões
        nav_buttons = {
            "split_rename": self.btn_nav_rename,
            "split_simple": self.btn_nav_simple,
            "merge": self.btn_nav_merge,
            "profiles": self.btn_nav_profiles
        }

        for p_name, btn in nav_buttons.items():
            if p_name == target:
                btn.configure(fg_color=BG_HOVER, text_color=ACCENT)
            else:
                btn.configure(fg_color=BG_INPUT, text_color=FG_TEXT)
        if target == "profiles":
            self._refresh_profiles_list()
        elif target == "split_rename":
            self.subtitle.configure(text="Dividir e Renomear")
        elif target == "split_simple":
            self.subtitle.configure(text="Divisão Simples")
        elif target == "merge":
            self.subtitle.configure(text="Juntar PDFs")

    def _toggle_theme(self):

        """Alterna entre tema escuro e claro, atualizando toda a UI."""
        global BG_MAIN, BG_CARD, BG_INPUT, BG_HOVER, ACCENT, ACCENT_HOVER
        global ACCENT_DIM, FG_TEXT, FG_MUTED, SUCCESS, WARNING, ERROR, BORDER
        global _ACTIVE_THEME

        # Alterna o tema
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self._current_theme = new_theme
        _ACTIVE_THEME = new_theme

        # Atualiza as variáveis globais de cor
        t = THEMES[new_theme]
        BG_MAIN      = t["BG_MAIN"]
        BG_CARD      = t["BG_CARD"]
        BG_INPUT     = t["BG_INPUT"]
        BG_HOVER     = t["BG_HOVER"]
        ACCENT       = t["ACCENT"]
        ACCENT_HOVER = t["ACCENT_HOVER"]
        ACCENT_DIM   = t["ACCENT_DIM"]
        FG_TEXT      = t["FG_TEXT"]
        FG_MUTED     = t["FG_MUTED"]
        SUCCESS      = t["SUCCESS"]
        WARNING      = t["WARNING"]
        ERROR        = t["ERROR"]
        BORDER       = t["BORDER"]

        # Aplica modo no CustomTkinter
        ctk.set_appearance_mode("light" if new_theme == "light" else "dark")

        # Atualiza texto do botão (escuro → claro → escuro)
        self.btn_theme.configure(text="Tema ○" if new_theme == "light" else "Tema ●")

        # ── Recolore a janela raiz e frame principal ──
        self.root.configure(fg_color=BG_MAIN)
        self.root_frame.configure(fg_color=BG_MAIN)

        # ── Recolore botões de navegação ──
        nav_buttons = {
            "split_rename": self.btn_nav_rename,
            "split_simple": self.btn_nav_simple,
            "merge": self.btn_nav_merge,
            "profiles": self.btn_nav_profiles,
        }
        for p_name, btn in nav_buttons.items():
            if p_name == getattr(self, "_current_page", "split_rename"):
                btn.configure(fg_color=BG_HOVER, text_color=ACCENT,
                              hover_color=BG_HOVER, border_color=BORDER)
            else:
                btn.configure(fg_color=BG_INPUT, text_color=FG_TEXT,
                              hover_color=BG_HOVER, border_color=BORDER)

        for btn in [self.btn_readme, self.btn_theme]:
            btn.configure(fg_color=BG_INPUT, hover_color=BG_HOVER,
                          border_color=BORDER, text_color=FG_TEXT)

        # ── Recolore logo e título ──
        try:
            self.title_label.configure(text_color=FG_TEXT)
            self.subtitle.configure(text_color=FG_MUTED)
        except Exception:
            pass

        # ── Recolore a página principal (Dividir e Renomear) ──
        try:
            self.drop_card.configure(fg_color=BG_CARD, border_color=BORDER)
            self.out_entry.configure(fg_color=BG_INPUT, border_color=BORDER, text_color=FG_TEXT,
                                     placeholder_text_color=FG_MUTED)
            self.btn_split.configure(fg_color=ACCENT_DIM, hover_color=ACCENT)
            self.btn_open_folder.configure(fg_color=BG_INPUT, hover_color=BG_HOVER,
                                           border_color=BORDER, text_color=FG_MUTED)
            self.btn_select_out.configure(fg_color=BG_INPUT, hover_color=BG_HOVER,
                                          border_color=BORDER, text_color=FG_TEXT)
            self.progress_bar.configure(fg_color=BG_INPUT, progress_color=ACCENT_DIM)
            self.progress_label.configure(text_color=FG_MUTED)
            self.drop_label.configure(text_color=FG_MUTED)
            self.drop_icon.configure(text_color=FG_MUTED)
            self.file_label.configure(text_color=ACCENT)
            self.btn_clear_log.configure(hover_color=BG_HOVER, border_color=BORDER, text_color=FG_MUTED)
            self._log_title_label.configure(text_color=FG_TEXT)
            self._prof_lbl.configure(text_color=FG_TEXT)
            self._out_lbl.configure(text_color=FG_TEXT)
            self.log_card.configure(fg_color=BG_CARD, border_color=BORDER)
            self.log_text.configure(fg_color=BG_CARD, text_color=FG_TEXT,
                                    scrollbar_button_color=BG_INPUT,
                                    scrollbar_button_hover_color=BG_HOVER)
            self.profile_dropdown.configure(fg_color=BG_INPUT, button_color=BG_INPUT,
                                            button_hover_color=BG_HOVER,
                                            dropdown_fg_color=BG_CARD,
                                            dropdown_hover_color=BG_HOVER,
                                            text_color=FG_TEXT)
        except Exception:
            pass

        # ── Recolore página Divisão Simples ──
        try:
            self.drop_card_s.configure(fg_color=BG_CARD, border_color=BORDER)
            self.out_entry_s.configure(fg_color=BG_INPUT, border_color=BORDER, text_color=FG_TEXT,
                                       placeholder_text_color=FG_MUTED)
            self.btn_split_s.configure(fg_color=ACCENT_DIM, hover_color=ACCENT)
            self.btn_select_out_s.configure(fg_color=BG_INPUT, hover_color=BG_HOVER,
                                            border_color=BORDER, text_color=FG_TEXT)
            self.progress_bar_s.configure(fg_color=BG_INPUT, progress_color=ACCENT_DIM)
            self.progress_label_s.configure(text_color=FG_MUTED)
            self.drop_label_s.configure(text_color=FG_MUTED)
            self.drop_icon_s.configure(text_color=FG_MUTED)
            self.file_label_s.configure(text_color=ACCENT)
            self._simple_info_label.configure(text_color=FG_MUTED)
            self._simple_out_lbl.configure(text_color=FG_TEXT)
        except Exception:
            pass

        # ── Recolore página Juntar ──
        try:
            self.m_lf.configure(fg_color=BG_CARD, border_color=BORDER)
            self.m_list.configure(fg_color=BG_CARD, text_color=FG_TEXT,
                                  scrollbar_button_color=BG_INPUT,
                                  scrollbar_button_hover_color=BG_HOVER)
            self.m_out.configure(fg_color=BG_INPUT, border_color=BORDER, text_color=FG_TEXT,
                                 placeholder_text_color=FG_MUTED)
            self.m_btn.configure(fg_color=ACCENT_DIM, hover_color=ACCENT)
            self.m_btn_add.configure(fg_color=BG_INPUT, hover_color=BG_HOVER,
                                     border_color=BORDER, text_color=FG_TEXT)
            self.m_btn_clear.configure(fg_color=BG_INPUT, hover_color=BG_HOVER,
                                       border_color=BORDER, text_color=FG_MUTED)
            self.m_btn_sel.configure(fg_color=BG_INPUT, hover_color=BG_HOVER,
                                     border_color=BORDER, text_color=FG_TEXT)
            self.m_progress.configure(fg_color=BG_INPUT, progress_color=ACCENT_DIM)
            self.m_status.configure(text_color=FG_MUTED)
            self.m_info_lbl.configure(text_color=FG_MUTED)
            self.m_out_lbl.configure(text_color=FG_TEXT)
        except Exception:
            pass

        # ── Recolore editor de Perfis ──
        try:
            # ScrollableFrame principal
            self.profiles_scroll.configure(fg_color=BG_MAIN)
            # Editor card e campos
            self.editor_card.configure(fg_color=BG_CARD, border_color=BORDER)
            self.editor_title.configure(text_color=FG_TEXT)
            self._prof_name_lbl.configure(text_color=FG_MUTED)
            self._labels_search_lbl.configure(text_color=FG_MUTED)
            self.profile_name_entry.configure(fg_color=BG_INPUT, border_color=BORDER,
                                              text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
            self.labels_textbox.configure(fg_color=BG_INPUT, text_color=FG_TEXT)
            self.period_label_entry.configure(fg_color=BG_INPUT, border_color=BORDER,
                                              text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
            self.dept_label_entry.configure(fg_color=BG_INPUT, border_color=BORDER,
                                            text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
            self.naming_prefix_entry.configure(fg_color=BG_INPUT, border_color=BORDER,
                                               text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
            self.naming_sector_entry.configure(fg_color=BG_INPUT, border_color=BORDER,
                                               text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
            self.naming_type_entry.configure(fg_color=BG_INPUT, border_color=BORDER,
                                             text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
            self.btn_save_profile.configure(fg_color=ACCENT_DIM, hover_color=ACCENT)
            self.btn_cancel_edit.configure(fg_color=BG_INPUT, hover_color=ERROR)
            # Labels e separadores abaixo do editor
            self._profiles_saved_lbl.configure(text_color=FG_TEXT)
            self._profiles_separator.configure(fg_color=BORDER)
            self._mapping_title_lbl.configure(text_color=FG_TEXT)
            self._mapping_sub_lbl.configure(text_color=FG_MUTED)
            # Card de adicionar mapeamento
            self.add_mapping_card.configure(fg_color=BG_CARD, border_color=BORDER)
            self.new_dept_full.configure(fg_color=BG_INPUT, border_color=BORDER,
                                         text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
            self.new_dept_sigla.configure(fg_color=BG_INPUT, border_color=BORDER,
                                          text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
        except Exception:
            pass

        # ── Recolore footer ──
        try:
            self.footer.configure(text_color=FG_MUTED)
        except Exception:
            pass

        # ── Recarrega cards dinâmicos da página de Perfis ──
        # (cards de perfis e mapeamentos são criados dinamicamente e precisam ser recriados)
        try:
            self._refresh_profiles_list()
        except Exception:
            pass


    def _build_page_simple_split(self):
        """Página: Divisão Simples (sem renomear)."""
        main = self.split_simple_frame

        # ── Info ──
        self._simple_info_label = ctk.CTkLabel(
            main, text="Divide o PDF em páginas individuais (Pagina_1.pdf, ...).",
            font=(FONT_FAMILY, 12), text_color=FG_MUTED
        )
        self._simple_info_label.pack(anchor="w", pady=(0, 12))

        # ── Drop Zone ──
        self.drop_card_s = ctk.CTkFrame(
            main, fg_color=BG_CARD, corner_radius=12,
            border_width=2, border_color=BORDER
        )
        self.drop_card_s.pack(fill="x", pady=(0, 14))

        inner_drop = ctk.CTkFrame(self.drop_card_s, fg_color="transparent", height=140)
        inner_drop.pack(fill="x", padx=20, pady=20)
        inner_drop.pack_propagate(False)

        self.drop_icon_s = ctk.CTkLabel(
            inner_drop, text="✂️", font=(FONT_FAMILY, 42), text_color=FG_MUTED
        )
        self.drop_icon_s.pack(pady=(10, 5))

        self.drop_label_s = ctk.CTkLabel(
            inner_drop, text="Clique ou arraste um PDF aqui para dividir",
            font=(FONT_FAMILY, 13), text_color=FG_MUTED
        )
        self.drop_label_s.pack()

        self.file_label_s = ctk.CTkLabel(
            inner_drop, text="", font=(FONT_FAMILY, 11), text_color=ACCENT
        )
        self.file_label_s.pack()

        # Bindings
        for widget in [self.drop_card_s, inner_drop, self.drop_icon_s, self.drop_label_s, self.file_label_s]:
            widget.bind("<Button-1>", lambda e: self._sel_pdf_s())
            widget.configure(cursor="hand2")

        if HAS_DND:
            self.drop_card_s.drop_target_register(DND_FILES)
            self.drop_card_s.dnd_bind('<<Drop>>', self._on_drop) # _on_drop já lida com o path
            self.drop_card_s.dnd_bind('<<DragEnter>>', self._on_drag_enter)
            self.drop_card_s.dnd_bind('<<DragLeave>>', self._on_drag_leave)

        # ── Pasta de Saída ──
        out_row = ctk.CTkFrame(main, fg_color="transparent")
        out_row.pack(fill="x", pady=(0, 14))

        self._simple_out_lbl = ctk.CTkLabel(
            out_row, text="📁  Pasta de Saída",
            font=(FONT_FAMILY, 12, "bold"), text_color=FG_TEXT
        )
        self._simple_out_lbl.pack(anchor="w", pady=(0, 6))

        field_row = ctk.CTkFrame(out_row, fg_color="transparent")
        field_row.pack(fill="x")

        self.out_entry_s = ctk.CTkEntry(
            field_row, placeholder_text="Selecione onde os arquivos serão salvos...",
            font=(FONT_FAMILY, 12), height=40,
            fg_color=BG_INPUT, border_color=BORDER, text_color=FG_TEXT,
            placeholder_text_color=FG_MUTED, corner_radius=8
        )
        self.out_entry_s.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_select_out_s = ctk.CTkButton(
            field_row, text="Selecionar", width=110, height=40,
            font=(FONT_FAMILY, 12, "bold"), corner_radius=8,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER, text_color=FG_TEXT,
            command=self._sel_out_s
        )
        self.btn_select_out_s.pack(side="right")

        # ── Botões de ação ──
        btn_row = ctk.CTkFrame(main, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 14))

        self.btn_split_s = ctk.CTkButton(
            btn_row, text="✂️   DIVIDIR (SIMPLES)",
            font=(FONT_FAMILY, 14, "bold"), height=48,
            corner_radius=10,
            fg_color=ACCENT_DIM, hover_color=ACCENT,
            text_color="#ffffff",
            command=self._start_simple_split
        )
        self.btn_split_s.pack(side="left", fill="x", expand=True, padx=(0, 6))

        # ── Progresso ──
        progress_frame = ctk.CTkFrame(main, fg_color="transparent")
        progress_frame.pack(fill="x", pady=(0, 4))

        self.progress_bar_s = ctk.CTkProgressBar(
            progress_frame, height=6, corner_radius=3,
            fg_color=BG_INPUT, progress_color=ACCENT_DIM
        )
        self.progress_bar_s.pack(fill="x")
        self.progress_bar_s.set(0)

        self.progress_label_s = ctk.CTkLabel(
            progress_frame, text="",
            font=(FONT_FAMILY, 11), text_color=FG_MUTED
        )
        self.progress_label_s.pack(anchor="w", pady=(4, 0))

    def _build_page_merge(self):
        """Página: Juntar PDFs."""
        page = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self._pages["merge"] = page

        self.m_info_lbl = ctk.CTkLabel(page, text="Selecione múltiplos PDFs para juntar em um só.",
                     font=(FONT_FAMILY, 11), text_color=FG_MUTED)
        self.m_info_lbl.pack(anchor="w", pady=(0, 10))

        # Lista
        self.m_lf = ctk.CTkFrame(page, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER)
        self.m_lf.pack(fill="both", expand=True, pady=(0, 10))
        self.m_list = ctk.CTkTextbox(self.m_lf, font=(FONT_FAMILY, 11), fg_color=BG_CARD, text_color=FG_TEXT, corner_radius=10, wrap="word", height=120, state="disabled", scrollbar_button_color=BG_INPUT, scrollbar_button_hover_color=BG_HOVER)
        self.m_list.pack(fill="both", expand=True, padx=4, pady=4)
        self.m_files = []

        # Buttons
        mr = ctk.CTkFrame(page, fg_color="transparent")
        mr.pack(fill="x", pady=(0, 10))
        self.m_btn_add = ctk.CTkButton(mr, text="➕ Adicionar", width=120, height=36, font=(FONT_FAMILY, 12), corner_radius=8, fg_color=BG_INPUT, hover_color=BG_HOVER, border_width=1, border_color=BORDER, text_color=FG_TEXT, command=self._merge_add)
        self.m_btn_add.pack(side="left", padx=(0, 6))
        self.m_btn_clear = ctk.CTkButton(mr, text="🗑️ Limpar", width=100, height=36, font=(FONT_FAMILY, 12), corner_radius=8, fg_color=BG_INPUT, hover_color=BG_HOVER, border_width=1, border_color=BORDER, text_color=FG_MUTED, command=self._merge_clear)
        self.m_btn_clear.pack(side="left")

        # Output
        self.m_out_lbl = ctk.CTkLabel(page, text="📁 Salvar como", font=(FONT_FAMILY, 12, "bold"), text_color=FG_TEXT)
        self.m_out_lbl.pack(anchor="w", pady=(0, 6))
        or2 = ctk.CTkFrame(page, fg_color="transparent")
        or2.pack(fill="x", pady=(0, 10))
        self.m_out = ctk.CTkEntry(or2, placeholder_text="Nome do arquivo de saída...", font=(FONT_FAMILY, 12), height=40, fg_color=BG_INPUT, border_color=BORDER, text_color=FG_TEXT, placeholder_text_color=FG_MUTED, corner_radius=8)
        self.m_out.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.m_btn_sel = ctk.CTkButton(or2, text="Selecionar", width=110, height=40, font=(FONT_FAMILY, 12), corner_radius=8, fg_color=BG_INPUT, hover_color=BG_HOVER, border_width=1, border_color=BORDER, text_color=FG_TEXT, command=self._merge_sel_out)
        self.m_btn_sel.pack(side="right")
        self.m_output = ""

        self.m_btn = ctk.CTkButton(page, text="📎   JUNTAR PDFs", font=(FONT_FAMILY, 14, "bold"), height=48, corner_radius=10, fg_color=ACCENT_DIM, hover_color=ACCENT, text_color="#ffffff", command=self._start_merge)
        self.m_btn.pack(fill="x", pady=(6, 10))

        self.m_progress = ctk.CTkProgressBar(page, height=6, corner_radius=3, fg_color=BG_INPUT, progress_color=ACCENT_DIM)
        self.m_progress.set(0)
        self.m_progress.pack(fill="x")
        self.m_status = ctk.CTkLabel(page, text="", font=(FONT_FAMILY, 11), text_color=FG_MUTED)
        self.m_status.pack(anchor="w", pady=(4, 0))

    # ── Ações: Juntar PDFs ──

    def _merge_add(self):
        files = filedialog.askopenfilenames(title="Adicionar PDFs", filetypes=[("PDF", "*.pdf")])
        if files:
            self.m_files.extend(files)
            self._merge_refresh_list()

    def _merge_clear(self):
        self.m_files.clear()
        self._merge_refresh_list()

    def _merge_refresh_list(self):
        self.m_list.configure(state="normal")
        self.m_list.delete("1.0", "end")
        for i, f in enumerate(self.m_files, 1):
            self.m_list.insert("end", f"{i}. {os.path.basename(f)}\n")
        if not self.m_files:
            self.m_list.insert("end", "Nenhum PDF adicionado.\n")
        self.m_list.configure(state="disabled")

    def _merge_sel_out(self):
        path = filedialog.asksaveasfilename(title="Salvar como", defaultextension=".pdf",
                                             filetypes=[("PDF", "*.pdf")])
        if path:
            self.m_output = path
            self.m_out.delete(0, "end")
            self.m_out.insert(0, path)

    def _start_merge(self):
        if not self.m_files:
            self._log("⚠️  Adicione PDFs para juntar.", "warning")
            return
        out = self.m_out.get().strip()
        if not out:
            self._log("⚠️  Selecione onde salvar.", "warning")
            return
        self.m_btn.configure(text="⏳  Processando...", state="disabled", fg_color=BG_INPUT)
        self.m_progress.set(0)
        threading.Thread(target=self._run_merge, args=(list(self.m_files), out), daemon=True).start()

    def _run_merge(self, files, output):
        try:
            writer = PdfWriter()
            total = len(files)
            for i, f in enumerate(files, 1):
                reader = PdfReader(f)
                for page in reader.pages:
                    writer.add_page(page)
                pct = i / total
                self.root.after(0, lambda p=pct, c=i, t=total: (
                    self.m_progress.set(p),
                    self.m_status.configure(text=f"Processando {c}/{t} • {p*100:.0f}%")
                ))
            os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
            with open(output, "wb") as f:
                writer.write(f)
            tp = len(writer.pages)
            self._log(f"✅  {len(files)} PDFs unidos → {tp} páginas → {os.path.basename(output)}", "success")
            self.root.after(0, lambda: self.m_status.configure(text=f"Concluído! {tp} páginas"))
        except Exception as e:
            self._log(f"❌ Erro: {e}", "error")
        finally:
            self.root.after(0, lambda: self.m_btn.configure(
                text="📎   JUNTAR PDFs", state="normal", fg_color=ACCENT_DIM, hover_color=ACCENT))

    # ── Alertas inline ──

    def _build_profiles_editor(self):
        """Constrói o editor de perfis integrado."""
        frame = self.profiles_frame

        # Container principal com scroll para a configuração e lista
        self.profiles_scroll = ctk.CTkScrollableFrame(frame, fg_color=BG_MAIN)
        self.profiles_scroll.pack(fill="both", expand=True)
        main_scroll = self.profiles_scroll

        # ── Seção: Editor de Perfil ──
        self.editor_card = ctk.CTkFrame(main_scroll, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color=BORDER)
        self.editor_card.pack(fill="x", pady=(0, 14))

        self.editor_inner = ctk.CTkFrame(self.editor_card, fg_color="transparent")
        self.editor_inner.pack(fill="x", padx=20, pady=16)

        self.editor_title = ctk.CTkLabel(
            self.editor_inner, text="➕  Criar Novo Perfil",
            font=(FONT_FAMILY, 15, "bold"), text_color=FG_TEXT
        )
        self.editor_title.pack(anchor="w", pady=(0, 12))

        # Nome do perfil
        name_row = ctk.CTkFrame(self.editor_inner, fg_color="transparent")
        name_row.pack(fill="x", pady=(0, 10))
        self._prof_name_lbl = ctk.CTkLabel(name_row, text="Nome do Perfil:", font=(FONT_FAMILY, 12), text_color=FG_MUTED)
        self._prof_name_lbl.pack(side="left", padx=(0, 8))
        self.profile_name_entry = ctk.CTkEntry(name_row, placeholder_text="Ex: Informe de Rendimento", height=36, corner_radius=8, fg_color=BG_INPUT, border_color=BORDER, text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
        self.profile_name_entry.pack(side="left", fill="x", expand=True)

        # ── Subseção: 🔍 Busca no PDF ──
        ctk.CTkLabel(self.editor_inner, text="🔍 Busca no PDF (Configurações Dinâmicas)", font=(FONT_FAMILY, 13, "bold"), text_color=ACCENT).pack(anchor="w", pady=(10, 5))
        
        # Rótulos de Nome
        self._labels_search_lbl = ctk.CTkLabel(self.editor_inner, text="Rótulos de busca de Nome (um por linha):", font=(FONT_FAMILY, 11), text_color=FG_MUTED)
        self._labels_search_lbl.pack(anchor="w")
        self.labels_textbox = ctk.CTkTextbox(self.editor_inner, height=80, corner_radius=8, fg_color=BG_INPUT, text_color=FG_TEXT)
        self.labels_textbox.pack(fill="x", pady=(0, 10))

        # Regex de Período e Depto
        def create_small_field(parent, label, placeholder, default_val=""):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(fill="x", pady=2)
            ctk.CTkLabel(f, text=label, width=120, anchor="w", font=(FONT_FAMILY, 11), text_color=FG_MUTED).pack(side="left")
            entry = ctk.CTkEntry(f, placeholder_text=placeholder, height=30, corner_radius=6, fg_color=BG_INPUT, border_color=BORDER, font=(FONT_FAMILY, 11), text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
            entry.insert(0, default_val)
            entry.pack(side="left", fill="x", expand=True)
            return entry

        self.period_label_entry = create_small_field(
            self.editor_inner,
            "Texto antes da data:",
            "Ex: Período:   ou   Competência:"
        )
        ctk.CTkLabel(
            self.editor_inner,
            text="   💡 O app vai encontrar a data automaticamente após esse texto (ex: 02/2025)",
            font=(FONT_FAMILY, 10), text_color=FG_MUTED
        ).pack(anchor="w", pady=(0, 6))

        self.dept_label_entry = create_small_field(
            self.editor_inner,
            "Texto antes do depto:",
            "Ex: Depto.:   ou   Departamento:"
        )
        ctk.CTkLabel(
            self.editor_inner,
            text="   💡 Deixe em branco se o PDF não tiver departamento",
            font=(FONT_FAMILY, 10), text_color=FG_MUTED
        ).pack(anchor="w", pady=(0, 6))

        # ── Subseção: 📛 Nomenclatura ──
        ctk.CTkLabel(self.editor_inner, text="📛 Nomenclatura (Configurações Fixas)", font=(FONT_FAMILY, 13, "bold"), text_color=SUCCESS).pack(anchor="w", pady=(15, 5))
        
        self.naming_active_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.editor_inner, text="Ativar nomenclatura para este perfil", variable=self.naming_active_var, font=(FONT_FAMILY, 12)).pack(anchor="w", pady=5)

        self.naming_prefix_entry = create_small_field(self.editor_inner, "Prefixo:", "Ex: EMPRESA_RH")
        self.naming_sector_entry = create_small_field(self.editor_inner, "Setor:", "Ex: ADM")
        self.naming_type_entry = create_small_field(self.editor_inner, "Tipo Doc:", "Ex: HOLERITE")

        ctk.CTkLabel(
            self.editor_inner,
            text="   💡 Campos vazios são ignorados no nome do arquivo. Ordem: Período → Prefixo → Setor → Depto → Tipo → Nome",
            font=(FONT_FAMILY, 10), text_color=FG_MUTED, wraplength=540, justify="left"
        ).pack(anchor="w", pady=(2, 6))

        # Botões de ação do editor
        self.editor_btns_row = ctk.CTkFrame(self.editor_inner, fg_color="transparent")
        self.editor_btns_row.pack(fill="x", pady=(15, 0))

        self.btn_save_profile = ctk.CTkButton(
            self.editor_btns_row, text="💾  Salvar Perfil",
            font=(FONT_FAMILY, 13, "bold"), height=40, corner_radius=8,
            fg_color=ACCENT_DIM, hover_color=ACCENT, command=self._save_profile_data
        )
        self.btn_save_profile.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_cancel_edit = ctk.CTkButton(
            self.editor_btns_row, text="Cancelar",
            font=(FONT_FAMILY, 13), height=40, corner_radius=8,
            fg_color=BG_INPUT, hover_color=ERROR, command=self._cancel_profile_edit
        )
        # Oculto por padrão, aparece apenas ao editar
        self.is_editing_profile = False

        # ── Seção: Perfis existentes ──
        self._profiles_saved_lbl = ctk.CTkLabel(main_scroll, text="📋  Perfis Salvos", font=(FONT_FAMILY, 15, "bold"), text_color=FG_TEXT)
        self._profiles_saved_lbl.pack(anchor="w", pady=(6, 8))

        self.profiles_list_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
        self.profiles_list_frame.pack(fill="x", pady=(0, 20))

        # ── Seção: Mapeamento de Departamentos ──
        self._profiles_separator = ctk.CTkFrame(main_scroll, fg_color=BORDER, height=1)
        self._profiles_separator.pack(fill="x", pady=10)
        
        mapping_title_row = ctk.CTkFrame(main_scroll, fg_color="transparent")
        mapping_title_row.pack(fill="x", pady=(10, 5))
        self._mapping_title_lbl = ctk.CTkLabel(mapping_title_row, text="🗺️  Mapeamento de Departamentos", font=(FONT_FAMILY, 15, "bold"), text_color=FG_TEXT)
        self._mapping_title_lbl.pack(side="left")
        self._mapping_sub_lbl = ctk.CTkLabel(mapping_title_row, text="(Nomes longos → Siglas curtas)", font=(FONT_FAMILY, 11), text_color=FG_MUTED)
        self._mapping_sub_lbl.pack(side="left", padx=10)

        # Adicionar novo mapeamento
        self.add_mapping_card = ctk.CTkFrame(main_scroll, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color=BORDER)
        self.add_mapping_card.pack(fill="x", pady=(0, 10))
        
        am_inner = ctk.CTkFrame(self.add_mapping_card, fg_color="transparent")
        am_inner.pack(fill="x", padx=15, pady=12)
        
        self.new_dept_full = ctk.CTkEntry(am_inner, placeholder_text="Nome no PDF (Ex: RECURSOS HUMANOS, FINANCEIRO...)", height=36, corner_radius=8, fg_color=BG_INPUT, border_color=BORDER, text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
        self.new_dept_full.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.new_dept_sigla = ctk.CTkEntry(am_inner, placeholder_text="Sigla (Ex: RH, FIN)", width=120, height=36, corner_radius=8, fg_color=BG_INPUT, border_color=BORDER, text_color=FG_TEXT, placeholder_text_color=FG_MUTED)
        self.new_dept_sigla.pack(side="left", padx=(0, 10))
        
        ctk.CTkButton(
            am_inner, text="➕ Add", width=80, height=36, corner_radius=8,
            fg_color=SUCCESS, hover_color="#2ea043", text_color="#ffffff",
            font=(FONT_FAMILY, 12, "bold"),
            command=self._add_dept_mapping
        ).pack(side="right")

        # Lista de mapeamentos
        self.mapping_list_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
        self.mapping_list_frame.pack(fill="x", pady=(0, 20))

    def _refresh_profiles_list(self):
        """Atualiza a lista de perfis e mapeamentos no editor."""
        # Perfis
        for widget in self.profiles_list_frame.winfo_children():
            widget.destroy()

        data = load_profiles()
        profiles = data.get("profiles", {})
        
        for name, info in sorted(profiles.items()):
            self._add_profile_card(name, info)
            
        # Mapeamentos
        self._refresh_mapping_list()

    def _refresh_mapping_list(self):
        """Atualiza a lista de siglas de departamentos."""
        for widget in self.mapping_list_frame.winfo_children():
            widget.destroy()
            
        data = load_profiles()
        mapping = data.get("dept_mapping", {})
        
        if not mapping:
            ctk.CTkLabel(self.mapping_list_frame, text="Nenhum mapeamento cadastrado.", font=(FONT_FAMILY, 11), text_color=FG_MUTED).pack(pady=10)
            return
            
        for full, sigla in sorted(mapping.items()):
            row = ctk.CTkFrame(self.mapping_list_frame, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER)
            row.pack(fill="x", pady=2)
            
            ctk.CTkLabel(row, text=f"📍 {full}", font=(FONT_FAMILY, 12), text_color=FG_TEXT).pack(side="left", padx=15, pady=8)
            ctk.CTkLabel(row, text="→", font=(FONT_FAMILY, 12), text_color=FG_MUTED).pack(side="left")
            ctk.CTkLabel(row, text=sigla, font=(FONT_FAMILY, 12, "bold"), text_color=ACCENT).pack(side="left", padx=10)
            
            ctk.CTkButton(
                row, text="✕", width=24, height=24, corner_radius=6,
                fg_color="transparent", hover_color=ERROR, text_color=FG_MUTED,
                command=lambda f=full: self._delete_dept_mapping(f)
            ).pack(side="right", padx=10)

    def _add_dept_mapping(self):
        full = self.new_dept_full.get().strip()
        sigla = self.new_dept_sigla.get().strip()
        
        if not full or not sigla:
            return
            
        data = load_profiles()
        if "dept_mapping" not in data: data["dept_mapping"] = {}
        
        data["dept_mapping"][full] = sigla
        save_profiles(data)
        
        self.new_dept_full.delete(0, "end")
        self.new_dept_sigla.delete(0, "end")
        self._refresh_mapping_list()
        self._log(f"✅ Mapeamento '{sigla}' adicionado.", "success")

    def _delete_dept_mapping(self, full_name):
        data = load_profiles()
        if "dept_mapping" in data and full_name in data["dept_mapping"]:
            del data["dept_mapping"][full_name]
            save_profiles(data)
            self._refresh_mapping_list()
            self._log(f"🗑️ Mapeamento removido.", "info")

    def _add_profile_card(self, name: str, info: dict):
        """Adiciona um card de perfil na lista com botão de editar."""
        card = ctk.CTkFrame(self.profiles_list_frame, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=4)

        card_inner = ctk.CTkFrame(card, fg_color="transparent")
        card_inner.pack(fill="x", padx=15, pady=12)

        # Esquerda: Nome e Atalhos
        left_side = ctk.CTkFrame(card_inner, fg_color="transparent")
        left_side.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(left_side, text=f"📄 {name}", font=(FONT_FAMILY, 14, "bold"), text_color=FG_TEXT).pack(anchor="w")
        
        labels = info.get("labels", [])
        labels_txt = ", ".join(labels[:4]) + ("..." if len(labels) > 4 else "")
        ctk.CTkLabel(left_side, text=f"Busca: {labels_txt}", font=(FONT_FAMILY, 11), text_color=FG_MUTED).pack(anchor="w")

        # Direita: Botões
        btn_row = ctk.CTkFrame(card_inner, fg_color="transparent")
        btn_row.pack(side="right")

        ctk.CTkButton(
            btn_row, text="✏️ Editar", width=70, height=30, corner_radius=6,
            fg_color=BG_INPUT, hover_color=ACCENT_DIM, text_color=FG_TEXT,
            command=lambda n=name: self._edit_profile(n)
        ).pack(side="left", padx=4)

        if name != DEFAULT_PROFILE_NAME:
            ctk.CTkButton(
                btn_row, text="✕", width=34, height=30, corner_radius=6,
                fg_color=BG_INPUT, hover_color=ERROR, text_color=FG_MUTED,
                command=lambda n=name: self._delete_profile(n)
            ).pack(side="left")

    def _sel_pdf_s(self):
        """Seleciona o PDF para a divisão simples."""
        path = filedialog.askopenfilename(title="Selecionar PDF", filetypes=[("PDF", "*.pdf")])
        if path:
            self.s_pdf_path = path
            self.drop_label_s.configure(text="Arquivo selecionado:")
            self.file_label_s.configure(text=os.path.basename(path))
            self.drop_icon_s.configure(text="✅")
            self.drop_card_s.configure(border_color=ACCENT_DIM)
            
            # Sugerir pasta de saída
            if not self.out_entry_s.get().strip():
                default_out = os.path.join(os.path.dirname(path), "PDFs_Divididos")
                self.out_entry_s.delete(0, "end")
                self.out_entry_s.insert(0, default_out)

    def _sel_out_s(self):
        """Seleciona a pasta de saída para a divisão simples."""
        path = filedialog.askdirectory(title="Pasta de Saída")
        if path:
            self.out_entry_s.delete(0, "end")
            self.out_entry_s.insert(0, path)

    def _start_simple_split(self):
        """Inicia a divisão simples em thread."""
        pdf = self.s_pdf_path
        out = self.out_entry_s.get().strip()
        
        if not pdf:
            self._log("⚠️  Selecione um arquivo PDF primeiro.", "warning")
            return
        if not out:
            self._log("⚠️  Selecione uma pasta de saída.", "warning")
            return

        self.btn_split_s.configure(text="⏳ Processando...", state="disabled")
        self.is_processing = True
        self.progress_bar_s.set(0)
        self.progress_label_s.configure(text="Iniciando divisão...")

        threading.Thread(
            target=self._run_simple_split,
            args=(pdf, out),
            daemon=True
        ).start()

    def _run_simple_split(self, pdf_path, output_dir):
        """Executa a divisão simples (sem renomeio)."""
        try:
            os.makedirs(output_dir, exist_ok=True)
            reader = PdfReader(pdf_path)
            total = len(reader.pages)

            for i, page in enumerate(reader.pages, 1):
                writer = PdfWriter()
                writer.add_page(page)
                
                out_file = os.path.join(output_dir, f"Pagina_{i:03d}.pdf")
                with open(out_file, "wb") as f:
                    writer.write(f)

                pct = i / total
                self.root.after(0, lambda p=pct, c=i, t=total: (
                    self.progress_bar_s.set(p),
                    self.progress_label_s.configure(text=f"Processando página {c} de {t} ({p*100:.0f}%)")
                ))

            self._log(f"✅ Sucesso! {total} páginas salvas em: {output_dir}", "success")
            self._show_result_banner(f"Concluído! {total} arquivos gerados.", "success")
            
        except Exception as e:
            self._log(f"❌ Erro na divisão simples: {e}", "error")
            self._show_result_banner("Ocorreu um erro inesperado.", "error")
        finally:
            self.is_processing = False
            self.root.after(0, lambda: self.btn_split_s.configure(text="✂️   DIVIDIR (SIMPLES)", state="normal"))

    def _edit_profile(self, name: str):
        """Carrega os dados de um perfil no editor para edição."""
        data = load_profiles()
        profile = data.get("profiles", {}).get(name)
        if not profile: return

        self.is_editing_profile = name
        self.editor_title.configure(text=f"📝 Editar Perfil: {name}")
        self.btn_save_profile.configure(text="💾  Atualizar Perfil")
        self.btn_cancel_edit.pack(side="right", fill="x", expand=True)

        # Preencher campos
        self.profile_name_entry.delete(0, "end")
        self.profile_name_entry.insert(0, name)
        
        self.labels_textbox.delete("1.0", "end")
        self.labels_textbox.insert("1.0", "\n".join(profile.get("labels", [])))

        # Usa o texto simples salvo; se não houver, tenta extrair do regex
        self.period_label_entry.delete(0, "end")
        self.period_label_entry.insert(0, profile.get("period_label", ""))

        self.dept_label_entry.delete(0, "end")
        self.dept_label_entry.insert(0, profile.get("dept_label", ""))

        naming = profile.get("naming", {})
        self.naming_active_var.set(naming.get("active", True))
        self.naming_prefix_entry.delete(0, "end")
        self.naming_prefix_entry.insert(0, naming.get("prefix", ""))
        self.naming_sector_entry.delete(0, "end")
        self.naming_sector_entry.insert(0, naming.get("sector", ""))
        self.naming_type_entry.delete(0, "end")
        self.naming_type_entry.insert(0, naming.get("doc_type", ""))

        self.profiles_frame.focus_set()

    def _cancel_profile_edit(self):
        self.is_editing_profile = False
        self.editor_title.configure(text="➕  Criar Novo Perfil")
        self.btn_save_profile.configure(text="💾  Salvar Perfil")
        self.btn_cancel_edit.pack_forget()
        
        # Limpar campos
        self.profile_name_entry.delete(0, "end")
        self.labels_textbox.delete("1.0", "end")
        self.period_label_entry.delete(0, "end")
        self.dept_label_entry.delete(0, "end")
        self.naming_prefix_entry.delete(0, "end")
        self.naming_sector_entry.delete(0, "end")
        self.naming_type_entry.delete(0, "end")

    def _save_profile_data(self):
        """Salva ou atualiza um perfil com todas as suas configurações."""
        name = self.profile_name_entry.get().strip()
        if not name:
            self._log("⚠️  Insira um nome para o perfil.", "warning")
            return

        # Rótulos
        labels_raw = self.labels_textbox.get("1.0", "end").strip()
        labels = [l.strip() for l in labels_raw.split("\n") if l.strip()]

        # Converte texto simples em regex automaticamente
        period_label = self.period_label_entry.get().strip()
        if period_label:
            escaped = re.escape(period_label.rstrip(":").strip())
            period_regex = escaped + r'[:\s]+(\d{2}/\d{4})'
        else:
            period_regex = r'Per[ií]odo[:\s]+(\d{2})/(\d{4})'

        dept_label = self.dept_label_entry.get().strip()
        if dept_label:
            escaped = re.escape(dept_label.rstrip(":").strip())
            dept_regex = escaped + r'[.:\s]*(.+)'
        else:
            dept_regex = ""

        # Armazena os textos simples junto para recuperar na edição
        # Configurações do perfil
        profile_info = {
            "labels": labels,
            "period_regex": period_regex,
            "dept_regex": dept_regex,
            "period_label": period_label,
            "dept_label": dept_label,
            "naming": {
                "active": self.naming_active_var.get(),
                "prefix": self.naming_prefix_entry.get().strip(),
                "sector": self.naming_sector_entry.get().strip(),
                "doc_type": self.naming_type_entry.get().strip()
            }
        }

        data = load_profiles()
        
        # Se estiver editando e o nome mudou, remove o antigo
        if self.is_editing_profile and self.is_editing_profile != name:
            if self.is_editing_profile == DEFAULT_PROFILE_NAME:
                self._log("⚠️ Não é possível renomear o perfil padrão.", "error")
                return
            if self.is_editing_profile in data["profiles"]:
                del data["profiles"][self.is_editing_profile]

        data["profiles"][name] = profile_info
        save_profiles(data)

        self._refresh_profile_dropdown()
        self._cancel_profile_edit()
        self._refresh_profiles_list()
        self._log(f"✅ Perfil '{name}' salvo com sucesso.", "success")

    def _delete_profile(self, name: str):
        """Exclui um perfil customizado."""
        if name == DEFAULT_PROFILE_NAME: return
        
        data = load_profiles()
        if name in data.get("profiles", {}):
            del data["profiles"][name]
            save_profiles(data)

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

    def _show_result_banner(self, sucesso: int, falhas: int, total: int, output_dir: str):
        """Mostra banner de resultado integrado na janela após o processamento."""
        # Limpar conteúdo anterior
        for widget in self.result_banner.winfo_children():
            widget.destroy()

        inner = ctk.CTkFrame(self.result_banner, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        # Determinar cor e ícone conforme resultado
        if falhas == 0:
            icon, title_color, border_color = "✅", SUCCESS, SUCCESS
            title = f"Concluído com sucesso! {sucesso} arquivo(s) gerado(s)."
        elif sucesso == 0:
            icon, title_color, border_color = "❌", ERROR, ERROR
            title = f"Nenhum nome encontrado. {total} arquivo(s) salvo(s) como Pagina_XXX."
        else:
            icon, title_color, border_color = "⚠️", WARNING, WARNING
            title = f"{sucesso} arquivo(s) nomeado(s), {falhas} sem nome."

        self.result_banner.configure(border_color=border_color)

        ctk.CTkLabel(
            inner, text=f"{icon}  {title}",
            font=(FONT_FAMILY, 13, "bold"), text_color=title_color, anchor="w"
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            inner, text="✕", width=28, height=28,
            font=(FONT_FAMILY, 12, "bold"), corner_radius=6,
            fg_color="transparent", hover_color=BG_HOVER,
            text_color=FG_MUTED, border_width=0,
            command=self._dismiss_result_banner
        ).pack(side="right")

        # Exibir acima do log
        self.result_banner.pack(fill="x", pady=(0, 10), before=self._log_header)
        self.result_banner_visible = True

    def _dismiss_result_banner(self):
        """Esconde o banner de resultado se estiver visível."""
        if self.result_banner_visible:
            self.result_banner.pack_forget()
            self.result_banner_visible = False

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
            self._log("⚠️  Selecione um arquivo PDF.", "warning")
            return
        if not os.path.isfile(pdf):
            self._log(f"⚠️  Arquivo não encontrado: {pdf}", "error")
            return
        if not output:
            self._log("⚠️  Selecione a pasta de saída.", "warning")
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

        profile_name = self.profile_var.get()
        data = load_profiles()
        profile_data = data.get("profiles", {}).get(profile_name, DEFAULT_PROFILE_DATA)
        dept_mapping = data.get("dept_mapping", {})
        
        self._log(f"🏷️  Perfil selecionado: {profile_name}", "info")

        thread = threading.Thread(
            target=self._run_split, args=(pdf, output, profile_data, dept_mapping), daemon=True
        )
        thread.start()

    def _run_split(self, pdf_path: str, output_dir: str, profile_data=None, dept_mapping=None):
        try:
            sucesso, falhas, total = split_pdf(
                pdf_path, output_dir,
                progress_callback=self._update_progress,
                log_callback=self._log,
                profile_data=profile_data,
                dept_mapping=dept_mapping
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

    def _version_newer(self, remote: str, local: str) -> bool:
        """Compara versões semânticas."""
        try:
            r = [int(x) for x in remote.split(".")]
            l = [int(x) for x in local.split(".")]
            return r > l
        except (ValueError, IndexError):
            return remote != local

    def _show_update_banner(self, version: str, url: str):
        """Mostra banner de atualização disponível."""
        banner = self.update_banner
        banner.pack(fill="x", pady=(8, 0), before=self.footer_row)

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

    # ── Ações: Juntar PDFs ──

    def _merge_add(self):
        files = filedialog.askopenfilenames(title="Adicionar PDFs", filetypes=[("PDF", "*.pdf")])
        if files:
            for f in files:
                if f not in self.m_files:
                    self.m_files.append(f)
            self._merge_refresh_list()

    def _merge_clear(self):
        self.m_files = []
        self._merge_refresh_list()

    def _merge_refresh_list(self):
        self.m_list.configure(state="normal")
        self.m_list.delete("1.0", "end")
        for f in self.m_files:
            self.m_list.insert("end", f"📍 {os.path.basename(f)}\n")
        self.m_list.configure(state="disabled")

    def _merge_sel_out(self):
        path = filedialog.asksaveasfilename(title="Salvar PDF Unido", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if path:
            self.m_output = path
            self.m_out.delete(0, "end")
            self.m_out.insert(0, path)

    def _start_merge(self):
        if not self.m_files:
            self._log("⚠️ Adicione PDFs para juntar.", "warning")
            return
        out = self.m_out.get().strip()
        if not out:
            self._log("⚠️ Selecione o arquivo de saída.", "warning")
            return
        
        self.m_btn.configure(text="⏳  Processando...", state="disabled", fg_color=BG_INPUT)
        self.m_progress.set(0)
        self.m_status.configure(text="Iniciando...")
        
        threading.Thread(target=self._run_merge, args=(self.m_files, out), daemon=True).start()

    def _run_merge(self, files, output):
        try:
            writer = PdfWriter()
            t = len(files)
            for i, fpath in enumerate(files, 1):
                pdf = PdfReader(fpath)
                for page in pdf.pages:
                    writer.add_page(page)
                p = i / t
                self.root.after(0, lambda p=p, c=i, t=t: (
                    self.m_progress.set(p),
                    self.m_status.configure(text=f"Processando {c}/{t} • {p*100:.0f}%")
                ))
            os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
            with open(output, "wb") as f:
                writer.write(f)
            tp = len(writer.pages)
            self._log(f"✅  {len(files)} PDFs unidos → {tp} páginas → {os.path.basename(output)}", "success")
            self.root.after(0, lambda: self.m_status.configure(text=f"Concluído! {tp} páginas"))
        except Exception as e:
            self._log(f"❌ Erro: {e}", "error")
        finally:
            self.root.after(0, lambda: self.m_btn.configure(
                text="📎   JUNTAR PDFs", state="normal", fg_color=ACCENT_DIM, hover_color=ACCENT))

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

            if self._version_newer(latest_tag, APP_VERSION):
                download_url = data.get("html_url", "")
                self.root.after(0, lambda: self._show_update_banner(latest_tag, download_url))
        except Exception:
            pass

    def _toggle_readme(self):
        """Alterna entre a view atual e o Leia-me."""
        if self._in_readme:
            self.readme_frame.pack_forget()
            self._in_readme = False
            self.btn_readme.configure(text="ℹ️  Leia-me", fg_color=BG_INPUT)
            # Volta para a página onde estava
            for page in self._pages.values():
                page.pack_forget()
            if self._current_page in self._pages:
                self._pages[self._current_page].pack(fill="both", expand=True)
        else:
            for page in self._pages.values():
                page.pack_forget()
            
            self.readme_frame.pack(fill="both", expand=True)
            self.readme_frame.lift() # Garante que está no topo
            self._in_readme = True
            self.btn_readme.configure(text="←", fg_color=BG_HOVER)

            # Desativa cores dos outros botões
            for btn in [self.btn_nav_rename, self.btn_nav_simple, self.btn_nav_merge, self.btn_nav_profiles]:
                btn.configure(fg_color=BG_INPUT, text_color=FG_TEXT)

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

        add("DivitorPDF v1.2", "title")
        add("Ferramenta completa para PDFs", "muted")
        sep()

        add("━━━  FUNCIONALIDADES  ━━━", "section")
        sep()
        add("  📝  Dividir e Renomear", "bullet")
        add("     Divide o PDF e renomeia cada página com o nome")
        add("     do funcionário encontrado no texto da página.")
        add("     Usa perfis de rótulos para identificar nomes.")
        sep()
        add("  ✂️  Divisão Simples", "bullet")
        add("     Divide o PDF em páginas individuais (Pagina_1.pdf, ...).")
        sep()
        add("  📎  Juntar PDFs", "bullet")
        add("     Seleciona múltiplos PDFs e junta todos em um")
        add("     único arquivo PDF na ordem escolhida.")
        sep()
        add("  ⚙️  Configuração de Perfis", "bullet")
        add("     Crie e edite perfis personalizados para busca")
        add("     de nomes e padrões de nomenclatura.")
        sep()

        add("━━━  COMO USAR  ━━━", "section")
        sep()
        add("  1.  Selecione o modo desejado no menu superior", "bullet")
        add("  2.  Selecione o PDF ou arraste-o para a área central", "bullet")
        add("  3.  Escolha uma pasta de saída", "bullet")
        add("  4.  Clique no botão de ação principal", "bullet")
        sep()

        add("━━━  LIMITAÇÕES  ━━━", "section")
        sep()
        add("  ⚠  PDF precisa ter texto selecionável (Modo Renomear)", "warn")
        add("     PDFs escaneados (imagem) não funcionam para renomeio automático.")
        sep()

        content.configure(state="disabled")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = DivitorPDFApp()
    app.run()
