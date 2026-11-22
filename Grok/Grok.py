import pygame
import sys
import os
import shutil
import time
import re
import html
import subprocess
import platform
import json
from datetime import datetime
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==================== CONFIG / PERSISTENCE ====================
CONFIG_FILE = "grok_gui_config.json"
CODE_TYPES_FILE = "code_types.txt"
DEFAULT_CHROME_VERSION = 146

def load_config():
    defaults = {
        "chrome_version": DEFAULT_CHROME_VERSION,
        "last_script": "script.py",
        "last_code_type": "python",
        "skill": "Using pygame.",
        "code_types": ["python", "javascript", "bash", "html", "css"]
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except:
            pass
    if os.path.exists(CODE_TYPES_FILE):
        try:
            with open(CODE_TYPES_FILE, "r", encoding="utf-8") as f:
                types = [line.strip() for line in f if line.strip()]
                if types:
                    defaults["code_types"] = types
        except:
            pass
    return defaults

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    with open(CODE_TYPES_FILE, "w", encoding="utf-8") as f:
        for t in config.get("code_types", []):
            f.write(t + "\n")

config = load_config()

GROK_URL = "https://grok.com"
LOGIN_URL = "https://x.com/login"
LOG_FILE = "grok_session_log.txt"
CODE_INSTRUCTION = "   Always show all the code in a single coding box (```python ... ```)."
MAX_WAIT_SECONDS = 90
POLL_INTERVAL = 1.5
GROK_BUTTON_TIMEOUT = 300

# ==================== CLIPBOARD ====================
def copy_to_clipboard(text):
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except ImportError:
        pass
    if platform.system() == "Darwin":
        try:
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, close_fds=True)
            p.communicate(text.encode("utf-8"))
            return True
        except:
            return False
    return False

def paste_from_clipboard():
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except ImportError:
        pass
    if platform.system() == "Darwin":
        try:
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, check=False)
            return r.stdout or ""
        except:
            return ""
    return ""

# ==================== LOG / SIDECAR ====================
def parse_log():
    if not os.path.exists(LOG_FILE):
        return []
    entries = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    for block in content.split("===\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if len(lines) >= 4:
            entries.append({
                "datetime": lines[0],
                "filename": lines[1],
                "url": lines[2],
                "prompt": "\n".join(lines[3:])
            })
    return entries

def log_entry(filename, url, prompt):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("===\n")
        f.write(f"{now}\n{filename}\n{url}\n{prompt}\n")

def grok_sidecar_path(script_name):
    base = os.path.splitext(script_name)[0]
    return base + ".grok.txt"

def save_sidecar(script_name, prompt, url=""):
    path = grok_sidecar_path(script_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"URL: {url}\n")
        f.write("---PROMPT---\n")
        f.write(prompt)

def load_sidecar(script_name):
    path = grok_sidecar_path(script_name)
    if not os.path.exists(path):
        return "", ""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    url = ""
    prompt = content
    if content.startswith("URL:"):
        lines = content.split("\n", 2)
        if len(lines) >= 1:
            url = lines[0][4:].strip()
        if "---PROMPT---" in content:
            prompt = content.split("---PROMPT---", 1)[1].lstrip("\n")
    return prompt, url

def get_history_for_filename(filename):
    return [e for e in parse_log() if e["filename"] == filename]

# ==================== BROWSER ====================
def start_browser(chrome_version):
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    try:
        driver = uc.Chrome(
            options=options,
            version_main=int(chrome_version),
            use_subprocess=True
        )
        driver.get(LOGIN_URL)
        return driver
    except Exception as e:
        raise RuntimeError(f"Failed to start Chrome (version {chrome_version}): {e}")

def try_auto_login(driver):
    username = os.environ.get("GROK_USERNAME")
    if not username:
        return False
    try:
        user_el = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//input[@name='text' or @autocomplete='username' or contains(@placeholder,'Phone') or contains(@placeholder,'email')]"))
        )
        user_el.clear()
        user_el.send_keys(username)
        user_el.send_keys(Keys.ENTER)
        time.sleep(2)
        return True
    except Exception as e:
        print("Auto-login partial failure:", e)
        return False

def wait_for_grok_button(driver, timeout=GROK_BUTTON_TIMEOUT):
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, "//a[@aria-label='Grok']"))
        )
        return True
    except:
        return False

def click_grok_or_goto(driver, fallback_url=None):
    try:
        btn = driver.find_element(By.XPATH, "//a[@aria-label='Grok']")
        btn.click()
        time.sleep(2)
        return True
    except:
        if fallback_url:
            driver.get(fallback_url)
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            return True
    return False

def send_prompt_to_grok(driver, prompt, new_session=False):
    try:
        if new_session:
            driver.get(GROK_URL)
            time.sleep(2)
        selectors = ["textarea", "[data-testid='grokInput']", "div[contenteditable='true']", "textarea[placeholder]"]
        input_box = None
        for sel in selectors:
            try:
                input_box = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                break
            except:
                continue
        if not input_box:
            return False
        input_box.click()
        input_box.clear()
        input_box.send_keys(prompt)
        input_box.send_keys(Keys.ENTER)
        return True
    except Exception as e:
        print("Send error:", e)
        return False

def extract_code(html_source, language="python"):
    if not html_source:
        return ""
    language = (language or "python").strip().lower()
    aliases = {"python": r"python|py", "javascript": r"javascript|js", "bash": r"bash|sh|shell", "html": r"html", "css": r"css"}
    lang_pattern = aliases.get(language, re.escape(language))
    pattern = rf"```(?:{lang_pattern})\s*\n(.*?)```"
    blocks = re.findall(pattern, html_source, re.DOTALL | re.IGNORECASE)
    if blocks:
        return html.unescape(blocks[-1].strip())
    fallback = rf"```\s*{language}\s*\n(.*?)```"
    blocks = re.findall(fallback, html_source, re.DOTALL | re.IGNORECASE)
    if blocks:
        return html.unescape(blocks[-1].strip())
    pres = re.findall(r"<pre[^>]*>(.*?)</pre>", html_source, re.DOTALL | re.IGNORECASE)
    if pres:
        cleaned = [re.sub(r"<[^>]+>", "", p).strip() for p in pres]
        cleaned = [c for c in cleaned if len(c) > 20]
        if cleaned:
            return html.unescape(cleaned[-1])
    return ""

def wait_for_grok_response(driver, language="python", status_callback=None):
    start = time.time()
    last_code = ""
    stable = 0
    while time.time() - start < MAX_WAIT_SECONDS:
        if status_callback:
            status_callback(f"Waiting for Grok… {int(time.time()-start)}s")
        pygame.display.flip()
        pygame.event.pump()
        try:
            code = extract_code(driver.page_source, language)
            if code and len(code) > 30:
                if code == last_code:
                    stable += 1
                    if stable >= 3:
                        return code
                else:
                    stable = 0
                    last_code = code
        except:
            pass
        time.sleep(POLL_INTERVAL)
    try:
        return extract_code(driver.page_source, language)
    except:
        return ""

def backup_file(filename):
    if not os.path.exists(filename):
        return
    base, ext = os.path.splitext(filename)
    i = 1
    while True:
        bk = f"{base}V{i:04d}.bkup"
        if not os.path.exists(bk):
            shutil.copy2(filename, bk)
            return
        i += 1

# ==================== TEXT HELPERS ====================
def wrap_text(text, font, max_width):
    if not text:
        return [""]
    lines = []
    for raw in text.split("\n"):
        words = raw.split(" ")
        cur = ""
        for w in words:
            test = cur + (" " if cur else "") + w
            if font.size(test)[0] <= max_width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        lines.append(cur if cur else "")
    return lines if lines else [""]

# ==================== INPUT BOX (scrollable + selection) ====================
class InputBox:
    def __init__(self, x, y, w, h, text="", multiline=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = (100, 100, 120)
        self.text = text
        self.cursor = len(text)
        self.sel_start = None
        self.sel_end = None
        self.active = False
        self.multiline = multiline
        self.font = pygame.font.SysFont("consolas", 20)
        self.dragging = False
        self.scroll = 0  # line offset

    def get_selection(self):
        if self.sel_start is None or self.sel_end is None:
            return None
        a, b = sorted([self.sel_start, self.sel_end])
        return self.text[a:b]

    def delete_selection(self):
        if self.sel_start is None:
            return
        a, b = sorted([self.sel_start, self.sel_end])
        self.text = self.text[:a] + self.text[b:]
        self.cursor = a
        self.sel_start = self.sel_end = None

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = True
                self.color = (80, 160, 255)
                self.cursor = len(self.text)
                self.sel_start = self.cursor
                self.dragging = True
            else:
                self.active = False
                self.color = (100, 100, 120)
                self.sel_start = self.sel_end = None
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEWHEEL and self.active and self.multiline:
            self.scroll = max(0, self.scroll - event.y)
        if not self.active or event.type != pygame.KEYDOWN:
            return
        mods = pygame.key.get_mods()
        if mods & pygame.KMOD_CTRL:
            if event.key == pygame.K_c:
                sel = self.get_selection()
                copy_to_clipboard(sel if sel else self.text)
                return
            if event.key == pygame.K_x:
                sel = self.get_selection()
                if sel:
                    copy_to_clipboard(sel)
                    self.delete_selection()
                else:
                    copy_to_clipboard(self.text)
                    self.text = ""
                    self.cursor = 0
                return
            if event.key == pygame.K_v:
                pasted = paste_from_clipboard()
                if pasted:
                    if self.get_selection():
                        self.delete_selection()
                    self.text = self.text[:self.cursor] + pasted + self.text[self.cursor:]
                    self.cursor += len(pasted)
                return
            if event.key == pygame.K_a:
                self.sel_start = 0
                self.sel_end = len(self.text)
                self.cursor = len(self.text)
                return
        if event.key == pygame.K_LEFT:
            self.cursor = max(0, self.cursor - 1)
            if not (mods & pygame.KMOD_SHIFT):
                self.sel_start = self.sel_end = None
        elif event.key == pygame.K_RIGHT:
            self.cursor = min(len(self.text), self.cursor + 1)
            if not (mods & pygame.KMOD_SHIFT):
                self.sel_start = self.sel_end = None
        elif event.key == pygame.K_UP and self.multiline:
            self.scroll = max(0, self.scroll - 1)
        elif event.key == pygame.K_DOWN and self.multiline:
            self.scroll += 1
        elif event.key == pygame.K_BACKSPACE and self.cursor > 0:
            if self.get_selection():
                self.delete_selection()
            else:
                self.text = self.text[:self.cursor-1] + self.text[self.cursor:]
                self.cursor -= 1
        elif event.key == pygame.K_DELETE:
            if self.get_selection():
                self.delete_selection()
            elif self.cursor < len(self.text):
                self.text = self.text[:self.cursor] + self.text[self.cursor+1:]
        elif event.key == pygame.K_RETURN and self.multiline:
            self.text = self.text[:self.cursor] + "\n" + self.text[self.cursor:]
            self.cursor += 1
        elif event.key == pygame.K_TAB:
            self.text = self.text[:self.cursor] + "    " + self.text[self.cursor:]
            self.cursor += 4
        elif event.unicode and event.key not in (pygame.K_RETURN,):
            if self.get_selection():
                self.delete_selection()
            self.text = self.text[:self.cursor] + event.unicode + self.text[self.cursor:]
            self.cursor += len(event.unicode)

    def draw(self, surface):
        pygame.draw.rect(surface, self.color, self.rect, 2)
        wrapped = wrap_text(self.text, self.font, self.rect.width - 12)
        max_visible = max(1, (self.rect.height - 8) // 22)
        self.scroll = max(0, min(self.scroll, max(0, len(wrapped) - max_visible)))
        y = self.rect.y + 4
        for i, line in enumerate(wrapped[self.scroll:self.scroll + max_visible]):
            if not line:
                continue  # avoid zero-width render
            surf = self.font.render(line, True, (240, 240, 240))
            surface.blit(surf, (self.rect.x + 4, y))
            y += 22
            if y > self.rect.bottom - 20:
                break
        if self.active:
            # simple cursor at end of visible text
            vis = wrapped[self.scroll:self.scroll + max_visible]
            if vis:
                last = vis[-1] if vis[-1] else " "
                cx = self.rect.x + 4 + self.font.size(last)[0]
                cy = self.rect.y + 4 + (len(vis)-1)*22
                if cy < self.rect.bottom - 10:
                    pygame.draw.line(surface, (255, 255, 0), (cx, cy), (cx, cy+18), 2)

# ==================== COMBO ====================
class ComboBox:
    def __init__(self, x, y, w, h, items, selected):
        self.rect = pygame.Rect(x, y, w, h)
        self.items = items[:]
        self.selected = selected if selected in items else (items[0] if items else "")
        self.open = False
        self.font = pygame.font.SysFont("consolas", 18)

    def handle_event(self, event, mouse):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.open = not self.open
                return True
            elif self.open:
                for i, item in enumerate(self.items):
                    ir = pygame.Rect(self.rect.x, self.rect.bottom + i*28, self.rect.w, 28)
                    if ir.collidepoint(event.pos):
                        self.selected = item
                        self.open = False
                        return True
                add_rect = pygame.Rect(self.rect.x, self.rect.bottom + len(self.items)*28, self.rect.w, 28)
                if add_rect.collidepoint(event.pos):
                    self.open = False
                    return "add"
                self.open = False
        return False

    def draw(self, surface):
        pygame.draw.rect(surface, (70, 70, 90), self.rect)
        pygame.draw.rect(surface, (180, 180, 200), self.rect, 1)
        surface.blit(self.font.render(self.selected or "", True, (240, 240, 240)), (self.rect.x+6, self.rect.y+6))
        if self.open:
            for i, item in enumerate(self.items):
                ir = pygame.Rect(self.rect.x, self.rect.bottom + i*28, self.rect.w, 28)
                pygame.draw.rect(surface, (50, 50, 70), ir)
                surface.blit(self.font.render(item, True, (220, 220, 220)), (ir.x+6, ir.y+4))
            add_rect = pygame.Rect(self.rect.x, self.rect.bottom + len(self.items)*28, self.rect.w, 28)
            pygame.draw.rect(surface, (40, 80, 40), add_rect)
            surface.blit(self.font.render("+ Add type…", True, (200, 255, 200)), (add_rect.x+6, add_rect.y+4))

# ==================== MAIN ====================
pygame.init()
pygame.key.set_repeat(400, 40)

WIDTH, HEIGHT = 1100, 820
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("Grok Coding Assistant")
font = pygame.font.SysFont("consolas", 20)
small_font = pygame.font.SysFont("consolas", 16)
clock = pygame.time.Clock()

filename_box = InputBox(20, 50, 340, 36, config["last_script"])
chrome_ver_box = InputBox(380, 50, 70, 36, str(config["chrome_version"]))
code_combo = ComboBox(470, 50, 140, 36, config["code_types"], config["last_code_type"])
skill_box = InputBox(20, 100, 1060, 70, config.get("skill", "Using pygame."), multiline=True)
prompt_box = InputBox(20, 190, 1060, 280, "", multiline=True)

p, u = load_sidecar(config["last_script"])
if p:
    prompt_box.text = p
    prompt_box.cursor = len(p)

status = "Ready. Click Start."
logged_in = False
driver = None
pending_url = None
history_index = -1
current_history = []
confirm_stop = False
adding_type = False
new_type_text = ""
run_output = ""

def reload_history():
    global current_history, history_index
    fname = filename_box.text.strip()
    current_history = get_history_for_filename(fname)
    history_index = len(current_history)

def set_status(msg):
    global status
    status = msg

def on_filename_change():
    global pending_url
    fname = filename_box.text.strip()
    if not fname:
        return
    if prompt_box.text.strip():
        url = driver.current_url if driver else (pending_url or "")
        save_sidecar(fname, prompt_box.text, url)
    p, u = load_sidecar(fname)
    if p:
        prompt_box.text = p
        prompt_box.cursor = len(p)
    if u:
        pending_url = u
        if driver and logged_in:
            try:
                driver.get(u)
                time.sleep(1.5)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except:
                pass
    config["last_script"] = fname
    save_config(config)
    reload_history()

reload_history()

running = True
while running:
    mouse = pygame.mouse.get_pos()
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            config["chrome_version"] = int(chrome_ver_box.text or DEFAULT_CHROME_VERSION)
            config["last_script"] = filename_box.text.strip()
            config["last_code_type"] = code_combo.selected
            config["code_types"] = code_combo.items
            config["skill"] = skill_box.text
            save_config(config)
            if prompt_box.text.strip():
                save_sidecar(filename_box.text.strip(), prompt_box.text, driver.current_url if driver else "")
            running = False

        elif event.type == pygame.VIDEORESIZE:
            WIDTH, HEIGHT = event.w, event.h
            screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
            skill_box.rect.width = WIDTH - 40
            prompt_box.rect.width = WIDTH - 40
            prompt_box.rect.height = min(300, HEIGHT - 480)

        old_fname = filename_box.text
        filename_box.handle_event(event)
        if filename_box.text != old_fname and event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_TAB):
            on_filename_change()

        chrome_ver_box.handle_event(event)
        skill_box.handle_event(event)
        prompt_box.handle_event(event)

        combo_res = code_combo.handle_event(event, mouse)
        if combo_res == "add":
            adding_type = True
            new_type_text = ""
            set_status("Type new language and press Enter")

        if adding_type and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN and new_type_text.strip():
                nt = new_type_text.strip()
                if nt not in code_combo.items:
                    code_combo.items.append(nt)
                    code_combo.selected = nt
                    config["code_types"] = code_combo.items
                    save_config(config)
                adding_type = False
                set_status(f"Added type: {nt}")
            elif event.key == pygame.K_ESCAPE:
                adding_type = False
            elif event.key == pygame.K_BACKSPACE:
                new_type_text = new_type_text[:-1]
            elif event.unicode:
                new_type_text += event.unicode

        if event.type == pygame.MOUSEBUTTONDOWN:
            if pygame.Rect(630, 40, 90, 40).collidepoint(event.pos) and not driver:
                try:
                    ver = int(chrome_ver_box.text or DEFAULT_CHROME_VERSION)
                    config["chrome_version"] = ver
                    save_config(config)
                    driver = start_browser(ver)
                    status = "Browser started. Logging in…"
                    pygame.display.flip()
                    if os.environ.get("GROK_USERNAME"):
                        try_auto_login(driver)
                    if wait_for_grok_button(driver, GROK_BUTTON_TIMEOUT):
                        logged_in = True
                        status = "Logged in (Grok button detected)."
                        if pending_url:
                            click_grok_or_goto(driver, pending_url)
                    else:
                        status = "Waiting for manual login… Click Logged in when ready."
                except Exception as e:
                    status = str(e)

            if pygame.Rect(730, 40, 80, 40).collidepoint(event.pos) and driver:
                confirm_stop = True
                status = "Click Stop again to confirm close browser"

            if confirm_stop and pygame.Rect(730, 40, 80, 40).collidepoint(event.pos):
                try:
                    driver.quit()
                except:
                    pass
                driver = None
                logged_in = False
                confirm_stop = False
                status = "Browser closed. You can Start again."

            if pygame.Rect(820, 40, 110, 40).collidepoint(event.pos) and driver and not logged_in:
                logged_in = True
                status = "Marked as Logged in."
                if pending_url:
                    click_grok_or_goto(driver, pending_url)

            if pygame.Rect(20, 490, 80, 36).collidepoint(event.pos):
                if current_history and history_index > 0:
                    history_index -= 1
                    e = current_history[history_index]
                    prompt_box.text = e["prompt"]
                    prompt_box.cursor = len(prompt_box.text)
                    if driver and e.get("url"):
                        try: driver.get(e["url"])
                        except: pass
                    status = f"History {history_index+1}/{len(current_history)}"

            if pygame.Rect(110, 490, 80, 36).collidepoint(event.pos):
                if history_index < len(current_history)-1:
                    history_index += 1
                    e = current_history[history_index]
                    prompt_box.text = e["prompt"]
                    prompt_box.cursor = len(prompt_box.text)
                    if driver and e.get("url"):
                        try: driver.get(e["url"])
                        except: pass
                    status = f"History {history_index+1}/{len(current_history)}"
                else:
                    history_index = len(current_history)
                    prompt_box.text = ""
                    status = "New prompt"

            if pygame.Rect(200, 490, 70, 36).collidepoint(event.pos):
                prompt_box.text = ""
                prompt_box.cursor = 0
                status = "Cleared"

            if pygame.Rect(280, 490, 90, 36).collidepoint(event.pos) and logged_in and driver:
                fname = filename_box.text.strip()
                up = prompt_box.text.strip()
                skill = skill_box.text.strip()
                lang = code_combo.selected or "python"
                if fname and up:
                    full = (skill + "\n\n" if skill else "") + up + CODE_INSTRUCTION
                    set_status("Sending…")
                    pygame.display.flip()
                    if send_prompt_to_grok(driver, full):
                        code = wait_for_grok_response(driver, lang, set_status)
                        if code and len(code) > 20:
                            backup_file(fname)
                            with open(fname, "w", encoding="utf-8") as f:
                                f.write(code)
                            log_entry(fname, driver.current_url, up)
                            save_sidecar(fname, up, driver.current_url)
                            reload_history()
                            status = f"Saved to {fname}"
                        else:
                            status = "No code found. Use Copy."
                    else:
                        status = "Send failed"

            if pygame.Rect(380, 490, 80, 36).collidepoint(event.pos) and driver:
                lang = code_combo.selected or "python"
                code = extract_code(driver.page_source, lang)
                fname = filename_box.text.strip()
                if code and fname:
                    backup_file(fname)
                    with open(fname, "w", encoding="utf-8") as f:
                        f.write(code)
                    status = f"Copied {lang} to {fname}"
                else:
                    status = "Nothing to copy"

            if pygame.Rect(470, 490, 90, 36).collidepoint(event.pos) and logged_in and driver:
                fname = filename_box.text.strip()
                entries = get_history_for_filename(fname)
                if entries:
                    set_status(f"Replaying {len(entries)}…")
                    driver.get(GROK_URL)
                    time.sleep(2)
                    lang = code_combo.selected or "python"
                    skill = skill_box.text.strip()
                    for i, e in enumerate(entries):
                        set_status(f"Replay {i+1}/{len(entries)}")
                        full = (skill + "\n\n" if skill else "") + e["prompt"] + CODE_INSTRUCTION
                        send_prompt_to_grok(driver, full)
                        wait_for_grok_response(driver, lang, set_status)
                        time.sleep(1)
                    status = "Replay done"
                else:
                    status = "No history"

            if pygame.Rect(570, 490, 90, 36).collidepoint(event.pos):
                fname = filename_box.text.strip()
                if fname and os.path.exists(fname):
                    try:
                        proc = subprocess.Popen(
                            [sys.executable, fname],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True
                        )
                        out, err = proc.communicate(timeout=60)
                        run_output = (out or "") + (("\n--- STDERR ---\n" + err) if err else "")
                        status = "Script finished. Output below."
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        status = "Script timed out (60s)"
                        run_output = "Timed out"
                    except Exception as e:
                        status = f"Run error: {e}"
                        run_output = str(e)
                else:
                    status = "Script file not found"
                    run_output = ""

    # Draw
    screen.fill((30, 30, 40))
    screen.blit(font.render("File:", True, (240,240,240)), (20, 15))
    screen.blit(font.render("Chrome ver:", True, (240,240,240)), (380, 15))
    screen.blit(font.render("Type:", True, (240,240,240)), (470, 15))
    screen.blit(small_font.render("Skill/Context (prepended):", True, (200,200,220)), (20, 82))

    filename_box.draw(screen)
    chrome_ver_box.draw(screen)
    code_combo.draw(screen)
    skill_box.draw(screen)
    prompt_box.draw(screen)

    def btn(r, t):
        c = (70,160,90) if r.collidepoint(mouse) else (50,130,70)
        pygame.draw.rect(screen, c, r)
        screen.blit(font.render(t, True, (255,255,255)), (r.x+6, r.y+6))

    btn(pygame.Rect(630, 40, 90, 40), "Start")
    btn(pygame.Rect(730, 40, 80, 40), "Stop")
    btn(pygame.Rect(820, 40, 110, 40), "Logged in")
    btn(pygame.Rect(20, 490, 80, 36), "Prev")
    btn(pygame.Rect(110, 490, 80, 36), "Next")
    btn(pygame.Rect(200, 490, 70, 36), "Clear")
    btn(pygame.Rect(280, 490, 90, 36), "Send")
    btn(pygame.Rect(380, 490, 80, 36), "Copy")
    btn(pygame.Rect(470, 490, 90, 36), "Replay")
    btn(pygame.Rect(570, 490, 90, 36), "Run")

    if adding_type:
        screen.blit(small_font.render("New type: " + new_type_text, True, (255,255,100)), (20, 530))

    y = 540
    for line in wrap_text(status, small_font, WIDTH-40)[:3]:
        screen.blit(small_font.render(line, True, (180,220,180)), (20, y))
        y += 18
    if run_output:
        screen.blit(small_font.render("Run output:", True, (220,220,100)), (20, y))
        y += 18
        for line in wrap_text(run_output, small_font, WIDTH-40)[:12]:
            screen.blit(small_font.render(line, True, (200,200,160)), (20, y))
            y += 16

    pygame.display.flip()
    clock.tick(30)

if driver:
    try:
        driver.quit()
    except:
        pass
pygame.quit()
sys.exit()j