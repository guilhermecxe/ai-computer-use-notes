import base64
from dotenv import load_dotenv
from openai import OpenAI
from playwright.sync_api import sync_playwright

load_dotenv()

# Definindo as proporções da tela do navegador
# A recomendação do Gemini é de 1440x900
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768

# Iniciando o navegador
playwright = sync_playwright().start()
browser = playwright.chromium.launch(
    headless=True,
    chromium_sandbox=True,
    env={}, # para não puxar as variáveis de ambiente
    args=[
        "--disable-extensions",
        "--disable-file-system"
    ]
)
# chromium_sandbox limita o controle do Playwright sobre camadas
# mais internas da máquina, aumentando a segurança da aplicação.

# Criando o contexto e uma nova página
context = browser.new_context(
    viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}
)
page = context.new_page()

# Acessando página
page.goto("https://goias.gov.br/fapeg/")

# Obtendo um screenshot da página
page_screenshot = page.screenshot()
page_screenshot_base64 = base64.b64encode(page_screenshot).decode("utf-8")

# ------ Criação do agente -------

client = OpenAI()

# Gerando o resultado do modelo
response = client.responses.create(
    model="computer-use-preview",
    tools=[{
        "type": "computer_use_preview",
        "display_width": SCREEN_WIDTH,
        "display_height": SCREEN_HEIGHT,
        "environment": "browser", # poderia ser também "mac", "windows" ou "ubuntu"
    }],
    input=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Descubra quais são os editais abertos da FAPEG"
                },
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{page_screenshot_base64}"
                }
            ]
        }
    ],
    reasoning={
        "summary": "concise"
    },
    truncation="auto" # para limitar o histórico se ficar longo demais
)

# Adicionando a respostas a um histórico
pass

print(f"Full Response:\n{response}")

# Computer-Use Preview da OpenAI ainda está em beta e disponível apenas para Tier 3
# ou acima