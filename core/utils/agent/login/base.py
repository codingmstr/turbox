from playwright.sync_api import sync_playwright
import random

class Base:

    def __init__ ( self ):

        self.headless   = True
        self.timeout    = None
        self.transition = None
        self.url        = None
        self.iframe     = None
        self.token_key  = None
        self.page       = None
        self.frame      = None
        self.browser    = None
        self.player     = None
        self.token      = None

    def open_browser ( self ):

        self.player = sync_playwright().start()
        self.browser = self.player.chromium.launch(headless=self.headless, slow_mo=self.transition)
        return self

    def close_browser ( self ):

        self.browser.close()
        self.player.stop()
        return self

    def new_tab ( self ):

        self.page = self.browser.new_page()
        return self

    def load_page ( self ):

        self.page.goto(self.url, timeout=self.timeout)
        self.page.wait_for_load_state("domcontentloaded")
        return self

    def load_frame ( self ):

        self.frame = self.page.wait_for_selector(f"iframe[src='{self.iframe}']", timeout=self.timeout).content_frame()
        return self

    def wait ( self, seconds: float ):

        self.page.wait_for_timeout(seconds * 1000)
        return self

    def mouse_up ( self ):

        self.page.mouse.up()
        return self

    def mouse_down ( self  ):

        self.page.mouse.down()
        return self

    def move_mouse ( self, x: float, y: float, steps: int = 1 ):

        self.page.mouse.move(x, y, steps=steps)
        return self

    def local_storage ( self, key: str ):

        return self.page.evaluate(f"() => localStorage.getItem('{key}')")

    def get ( self, element: str, parent: object ):

        try: return parent.wait_for_selector(element, timeout=self.timeout)
        except: return None

    def get_all ( self, element: str, parent: object ):

        try: return list(parent.query_selector_all(element))
        except: return []

    def text ( self, element: str, parent: object ):

        el = self.get(element, parent)
        return str(el.inner_text().strip()) if el else ''

    def click ( self, element: str, parent: object ):

        btn = self.get(element, parent)

        try: btn.click(force=True)
        except Exception: parent.evaluate("el => el.click()", btn)
        except: pass

        return self

    def fill ( self, element: str, parent: object, value: str ):
        
        try: parent.fill(element, value)
        except: pass

        return self

    def check ( self, element: str, parent: object ):

        try: parent.check(element, timeout=self.timeout)
        except: pass

        return self

    def select ( self, list_element: str, element: str, parent: object, value: str ):
        
        for option in self.get_all(list_element, parent):
            name = self.text(element, option)

            if str(name or '').lower() == str(value or '').lower():
                option.scroll_into_view_if_needed()
                option.click()
                break

        return self

    def coordinates ( self, element: str, parent: str ):

        el = self.get(element, parent)

        box = el.bounding_box() if el else None
        box = box or el.evaluate("el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; }")

        return [box['x'], box['y'], box['width'], box['height']] if box else [0, 0, 0, 0]

    def move ( self, element: str, parent: object, distance: float ):

        x, y, w, h = self.coordinates(element, parent)

        start_x = x + w / 2
        start_y = y + h / 2
        end_x   = start_x + distance

        self.move_mouse(start_x, start_y).mouse_down()
        total_steps = 35 + random.randint(-5, 5)

        for i in range(total_steps):
            t = i / total_steps
            ease = 3*t*t - 2*t*t*t
            cur_x = start_x + (end_x - start_x) * ease
            cur_y = start_y + random.uniform(-1, 1)

            self.move_mouse(cur_x, cur_y)
            self.wait(random.uniform(0.001, 0.006))

        self.mouse_up().wait(random.uniform(0.2, 0.5))
        return self

    def credentials ( self ):

        return self

    def workflow ( self ):

        return self

    def run_chain ( self ):

        self.open_browser().new_tab().load_page().workflow()
        return self.close_browser()

    def get_token ( self ):

        if not self.token: self.run_chain()
        return self.token
