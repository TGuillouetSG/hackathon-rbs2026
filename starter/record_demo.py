"""Record a single narrated demo of clients 001 and 003 with Playwright.

Run from starter: uv run python record_demo.py
The Flask app must be available at DEMO_URL (default http://127.0.0.1:5000).
"""

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright


@dataclass(frozen=True)
class Config:
    base_url: str = os.getenv("DEMO_URL", "http://127.0.0.1:5000").rstrip("/")
    output_dir: Path = Path(
        os.getenv("DEMO_OUTPUT_DIR", str(Path(__file__).parent / "output" / "demo"))
    ).resolve()
    width: int = int(os.getenv("DEMO_WIDTH", "1440"))
    height: int = int(os.getenv("DEMO_HEIGHT", "900"))
    scroll_step_px: int = int(os.getenv("DEMO_SCROLL_STEP_PX", "65"))
    scroll_delay_ms: int = int(os.getenv("DEMO_SCROLL_DELAY_MS", "700"))
    click_pause_ms: int = int(os.getenv("DEMO_CLICK_PAUSE_MS", "350"))
    scene_pause_ms: int = int(os.getenv("DEMO_SCENE_PAUSE_MS", "900"))
    workflow_timeout_ms: int = int(os.getenv("DEMO_WORKFLOW_TIMEOUT_MS", "180000"))
    max_takes: int = int(os.getenv("DEMO_MAX_TAKES", "3"))
    questions_per_topic: int = int(os.getenv("DEMO_QUESTIONS_PER_TOPIC", "1"))
    mouse_move_ms: int = int(os.getenv("DEMO_MOUSE_MOVE_MS", "350"))
    mouse_hover_ms: int = int(os.getenv("DEMO_MOUSE_HOVER_MS", "120"))
    headless: bool = os.getenv("DEMO_HEADLESS") == "1"
    browser_channel: str | None = os.getenv("DEMO_BROWSER_CHANNEL") or None


CONFIG = Config()

# Playwright's video records page pixels. Draw a cursor in the page so viewers
# can see the pointer movement even when the browser's native cursor is omitted.
CURSOR_SCRIPT = """(() => {
  document.addEventListener('DOMContentLoaded', () => {
    const cursor = document.createElement('div');
    cursor.id = 'demo-recording-cursor';
    cursor.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;display:none;width:28px;height:32px;filter:drop-shadow(0 1px 2px white) drop-shadow(0 0 2px white)';
    cursor.innerHTML = '<svg width="28" height="32" viewBox="0 0 28 32" xmlns="http://www.w3.org/2000/svg"><path d="M2 2V25L8 19L13 30L18 27L12 17H25Z" fill="#175cd3" stroke="white" stroke-width="2" stroke-linejoin="round"/></svg>';
    document.body.append(cursor);
    document.addEventListener('mousemove', event => {
      window.__demoCursorPosition = {x: event.clientX, y: event.clientY};
      cursor.style.transform = `translate(${event.clientX}px, ${event.clientY}px)`;
      cursor.style.display = 'block';
    });
    document.addEventListener('mousedown', () => {
      cursor.style.filter = 'drop-shadow(0 0 5px #facc15) drop-shadow(0 0 8px #facc15)';
      setTimeout(() => { cursor.style.filter = 'drop-shadow(0 1px 2px white) drop-shadow(0 0 2px white)'; }, 350);
    });
  }, {once: true});
})();"""


def pause(milliseconds: int) -> None:
    time.sleep(milliseconds / 1000)


def move_mouse_to(page: Page, locator: Locator) -> None:
    locator.wait_for(state="visible")
    box = locator.bounding_box()
    if box is None:
        raise RuntimeError("Cannot move the cursor to a hidden control")
    target_x = box["x"] + box["width"] / 2
    target_y = box["y"] + box["height"] / 2
    start = page.evaluate(
        "window.__demoCursorPosition || {x: window.innerWidth / 2, y: window.innerHeight / 2}"
    )
    steps = max(1, CONFIG.mouse_move_ms // 35)
    for step in range(1, steps + 1):
        progress = step / steps
        # Ease in and out so the pointer settles naturally over each control.
        progress = progress * progress * (3 - 2 * progress)
        x = start["x"] + (target_x - start["x"]) * progress
        y = start["y"] + (target_y - start["y"]) * progress
        page.mouse.move(x, y)
        pause(CONFIG.mouse_move_ms / steps)
    pause(CONFIG.mouse_hover_ms)


def click_with_cursor(page: Page, locator: Locator) -> None:
    slow_scroll_to(page, locator)
    move_mouse_to(page, locator)
    locator.click()
    pause(CONFIG.click_pause_ms)


def slow_scroll_to(page: Page, locator: Locator) -> None:
    for _ in range(300):
        position = locator.evaluate(
            "element => ({top: element.getBoundingClientRect().top, height: window.innerHeight})"
        )
        if 80 <= position["top"] <= position["height"] * 0.72:
            return
        direction = 1 if position["top"] > position["height"] * 0.72 else -1
        old_y = page.evaluate("window.scrollY")
        page.mouse.wheel(0, direction * CONFIG.scroll_step_px)
        pause(CONFIG.scroll_delay_ms)
        if page.evaluate("window.scrollY") == old_y:
            return  # At the document edge; the control is still clickable.
    raise RuntimeError("Could not scroll to a demo control")


def slow_scroll_to_bottom(page: Page) -> None:
    for _ in range(300):
        if page.evaluate(
            "window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2"
        ):
            return
        page.mouse.wheel(0, CONFIG.scroll_step_px)
        pause(CONFIG.scroll_delay_ms)
    raise RuntimeError("Could not reach the bottom of the page")


def select_customer(page: Page, customer_id: str) -> None:
    selector = page.locator("#customer-select")
    slow_scroll_to(page, selector)
    move_mouse_to(page, selector)
    selector.select_option(customer_id)
    page.wait_for_url(f"{CONFIG.base_url}/?customer={customer_id}")
    number = "(001)" if customer_id == "marc" else "(003)"
    page.locator(".client-banner").get_by_text(number).wait_for()
    pause(CONFIG.scene_pause_ms)


def record_customer(page: Page, customer_id: str) -> None:
    select_customer(page, customer_id)
    click_with_cursor(
        page, page.get_by_role("link", name=re.compile("Préparer prochain RDV"))
    )
    page.wait_for_url(f"{CONFIG.base_url}/rdv?customer={customer_id}")

    # The workflow starts automatically. Record its loading sequence.
    page.wait_for_function(
        """() => {
          const result = document.querySelector('#workflow-result');
          const error = document.querySelector('#workflow-error');
          return result && !result.hidden && error;
        }""",
        timeout=CONFIG.workflow_timeout_ms,
    )
    error = page.locator("#workflow-error")
    analysis_failed = error.is_visible()
    if analysis_failed and customer_id != "nadia":
        raise RuntimeError(f"Analysis failed for {customer_id}: {error.inner_text()}")
    if analysis_failed:
        print("Nadia's expected analysis error is visible; continuing the demo.")
    topics = page.locator("#topics-list .topic")
    count = topics.count()
    if count == 0 and customer_id != "nadia":
        raise RuntimeError(f"Analysis produced no topics for {customer_id}")
    pause(CONFIG.scene_pause_ms)

    if analysis_failed:
        slow_scroll_to(page, error)
        pause(CONFIG.scene_pause_ms)
    elif count == 0 and customer_id == "nadia":
        warning = page.locator("#topics-warning")
        if warning.is_visible():
            slow_scroll_to(page, warning)
            pause(CONFIG.scene_pause_ms)

    for index in range(count):
        details = topics.nth(index).locator("details")
        summary = details.get_by_text("Approfondir")
        click_with_cursor(page, summary)
        questions = details.locator('input[type="checkbox"]')
        for question in range(min(questions.count(), CONFIG.questions_per_topic)):
            checkbox = questions.nth(question)
            slow_scroll_to(page, checkbox)
            move_mouse_to(page, checkbox)
            checkbox.check()
            pause(CONFIG.click_pause_ms)

    agenda = page.locator("#agenda-button")
    click_with_cursor(page, agenda)
    page.locator("#agenda-panel").wait_for(state="visible")
    slow_scroll_to_bottom(page)
    pause(CONFIG.scene_pause_ms)


def record_take(attempt: int) -> None:
    with sync_playwright() as playwright:
        launch_options = {"headless": CONFIG.headless}
        if CONFIG.browser_channel:
            launch_options["channel"] = CONFIG.browser_channel
        browser = playwright.chromium.launch(**launch_options)
        context = browser.new_context(
            viewport={"width": CONFIG.width, "height": CONFIG.height},
            record_video_dir=str(CONFIG.output_dir),
            record_video_size={"width": CONFIG.width, "height": CONFIG.height},
        )
        context.add_init_script(script=CURSOR_SCRIPT)
        page = context.new_page()
        video = page.video
        success = False
        try:
            page.goto(CONFIG.base_url, wait_until="domcontentloaded")
            page.locator("#customer-select").wait_for()
            pause(CONFIG.scene_pause_ms)
            record_customer(page, "marc")
            click_with_cursor(
                page, page.get_by_role("link", name=re.compile("Retour à la synthèse"))
            )
            page.wait_for_url(re.compile(r"/\?customer=marc$"))
            pause(CONFIG.scene_pause_ms)
            record_customer(page, "nadia")
            success = True
        finally:
            context.close()  # Flush the video before moving or deleting it.
            browser.close()
            if video is not None:
                source = Path(video.path())
                if success:
                    destination = CONFIG.output_dir / "rdv-demo-001-003.webm"
                    source.replace(destination)
                    print(f"Recorded: {destination}")
                elif source.exists():
                    source.unlink()
                    print(f"Discarded failed take {attempt}")


def main() -> int:
    if CONFIG.max_takes < 1:
        raise ValueError("DEMO_MAX_TAKES must be at least 1")
    CONFIG.output_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, CONFIG.max_takes + 1):
        try:
            record_take(attempt)
            return 0
        except Exception as exc:
            print(f"Take {attempt}/{CONFIG.max_takes}: {exc}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
