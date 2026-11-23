import asyncio
from dataclasses import dataclass

import pytest

from src.crawler.crawl.actions import (
  LocatorStrategy,
  get_action_candidates,
)
from src.crawler.crawl.actions.execution import perform_action
from src.crawler.state.hashing import rendered_dom_identity_hash_for_page


@dataclass
class FakeElement:
  tag_name: str
  text: str = ""
  href: str = ""
  input_type: str = ""
  name: str = ""
  role: str = ""
  inferred_role: str = ""
  aria_expanded: str = ""
  aria_current: str = ""
  aria_label: str = ""
  label_text: str = ""
  data_testid: str = ""
  selector: str = ""
  checked: bool = False
  radio_label_selector: str = ""
  is_form_submit: bool = False
  inside_form: bool = False
  form_is_safe_to_submit: bool = False
  destructive_text: bool = False
  element_id: str = ""
  dom_path: str = ""
  in_header: bool = False
  in_nav: bool = False
  in_main: bool = False
  in_footer: bool = False
  ancestor_roles: tuple[str, ...] = ()
  ancestor_tags: tuple[str, ...] = ()
  visible: bool = True
  enabled: bool = True


class FakeLocator:
  def __init__(self, el: FakeElement):
    self.el = el

  async def is_visible(self) -> bool:
    return self.el.visible

  async def is_enabled(self) -> bool:
    return self.el.enabled

  async def evaluate(self, script: str):
    if "join('|')" in script:
      return "|".join(
        [
          self.el.tag_name.lower(),
          self.el.element_id,
          self.el.role,
          self.el.href,
          self.el.input_type.lower(),
          self.el.name,
          self.el.text[:120],
          self.el.dom_path,
        ]
      )
    if "text: (el.innerText" in script:
      return {
        "text": self.el.text,
        "href": self.el.href,
        "tag_name": self.el.tag_name.lower(),
        "input_type": self.el.input_type.lower(),
        "role": self.el.role,
        "inferred_role": self.el.inferred_role,
        "aria_label": self.el.aria_label,
        "label_text": self.el.label_text,
        "data_testid": self.el.data_testid,
        "aria_expanded": self.el.aria_expanded,
        "aria_current": self.el.aria_current,
        "selector": self.el.selector,
        "checked": self.el.checked,
        "radio_label_selector": self.el.radio_label_selector,
        "is_form_submit": self.el.is_form_submit,
        "inside_form": self.el.inside_form,
        "form_is_safe_to_submit": self.el.form_is_safe_to_submit,
        "destructive_text": self.el.destructive_text,
        "in_header": self.el.in_header,
        "in_nav": self.el.in_nav,
        "in_main": self.el.in_main,
        "in_footer": self.el.in_footer,
        "ancestor_roles": list(self.el.ancestor_roles),
        "ancestor_tags": list(self.el.ancestor_tags),
      }
    if "(el.getAttribute('type') || 'text').toLowerCase()" in script:
      return (self.el.input_type or "text").lower()
    raise AssertionError(f"Unexpected evaluate script: {script}")


class FakeLocatorGroup:
  def __init__(self, locators: list[FakeLocator]):
    self._locators = locators

  async def count(self) -> int:
    return len(self._locators)

  def nth(self, idx: int) -> FakeLocator:
    return self._locators[idx]


class FakePage:
  def __init__(self, mapping: dict[str, list[FakeLocator]]):
    self._mapping = mapping

  def locator(self, selector: str) -> FakeLocatorGroup:
    return FakeLocatorGroup(self._mapping.get(selector, []))


async def _with_chromium(callback):
  playwright = pytest.importorskip("playwright.async_api")
  try:
    manager = await playwright.async_playwright().start()
  except Exception as exc:
    pytest.skip(f"Playwright could not start in this environment: {exc}")
  browser = None
  try:
    try:
      browser = await manager.chromium.launch(headless=True)
    except Exception as exc:
      pytest.skip(f"Playwright Chromium is unavailable: {exc}")
    return await callback(browser)
  finally:
    if browser is not None:
      await browser.close()
    await manager.stop()


def test_get_action_candidates_uses_safe_default_actions():
  link = FakeLocator(FakeElement(tag_name="a", text="Learn more", href="/docs", inferred_role="link", element_id="link_1"))
  button = FakeLocator(FakeElement(tag_name="button", text="Save", role="button", inferred_role="button", element_id="btn_1"))
  summary = FakeLocator(FakeElement(tag_name="summary", text="More details", inferred_role="button", element_id="sum_1"))
  role_tab = FakeLocator(FakeElement(tag_name="button", text="Preview", role="tab", inferred_role="button", element_id="tab_1"))
  text_input = FakeLocator(FakeElement(tag_name="input", input_type="text", element_id="input_1"))
  checkbox = FakeLocator(FakeElement(tag_name="input", input_type="checkbox", element_id="chk_1"))
  hidden_input = FakeLocator(FakeElement(tag_name="input", input_type="hidden", element_id="hidden_1"))
  select = FakeLocator(FakeElement(tag_name="select", inferred_role="combobox", element_id="sel_1"))
  unsafe_submit = FakeLocator(
    FakeElement(
      tag_name="input",
      input_type="submit",
      text="Delete account",
      element_id="submit_1",
      is_form_submit=True,
      inside_form=True,
      form_is_safe_to_submit=False,
      destructive_text=True,
    )
  )

  page = FakePage(
    {
      "a[href]": [link],
      "button": [button],
      "summary": [summary],
      "[role='button']": [button],  # duplicate on purpose
      "[role='tab']": [role_tab],
      "[aria-expanded][aria-controls]": [],
      "select": [select],
      "input:not([type='hidden'])": [text_input, checkbox, hidden_input],
      "input[type='button'], input[type='submit']": [unsafe_submit],
    }
  )

  candidates = asyncio.run(get_action_candidates(page, limit=20))
  action_types = [c.action_type for c in candidates]
  texts = {c.text for c in candidates}

  assert action_types.count("click") == 4  # button + summary + tab + link
  assert "type" not in action_types
  assert "select" in action_types
  assert "check" not in action_types
  assert {"More details", "Preview"} <= texts
  assert "Delete account" not in texts

  # Ensure duplicate button from role strategy is deduped by fingerprint.
  button_like = [c for c in candidates if c.text == "Save"]
  assert len(button_like) == 1
  assert button_like[0].identity
  assert button_like[0].inferred_role == "button"
  assert next(c for c in candidates if c.text == "Learn more").inferred_role == "link"
  assert next(c for c in candidates if c.action_type == "select").inferred_role == "combobox"

  # Hidden input should never survive filtering.
  assert all(c.input_type != "hidden" for c in candidates)


def test_get_action_candidates_keeps_same_text_controls_with_distinct_dom_paths():
  first = FakeLocator(
    FakeElement(
      tag_name="button",
      text="Read more",
      dom_path="main:nth-of-type(1)>section:nth-of-type(1)>button:nth-of-type(1)",
    )
  )
  second = FakeLocator(
    FakeElement(
      tag_name="button",
      text="Read more",
      dom_path="main:nth-of-type(1)>section:nth-of-type(2)>button:nth-of-type(1)",
    )
  )

  page = FakePage(
    {
      "a[href]": [],
      "button": [first, second],
      "[role='button']": [],
      "summary": [],
      "[role='tab']": [],
      "[aria-expanded][aria-controls]": [],
      "select": [],
      "input:not([type='hidden'])": [],
      "input[type='button'], input[type='submit']": [],
    }
  )

  candidates = asyncio.run(get_action_candidates(page, limit=20))

  assert len(candidates) == 2
  assert candidates[0].text == "Read more"
  assert candidates[1].text == "Read more"
  assert candidates[0].identity != candidates[1].identity


def test_get_action_candidates_extracts_landmark_and_ancestor_context():
  current_nav = FakeLocator(
    FakeElement(
      tag_name="a",
      text="Docs",
      href="/docs",
      aria_current="page",
      in_header=True,
      in_nav=True,
      ancestor_roles=("navigation", "banner"),
      ancestor_tags=("nav", "header"),
    )
  )
  demo_button = FakeLocator(
    FakeElement(
      tag_name="button",
      text="Open demo",
      in_main=True,
      ancestor_tags=("section", "main"),
    )
  )

  page = FakePage(
    {
      "a[href]": [current_nav],
      "button": [demo_button],
      "[role='button']": [],
      "summary": [],
      "[role='tab']": [],
      "[aria-expanded][aria-controls]": [],
      "select": [],
      "input:not([type='hidden'])": [],
      "input[type='button'], input[type='submit']": [],
    }
  )

  candidates = asyncio.run(get_action_candidates(page, limit=20))
  nav_candidate = next(candidate for candidate in candidates if candidate.text == "Docs")
  demo_candidate = next(candidate for candidate in candidates if candidate.text == "Open demo")

  assert nav_candidate.aria_current == "page"
  assert nav_candidate.in_header is True
  assert nav_candidate.in_nav is True
  assert nav_candidate.in_main is False
  assert nav_candidate.ancestor_roles == ("navigation", "banner")
  assert nav_candidate.ancestor_tags == ("nav", "header")

  assert demo_candidate.in_main is True
  assert demo_candidate.in_nav is False
  assert demo_candidate.ancestor_tags == ("section", "main")



def test_get_action_candidates_respects_custom_strategy_order_and_limit():
  first = FakeLocator(FakeElement(tag_name="button", text="First", element_id="btn_1"))
  second = FakeLocator(FakeElement(tag_name="select", element_id="sel_1"))
  third = FakeLocator(FakeElement(tag_name="a", href="/x", element_id="a_1"))
  page = FakePage(
    {
      "button": [first],
      "select": [second],
      "a[href]": [third],
    }
  )

  strategies = [
    LocatorStrategy(name="buttons", selector="button"),
    LocatorStrategy(name="selects", selector="select"),
    LocatorStrategy(name="links", selector="a[href]"),
  ]
  candidates = asyncio.run(get_action_candidates(page, limit=2, strategies=strategies))

  assert len(candidates) == 2
  assert candidates[0].strategy_name == "buttons"
  assert candidates[1].strategy_name == "selects"


def test_get_action_candidates_balances_strategy_coverage_within_limit():
  links = [
    FakeLocator(FakeElement(tag_name="a", text=f"Link {idx}", href=f"/docs/{idx}", element_id=f"link_{idx}"))
    for idx in range(5)
  ]
  button = FakeLocator(FakeElement(tag_name="button", text="Open demo", element_id="btn_1"))

  page = FakePage(
    {
      "a[href]": links,
      "button": [button],
      "[role='button']": [],
      "summary": [],
      "[role='tab']": [],
      "[aria-expanded][aria-controls]": [],
      "select": [],
      "input:not([type='hidden'])": [],
      "input[type='button'], input[type='submit']": [],
    }
  )

  candidates = asyncio.run(get_action_candidates(page, limit=3))

  assert len(candidates) == 3
  assert candidates[0].strategy_name == "buttons"


def test_get_action_candidates_keeps_deeper_route_links_when_link_bucket_is_widened():
  links = [
    FakeLocator(FakeElement(tag_name="a", text=text, href=href, element_id=f"link_{idx}"))
    for idx, (text, href) in enumerate(
      [
        ("Skip to content", "#main-content"),
        ("Survey", "https://tally.so/example"),
        ("Home", "/"),
        ("Pricing", "/pricing"),
        ("About", "/about"),
        ("Get started", "/material-ui/getting-started/"),
      ],
      start=1,
    )
  ]
  button = FakeLocator(FakeElement(tag_name="button", text="Open demo", element_id="btn_1"))

  page = FakePage(
    {
      "a[href]": links,
      "button": [button],
      "[role='button']": [],
      "summary": [],
      "[role='tab']": [],
      "[aria-expanded][aria-controls]": [],
      "select": [],
      "input:not([type='hidden'])": [],
      "input[type='button'], input[type='submit']": [],
    }
  )

  candidates = asyncio.run(get_action_candidates(page, limit=10))

  assert any(candidate.text == "Get started" for candidate in candidates)


def test_get_action_candidates_discovers_only_enabled_unselected_native_radios():
  first = FakeLocator(
    FakeElement(
      tag_name="input",
      input_type="radio",
      name="plan",
      text="consultation",
      label_text="Web accessibility consultation",
      element_id="radio_1",
      selector="input#consultation",
      dom_path="main>fieldset>input:nth-of-type(1)",
      in_main=True,
    )
  )
  second = FakeLocator(
    FakeElement(
      tag_name="input",
      input_type="radio",
      name="plan",
      text="audit",
      label_text="Accessibility audit",
      element_id="radio_2",
      selector="input#audit",
      dom_path="main>fieldset>input:nth-of-type(2)",
      in_main=True,
    )
  )
  selected = FakeLocator(
    FakeElement(
      tag_name="input",
      input_type="radio",
      name="plan",
      text="training",
      label_text="Training",
      element_id="radio_3",
      checked=True,
    )
  )
  disabled = FakeLocator(
    FakeElement(
      tag_name="input",
      input_type="radio",
      name="plan",
      text="support",
      label_text="Support",
      element_id="radio_4",
      enabled=False,
    )
  )
  checkbox = FakeLocator(FakeElement(tag_name="input", input_type="checkbox", element_id="chk_1"))

  page = FakePage(
    {
      "a[href]": [],
      "button": [],
      "[role='button']": [],
      "summary": [],
      "[role='tab']": [],
      "[aria-expanded][aria-controls]": [],
      "select": [],
      "input[type='radio']": [first, second, selected, disabled],
      "input:not([type='hidden'])": [checkbox],
      "input[type='button'], input[type='submit']": [],
    }
  )

  candidates = asyncio.run(get_action_candidates(page, limit=20))

  assert [candidate.text for candidate in candidates] == [
    "select radio: Web accessibility consultation",
    "select radio: Accessibility audit",
  ]
  assert all(candidate.action_type == "radio" for candidate in candidates)
  assert candidates[0].identity != candidates[1].identity
  assert [candidate.strategy_name for candidate in candidates] == ["radios", "radios"]
  assert all(candidate.input_type == "radio" for candidate in candidates)


def test_native_radio_activation_selects_visible_option_and_does_not_submit():
  async def run_check(browser):
    page = await browser.new_page(viewport={"width": 800, "height": 600})
    await page.set_content(
      """
      <main>
        <form id="choice-form">
          <fieldset>
            <legend>plan</legend>
            <label for="consultation">Web accessibility consultation</label>
            <input id="consultation" name="plan" type="radio" value="consultation">
          </fieldset>
          <button id="continue" type="button" disabled>Continue</button>
        </form>
        <script>
          window.submitCount = 0;
          window.continueClicks = 0;
          document.querySelector("#choice-form").addEventListener("submit", (event) => {
            event.preventDefault();
            window.submitCount += 1;
          });
          document.querySelector("#continue").addEventListener("click", () => {
            window.continueClicks += 1;
          });
          document.querySelector("#consultation").addEventListener("change", () => {
            document.querySelector("#continue").disabled = false;
          });
        </script>
      </main>
      """,
      wait_until="domcontentloaded",
    )
    candidates = await get_action_candidates(page, limit=20)
    radio = next(candidate for candidate in candidates if candidate.action_type == "radio")

    assert radio.text == "select radio: Web accessibility consultation"
    assert await perform_action(radio) is True
    assert await page.locator("#consultation").is_checked()
    assert await page.locator("#continue").is_enabled()
    assert await page.evaluate("window.submitCount") == 0
    assert await page.evaluate("window.continueClicks") == 0

  asyncio.run(_with_chromium(run_check))


def test_native_radio_activation_uses_visible_explicit_label_for_hidden_input():
  async def run_check(browser):
    page = await browser.new_page(viewport={"width": 800, "height": 600})
    await page.set_content(
      """
      <main>
        <label for="remote">Remote consultation</label>
        <input id="remote" name="mode" type="radio" value="remote" style="display: none">
      </main>
      """,
      wait_until="domcontentloaded",
    )
    candidates = await get_action_candidates(page, limit=20)

    radio = next(candidate for candidate in candidates if candidate.action_type == "radio")
    assert radio.text == "select radio: Remote consultation"
    assert await perform_action(radio) is True
    assert await page.locator("#remote").is_checked()

  asyncio.run(_with_chromium(run_check))


def test_native_radio_activation_uses_visible_wrapping_label():
  async def run_check(browser):
    page = await browser.new_page(viewport={"width": 800, "height": 600})
    await page.set_content(
      """
      <main>
        <label>
          <span>Office visit</span>
          <input id="office" name="mode" type="radio" value="office" style="display: none">
        </label>
      </main>
      """,
      wait_until="domcontentloaded",
    )
    candidates = await get_action_candidates(page, limit=20)

    radio = next(candidate for candidate in candidates if candidate.action_type == "radio")
    assert radio.text == "select radio: Office visit"
    assert await perform_action(radio) is True
    assert await page.locator("#office").is_checked()

  asyncio.run(_with_chromium(run_check))


def test_hidden_radio_without_visible_label_is_excluded():
  async def run_check(browser):
    page = await browser.new_page(viewport={"width": 800, "height": 600})
    await page.set_content(
      """
      <main>
        <input id="hidden" name="mode" type="radio" value="hidden" style="display: none">
      </main>
      """,
      wait_until="domcontentloaded",
    )

    candidates = await get_action_candidates(page, limit=20)

    assert [candidate for candidate in candidates if candidate.action_type == "radio"] == []

  asyncio.run(_with_chromium(run_check))


def test_radio_selection_changes_rendered_state_without_url_change():
  async def run_check(browser):
    page = await browser.new_page(viewport={"width": 800, "height": 600})
    await page.set_content(
      """
      <main>
        <label for="audit">Audit</label>
        <input id="audit" name="plan" type="radio" value="audit">
        <p id="summary">No plan selected</p>
        <script>
          document.querySelector("#audit").addEventListener("change", () => {
            document.querySelector("#summary").textContent = "Selected Audit";
          });
        </script>
      </main>
      """,
      wait_until="domcontentloaded",
    )
    start_url = page.url
    before_hash = await rendered_dom_identity_hash_for_page(page)
    radio = next(candidate for candidate in await get_action_candidates(page, limit=20) if candidate.action_type == "radio")

    assert await perform_action(radio) is True

    assert page.url == start_url
    assert await rendered_dom_identity_hash_for_page(page) != before_hash

  asyncio.run(_with_chromium(run_check))
