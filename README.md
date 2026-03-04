# ✂️ DivitorPDF

Ferramenta desktop para dividir arquivos PDF em páginas individuais, renomeando cada arquivo automaticamente com o nome encontrado no conteúdo da página.

## ✨ Funcionalidades

- 📄 Divide PDF em arquivos individuais por página
- 🔍 Identifica nomes automaticamente via rótulos configuráveis
- 🏷️ Sistema de perfis: rótulos padrão + personalizados
- 📂 Arrastar e soltar (drag & drop)
- 🎨 Interface moderna com tema dark
- 🔄 Verificação automática de atualizações

## 📋 Perfis de Rótulos

O DivitorPDF vem com o perfil **Contracheque (Padrão)** que reconhece rótulos como:
- `Func.:`, `Funcionário:`, `Nome:`, `Empregado:`, `Colaborador:`, `Servidor:`

Você pode criar **perfis personalizados** com seus próprios rótulos para qualquer tipo de documento (Informe de Rendimento, Prontuário, etc).

## 🚀 Download

Baixe a última versão na página de [Releases](../../releases).

## 🛠️ Desenvolvimento

### Requisitos
- Python 3.10+
- Dependências: `pip install -r requirements.txt`

### Executar
```bash
python main.py
```

### Build (EXE)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name DivitorPDF main.py
```

## 📄 Licença

Uso interno — Powered by Zonninet
