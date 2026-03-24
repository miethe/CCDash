"""
CCDash README Screenshot Capture Script
Captures all 6 screenshots at 1280x720 for the README build system.
"""
import os
import time
from playwright.sync_api import sync_playwright, Page

BASE_URL = "http://localhost:3000"
OUT_DIR = "/Users/miethe/dev/homelab/development/CCDash/docs/screenshots"
PROJECT_ID = "3df0ff70-85fd-402f-a028-83cae8bcedc2"  # SkillMeat

os.makedirs(OUT_DIR, exist_ok=True)


def set_dark_theme(page: Page):
    page.evaluate("localStorage.setItem('ccdash:theme-mode:v1', 'dark')")


def dismiss_backdrop(page: Page):
    page.evaluate("(() => { document.querySelectorAll('div.fixed.inset-0').forEach(el => el.click()); })()")
    page.wait_for_timeout(300)


def ensure_project_loaded(page: Page, timeout: int = 25000):
    """Wait for SkillMeat data to appear; if not, manually select the project."""
    try:
        page.wait_for_selector('text="SkillMeat"', timeout=timeout)
        print("  (project: SkillMeat ready)")
        return True
    except Exception:
        pass

    # Try to select it via dropdown
    print("  (selecting project manually...)")
    try:
        # Click the project dropdown (whatever text it shows)
        proj_btn = page.locator("aside button, aside [role='button'], aside [class*='cursor-pointer']").first
        proj_btn.click(timeout=3000)
        page.wait_for_timeout(600)

        # Click SkillMeat (not "SkillMeat Example")
        items = page.locator("text=SkillMeat").all()
        for item in items:
            txt = item.inner_text(timeout=500)
            if txt.strip() == "SkillMeat":
                item.click()
                page.wait_for_timeout(5000)
                break
        page.wait_for_selector('text="SkillMeat"', timeout=10000)
        print("  (project: SkillMeat selected)")
        return True
    except Exception as e:
        print(f"  (project select failed: {e})")
        return False


def wait_for_content(page: Page, timeout: int = 8000):
    try:
        page.wait_for_selector(".animate-spin", state="hidden", timeout=timeout)
    except Exception:
        pass
    try:
        page.wait_for_function(
            "(() => !document.querySelector('.animate-spin') && "
            "!document.body.innerText.includes('Loading execution') && "
            "!document.body.innerText.includes('Loading analytics'))()",
            timeout=timeout,
        )
    except Exception:
        pass
    page.wait_for_timeout(600)


def goto(page: Page, url: str, extra_wait: int = 2000):
    page.goto(url)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(extra_wait)
    dismiss_backdrop(page)


def js_click(page: Page, selector: str) -> bool:
    """Click an element via JS, returning True if found."""
    return page.evaluate(f"(() => {{ const el = document.querySelector('{selector}'); if (el) {{ el.click(); return true; }} return false; }})()")


def js_click_contains(page: Page, tag: str, text: str) -> bool:
    """Click first element matching tag that contains text."""
    return page.evaluate(
        f"(() => {{ "
        f"const els = Array.from(document.querySelectorAll('{tag}')); "
        f"const el = els.find(e => e.textContent && e.textContent.includes('{text}')); "
        f"if (el) {{ el.click(); return true; }} "
        f"return false; "
        f"}})()"
    )


def capture(page: Page, filename: str):
    path = os.path.join(OUT_DIR, filename)
    page.screenshot(path=path)
    size = os.path.getsize(path)
    print(f"  ✓ {filename} ({size // 1024}KB)")
    return path


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            color_scheme="dark",
        )
        page = ctx.new_page()

        # --- Setup: load app, set theme, select project ---
        print("=== Setup ===")
        page.goto(f"{BASE_URL}/#/")
        page.wait_for_load_state("domcontentloaded")
        set_dark_theme(page)
        print("  (waiting for app to initialize...)")
        page.wait_for_timeout(5000)  # Give backend API time to respond
        ensure_project_loaded(page, timeout=25000)
        wait_for_content(page, timeout=10000)
        page.wait_for_timeout(1000)

        # --- Screenshot 1: Dashboard Hero ---
        print("\n[1/6] Dashboard Hero...")
        goto(page, f"{BASE_URL}/#/", extra_wait=3000)
        wait_for_content(page, timeout=10000)
        page.wait_for_timeout(1500)
        capture(page, "dashboard-hero.png")

        # --- Screenshot 2: Session Inspector ---
        print("\n[2/6] Session Inspector...")
        goto(page, f"{BASE_URL}/#/sessions", extra_wait=2500)
        wait_for_content(page, timeout=8000)
        page.wait_for_timeout(1000)

        # Click first session card
        try:
            clicked = page.evaluate(
                "(() => { const c = document.querySelectorAll('.space-y-2 > div'); "
                "if (c.length > 0) { c[0].click(); return true; } return false; })()"
            )
            if clicked:
                page.wait_for_timeout(2000)
                wait_for_content(page, timeout=5000)
        except Exception as e:
            print(f"  (session click: {e})")

        capture(page, "session-inspector-transcript.png")

        # --- Screenshot 3: Feature Board ---
        print("\n[3/6] Feature Board Kanban...")
        goto(page, f"{BASE_URL}/#/board", extra_wait=2500)
        wait_for_content(page, timeout=8000)
        page.wait_for_timeout(1000)

        # Ensure kanban view via title attribute button
        js_click(page, 'button[title="Kanban View"]')
        page.wait_for_timeout(500)

        # Click first draggable feature card
        try:
            clicked = page.evaluate(
                "(() => { const c = document.querySelectorAll('div[draggable=\"true\"]'); "
                "if (c.length > 0) { c[0].click(); return true; } return false; })()"
            )
            if clicked:
                page.wait_for_timeout(1500)
                wait_for_content(page, timeout=5000)
                js_click_contains(page, "button", "Phases")
                page.wait_for_timeout(800)
        except Exception as e:
            print(f"  (feature card: {e})")

        capture(page, "feature-board-kanban.png")

        # --- Screenshot 4: Execution Workbench ---
        print("\n[4/6] Execution Workbench...")
        goto(page, f"{BASE_URL}/#/execution", extra_wait=3500)
        wait_for_content(page, timeout=12000)
        page.wait_for_timeout(2000)

        # Try clicking first feature-like element
        try:
            page.evaluate(
                "(() => { const els = document.querySelectorAll('[class*=\"cursor-pointer\"]'); "
                "for (const el of els) { const t = (el.innerText || '').trim(); "
                "if (t.length > 5 && !/Loading|Select|Search|Filter|Refresh|Board|Plans|Sessions|Analytics/i.test(t)) "
                "{ el.click(); return; } } })()"
            )
            page.wait_for_timeout(3500)
            wait_for_content(page, timeout=10000)
        except Exception as e:
            print(f"  (feature picker: {e})")

        capture(page, "execution-workbench.png")

        # --- Screenshot 5: Workflow Registry ---
        print("\n[5/6] Workflow Registry...")
        goto(page, f"{BASE_URL}/#/workflows", extra_wait=3000)
        wait_for_content(page, timeout=10000)
        page.wait_for_timeout(2000)

        # Click first workflow item
        try:
            page.evaluate(
                "(() => { const els = document.querySelectorAll('[class*=\"cursor-pointer\"]'); "
                "for (const el of els) { const t = (el.innerText || '').trim(); "
                "if (t.length > 3 && !/Refresh|Search|Filter|All|Resolved|Hybrid|Weak|Unresolved/i.test(t)) "
                "{ el.click(); return; } } })()"
            )
            page.wait_for_timeout(1500)
            wait_for_content(page, timeout=5000)
        except Exception as e:
            print(f"  (workflow click: {e})")

        capture(page, "workflow-registry.png")

        # --- Screenshot 6: Analytics - Workflow Intelligence ---
        print("\n[6/6] Analytics - Workflow Intelligence...")
        goto(page, f"{BASE_URL}/#/analytics?tab=workflow_intelligence", extra_wait=3500)
        wait_for_content(page, timeout=12000)
        page.wait_for_timeout(2500)

        # Ensure Workflow Intel tab active
        js_click_contains(page, "button", "Workflow Intel")
        page.wait_for_timeout(2000)
        wait_for_content(page, timeout=8000)

        capture(page, "analytics-workflow-intelligence.png")

        browser.close()
        print("\n✓ All 6 screenshots captured.")


if __name__ == "__main__":
    main()
