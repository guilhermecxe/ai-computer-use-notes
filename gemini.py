from playwright.sync_api import sync_playwright
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Definindo as proporções da tela do navegador
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900

# Iniciando o navegador
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=False)

# Criando o contexto e uma nova página
context = browser.new_context(
    viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}
)
page = context.new_page()

# Acessando página
page.goto("https://www.google.com")

# Obtendo um screenshot da página
page_screenshot = page.screenshot()

# ------ Criação do agente -------

client = genai.Client()

# Especificando tools pré-definidas para desconsiderar
excluded_functions = ["drag_and_drop", "open_web_browser"]

# Definindo as tools que serão utilizadas
generate_content_config = genai.types.GenerateContentConfig(
    tools=[
        genai.types.Tool(
            computer_use=genai.types.ComputerUse(
                environment=genai.types.Environment.ENVIRONMENT_BROWSER,
                excluded_predefined_functions=excluded_functions,
            )
        )
    ]
)

# Criando o prompt a ser enviado
contents=[
    genai.types.Content(
        role="user",
        parts=[
            genai.types.Part(text="Search for the mean price of Acer Nitro in Brazil"),
            genai.types.Part.from_bytes(
                data=page_screenshot,
                mime_type="image/png"
            )
        ]
    )
]

# Gerando o resultado do modelo
response = client.models.generate_content(
    model="gemini-2.5-computer-use-preview-10-2025",
    contents=contents,
    config=generate_content_config
)

print("Response:")
print(response)