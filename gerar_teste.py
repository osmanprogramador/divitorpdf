"""
Gera um PDF de teste simulando contracheques com nomes de funcionários.
"""
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os

EMPLOYEES = [
    ("012437", "CARLOS EDUARDO SOUZA"),
    ("015892", "MARIA FERNANDA OLIVEIRA"),
    ("023001", "JOSÉ CARLOS PEREIRA"),
    ("008754", "ANA BEATRIZ COSTA"),
    ("031290", "PEDRO HENRIQUE ALMEIDA"),
]

OUTPUT = os.path.join(os.path.dirname(__file__), "teste_contracheques.pdf")


def create_test_pdf():
    c = canvas.Canvas(OUTPUT, pagesize=A4)
    width, height = A4

    for matricula, nome in EMPLOYEES:
        # Título
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width / 2, height - 50, "Demonstrativo de Pagamento")

        # Linha do funcionário (igual ao formato real)
        c.setFont("Helvetica", 11)
        c.drawString(30, height - 80, f"Func.:  {matricula} - {nome}")
        c.drawRightString(width - 30, height - 80, "Período: 02/2026")

        # Linha separadora
        c.setStrokeColorRGB(0, 0, 0)
        c.line(30, height - 90, width - 30, height - 90)

        # Conteúdo fictício
        c.setFont("Helvetica", 10)
        y = height - 120
        items = [
            ("Salário Base", "R$ 3.500,00"),
            ("Horas Extras", "R$ 450,00"),
            ("Vale Transporte", "-R$ 180,00"),
            ("INSS", "-R$ 420,00"),
            ("IRRF", "-R$ 210,00"),
        ]
        for desc, valor in items:
            c.drawString(50, y, desc)
            c.drawRightString(width - 50, y, valor)
            y -= 25

        c.line(30, y - 5, width - 30, y - 5)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y - 30, "Líquido a Receber:")
        c.drawRightString(width - 50, y - 30, "R$ 3.140,00")

        c.showPage()

    c.save()
    print(f"✅ PDF de teste criado: {OUTPUT}")
    print(f"   Páginas: {len(EMPLOYEES)}")
    for m, n in EMPLOYEES:
        print(f"   - {m}: {n}")


if __name__ == "__main__":
    create_test_pdf()
