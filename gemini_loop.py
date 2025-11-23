import time
from dotenv import load_dotenv
from google import genai
from playwright.sync_api import sync_playwright

load_dotenv()

client = genai.Client()

SCREEN_WIDTH = 1440
SCREEN_HEIGTH = 900

playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True)
context = browser.new_context(viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGTH})
page = context.new_page()

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
        else:
            print("Thoughts:")
            print(part.text)

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

            elif fname == "scroll_at":
                actual_x = denormalize_x(args["x"], screen_width)
                actual_y = denormalize_y(args["y"], screen_height)
                direction = args["direction"]

                if direction == "up":
                    magnitude = 0, - denormalize_y(args["magnitude"], screen_width)
                elif direction == "down":
                    magnitude = 0, denormalize_y(args["magnitude"], screen_width)
                elif direction == "left":
                    magnitude = - denormalize_x(args["magnitude"], screen_height), 0
                elif direction == "right":
                    magnitude = denormalize_x(args["magnitude"], screen_height), 0
                
                page.mouse.move(actual_x, actual_y)
                page.mouse.wheel(*magnitude)

            elif fname == "scroll_document":
                direction = args["direction"]

                if direction == "up":
                    page.evaluate("window.scrollTo(0, 0)")
                elif direction == "down":
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                elif direction == "left":
                    page.evaluate("window.scrollTo(0, 0)")
                elif direction == "right":
                    page.evaluate("window.scrollTo(document.body.scrollWidth, 0)")

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
            time.sleep(5)

        except Exception as e:
            print(f"Error executing {fname}: {e}")
            action_result = {"error": str(e)}

        results.append((fname, action_result))

    return results

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


excluded_functions = [
    "drag_and_drop",
    "open_web_browser",
    "scroll_document" # scroll muito brusco, costuma passar da informação
]

try:
    page.goto("https://www.go.gov.br/servicos-digitais/vapt-vupt/agendamento-atendimento-presencial/novo")

    config = genai.types.GenerateContentConfig(
        tools=[genai.types.Tool(computer_use=genai.types.ComputerUse(
            environment=genai.types.Environment.ENVIRONMENT_BROWSER,
            excluded_predefined_functions=excluded_functions,
        ))],
        thinking_config=genai.types.ThinkingConfig(include_thoughts=True)
    )

    initial_screenshot = page.screenshot(type="png")
    USER_PROMPT = """
        Descubra a data e horário mais próximos para agendar uma renovação de CNH.
        Dica: comece selecionando o Detran como órgão.

        ## Execution tips:
        - If clicking does not produce a response, check if the clicked position is disabled.
    """
    print(f"Goal: {USER_PROMPT}")

    contents = [
        genai.types.Content(role="user", parts=[
            genai.types.Part(text=USER_PROMPT),
            genai.types.Part.from_bytes(data=initial_screenshot, mime_type="image/png")
        ])
    ]

    turn_limit = 20
    for i in range(turn_limit):
        print(f"\n--- Turn {i} ---")
        print("Thinking")

        response = client.models.generate_content(
            model="gemini-2.5-computer-use-preview-10-2025",
            contents=contents,
            config=config
        )

        candidate = response.candidates[0]
        contents.append(candidate.content)

        # Se não há ações sugeridas na resposta, o modelo terminou
        has_function_calls = any(part.function_call for part in candidate.content.parts)
        if not has_function_calls:
            text_response = " ".join([part.text for part in candidate.content.parts if part.text])
            print("Agent finished:", text_response)
            break

        print("Executing actions...")
        results = execute_function_calls(candidate, page, SCREEN_WIDTH, SCREEN_HEIGTH)

        print("Capturing state...")
        function_responses = get_function_responses(page, results)

        page.screenshot(path=f"screenshots/turn_{i:02}_screenshot.png")

        contents.append(
            genai.types.Content(role="user", parts=[genai.types.Part(function_response=fr) for fr in function_responses])
        )

finally:
    print("Closing browser...")
    browser.close()
    playwright.stop()