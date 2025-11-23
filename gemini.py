from playwright.sync_api import sync_playwright
from google import genai
from dotenv import load_dotenv
import time

load_dotenv()

# Definindo as proporções da tela do navegador
# A recomendação do Gemini é de 1440x900
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
page.goto("https://goias.gov.br/fapeg/")

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
contents = [
    genai.types.Content(
        role="user",
        parts=[
            genai.types.Part(text="Descubra quais são os editais abertos da FAPEG"),
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

# Adicionando a respostas a um histórico
contents.append(response.candidates[0].content)

# print(f"Full Response:\n{response}")

print("Suggested actions:")
for part in response.candidates[0].content.parts:
    print(part)
    print("---")

# As posições retornadas são sempre no intervalo de 0 a 999, então
# é preciso haver uma conversão para a escala utilizada.
def denormalize_x(x: int, screen_width: int) -> int:
    return int(x / 1000 * screen_width)

def denormalize_y(y: int, screen_height: int) -> int:
    """Convert normalized y coordinate (0-1000) to actual pixel coordinate."""
    return int(y / 1000 * screen_height)

def execute_function_calls(candidate, page, screen_width, screen_height):
    # Listando as ações (function calls) da resposta
    function_calls = []
    for part in candidate.content.parts:
        if part.function_call:
            function_calls.append(part.function_call)

    results = []
    for function_call in function_calls:
        action_result = {}
        fname = function_call.name
        args = function_call.args
        print(f"  -> Executing: {fname}")

        try:
            if fname == "click_at":
                actual_x = denormalize_x(args["x"], screen_width)
                actual_y = denormalize_y(args["y"], screen_height)
                page.mouse.click(actual_x, actual_y)

            elif fname == "navigate":
                url = args["url"]
                page.goto(url)

            elif fname == "type_text_at":
                actual_x = denormalize_x(args["x"], screen_width)
                actual_y = denormalize_y(args["y"], screen_height)
                text = args["text"]
                press_enter = args.get("press_enter", False)

                page.mouse.click(actual_x, actual_y)
                
                # Selecionando tudo da caixa de texto e apagando
                page.keyboard.press("Meta+A")
                page.keyboard.press("Backspace")

                page.keyboard.type(text)
                if press_enter:
                    page.keyboard.press("Enter")
            else:
                print(f"Warning: Unimplemented or custom function {fname}")

            # Esperando a página carregar e depois esperando mais um pouco
            page.wait_for_load_state(timeout=5000)
            time.sleep(1)

        except Exception as e:
            print(f"Error executing {fname}: {e}")
            action_result = {"error": str(e)}

        results.append((fname, action_result))

    return results

results = execute_function_calls(response.candidates[0], page, SCREEN_WIDTH, SCREEN_HEIGHT)

def get_function_responses(page, results):
    screenshot_bytes = page.screenshot(type="png")
    current_url = page.url
    
    # Cada ação executada é listada com a URL e um screenshot atual,
    # além do resultado referente a ela
    function_responses = []
    for name, result in results:
        response_data = {"url": current_url}
        response_data.update(result)
        function_responses.append(
            genai.types.FunctionResponse(
                name=name,
                response=response_data,
                parts=[genai.types.FunctionResponsePart(
                        inline_data=genai.types.FunctionResponseBlob(
                            mime_type="image/png",
                            data=screenshot_bytes))
                ]
            )
        )
    return function_responses

function_responses = get_function_responses(page, results)

# Adicionando a respostas a um histórico
# que será reenvido para a LLM
contents.append(
    genai.types.Content(role="user", parts=[genai.types.Part(function_response=fr) for fr in function_responses])
)

# Obtendo nova resposta para o novo estado
response = client.models.generate_content(
    model='gemini-2.5-computer-use-preview-10-2025',
    contents=contents,
    config=generate_content_config,
)
contents.append(response.candidates[0].content)

# print(f"Full Response:\n{response}")

print("Suggested actions:")
for part in response.candidates[0].content.parts:
    print(part)
    print("---")

results = execute_function_calls(response.candidates[0], page, SCREEN_WIDTH, SCREEN_HEIGHT)
# ...