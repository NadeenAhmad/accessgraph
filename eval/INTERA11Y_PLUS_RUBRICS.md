# InterA11y+ rubrics for review (addition to InterA11y 8dcf06e for AccessGraph's evaluation)

Written in InterA11y's own rubric format, modelled on its 2.4.4 and 1.1.1 rubrics, from WCAG 2.2 Understanding documents and ACT rules only; no mention of history or transitions. Below is exactly what InterA11y's judge receives (its renderer strips ACT ids). Source files: runtime/intera11y/rubrics/2.4.2.js and 2.4.6.js; criterion modules src/criteria/2.4.2.js, 2.4.6.js (patch: eval/patches/intera11y-8dcf06e-w4a-rubrics.patch).

Candidates: 2.4.2 = the page (empty title fails without the model); 2.4.6 = every exposed heading, form field and button with a non-empty name (no name: not applicable, a 1.3.1/4.1.2 matter). Landmark and widget names are not covered.

Tested on 3 dev cases (page title co-sem-058, heading bs-sem-118, button bs-sem-112): all three seeded violations found, on the right element, about $0.001 per case.

## 2.4.2

```text
Analyze compliance with WCAG SC 2.4.2 (Page Titled).
A web page passes if it has a title that describes its topic or purpose.
Test rules:
1. The page must have a non-empty title.
2. The page title must describe the topic or purpose of the page.
   Tools: capture_full_page
   Rubric: A title fails when it does not identify the topic or purpose of the page as the page presents it (F25): a title that names a different page, step, item or topic than the content shows, or a placeholder or generic title ("Untitled", "Page", "New document") on a page with its own topic. A title passes when it identifies what the page is about, even when it is short or also names the site (G88). Judge the title against the page's main heading and its content; do not require it to repeat the heading. Evidence: the title, the page's headings and its visible text.
```

## 2.4.6

```text
Analyze compliance with WCAG SC 2.4.6 (Headings and Labels).
Headings and labels that are present must describe their topic or purpose. 2.4.6 does not require headings or labels to exist, and does not require them to be long.
Test rules:
1. Headings must describe the topic or purpose of the content they introduce.
   Tools: capture_full_page
   Rubric: A heading fails when its accessible name does not describe the topic or purpose of the content it introduces, that is the content after it up to the next heading of the same or a higher level (G130): a heading that names a different topic, step or item than that content, or a generic text ("Section", "Heading", "Content") where the content has its own topic. A heading passes when it identifies that topic, even briefly. Evidence: the heading's level and name, and the content under it.
2. Labels of form fields must describe the purpose of the field.
   Tools: query_ax_node
   Rubric: A form field's label fails when it does not describe what the field is for (G131): it names other information than the field collects, as its input type, autocomplete purpose, format, placeholder or the surrounding form and group show, or it is generic ("Field 1", "Input") where the purpose is specific. A label passes when it identifies the information asked for, even briefly. Evidence: the computed name and its source, the input type, autocomplete, placeholder, the nearest heading and the text around the field.
3. Button names must describe what the button does.
   Tools: interact_and_observe, observe_state_after_activation
   Rubric: A button's label fails when it does not describe the button's purpose (G131): it names a different action or object than the button acts on in its context, or it is generic ("Click", "Button", "Go") where the context does not make the action clear. A button passes when its name, read in its context (its form, group or the nearest heading), identifies its action. Evidence: the computed name and its source, the visible text, the element it controls and its state, the nearest heading and the text around it; interact_and_observe and observe_state_after_activation show what activating it does.
```

