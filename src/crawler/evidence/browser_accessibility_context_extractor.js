// Neutral browser-side semantic/accessibility evidence extraction only.
async ({ stateId, stateContext, screenshotPath, limits, schemaVersion }) => {
  const maxTextLength = limits.max_text_length;
  const textOf = (value, max = maxTextLength) => {
    const normalized = String(value || '').replace(/\s+/g, ' ').trim();
    return normalized.slice(0, max);
  };
  const maybeText = (value, max = maxTextLength) => {
    const normalized = textOf(value, max);
    return normalized || null;
  };
  const attr = (el, name) => el.getAttribute(name);
  const attrText = (el, name) => maybeText(attr(el, name));
  const roleOf = (el) => attr(el, 'role') || '';
  const tagOf = (el) => (el.tagName || '').toLowerCase();
  const cssEscape = (value) => {
    if (window.CSS && CSS.escape) return CSS.escape(String(value));
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  };
  const stableHash = (value) => {
    let hash = 2166136261;
    const input = String(value || '');
    for (let index = 0; index < input.length; index += 1) {
      hash ^= input.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, '0');
  };
  const isHiddenByStyle = (el) => {
    const style = window.getComputedStyle(el);
    return style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0;
  };
  const isVisible = (el) => {
    const rect = el.getBoundingClientRect();
    return !!(rect.width || rect.height)
      && !el.hidden
      && attr(el, 'aria-hidden') !== 'true'
      && !isHiddenByStyle(el);
  };
  const boundingBox = (el) => {
    const rect = el.getBoundingClientRect();
    return {
      x: Number(rect.x.toFixed(2)),
      y: Number(rect.y.toFixed(2)),
      width: Number(rect.width.toFixed(2)),
      height: Number(rect.height.toFixed(2))
    };
  };
  const computedStyle = (el) => {
    const style = window.getComputedStyle(el);
    return {
      display: style.display || '',
      visibility: style.visibility || '',
      color: style.color || '',
      background_color: style.backgroundColor || '',
      font_size: style.fontSize || '',
      font_weight: style.fontWeight || ''
    };
  };
  // W4A phase 1: open shadow roots and same-origin iframes are part of the page the user perceives. Their elements
  // get paths "<host path>>><path inside>" (the notation InterA11y uses), resolvable with resolveScopedPath().
  const rootPrefix = new Map();
  const xpathOf = (el) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
    const root = el.getRootNode ? el.getRootNode() : document;
    return (rootPrefix.get(root) || '') + localXpathOf(el);
  };
  const localXpathOf = (el) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE) {
      const tag = tagOf(current);
      let index = 1;
      let previous = current.previousElementSibling;
      while (previous) {
        if (tagOf(previous) === tag) index += 1;
        previous = previous.previousElementSibling;
      }
      parts.unshift(`${tag}[${index}]`);
      current = current.parentElement;
    }
    return `/${parts.join('/')}`;
  };
  const selectorOf = (el) => {
    const tag = tagOf(el);
    if (el.id) return `${tag}#${cssEscape(el.id)}`;
    const role = roleOf(el);
    const name = attr(el, 'name');
    if (role) return `${tag}[role="${role.replace(/"/g, '\\"')}"]`;
    if (name) return `${tag}[name="${String(name).replace(/"/g, '\\"')}"]`;
    const parent = el.parentElement;
    if (!parent) return tag;
    const sameTag = Array.from(parent.children).filter((child) => tagOf(child) === tag);
    const index = sameTag.indexOf(el);
    return index >= 0 ? `${tag}:nth-of-type(${index + 1})` : tag;
  };
  const elementsFromIds = (rawIds) => String(rawIds || '')
    .split(/\s+/)
    .filter(Boolean)
    .map((id) => document.getElementById(id))
    .filter(Boolean);
  const inputTypeOf = (el) => String(attr(el, 'type') || '').toLowerCase();
  const buttonLikeInputTypes = new Set(['button', 'submit', 'reset', 'image']);
  const isValueBearingFormControl = (el) => {
    const tag = tagOf(el);
    if (tag === 'textarea' || tag === 'select') return true;
    if (tag === 'input') return !buttonLikeInputTypes.has(inputTypeOf(el));
    return roleOf(el) === 'textbox' || roleOf(el) === 'combobox';
  };
  const scrubValueBearingFields = (root) => {
    const scrub = (node) => {
      if (!node || node.nodeType !== Node.ELEMENT_NODE) return;
      const nodeTag = tagOf(node);
      if (nodeTag === 'input') {
        node.removeAttribute('value');
      } else if (nodeTag === 'textarea') {
        node.removeAttribute('value');
        node.textContent = '';
      } else if (nodeTag === 'option') {
        node.removeAttribute('value');
      }
    };
    scrub(root);
    for (const node of Array.from(root.querySelectorAll('input, textarea, option'))) {
      scrub(node);
    }
  };
  const safeRawHtml = (el) => {
    const clone = el.cloneNode(true);
    scrubValueBearingFields(clone);
    return textOf(clone.outerHTML || '');
  };
  const safeNodeText = (el) => {
    const clone = el.cloneNode(true);
    scrubValueBearingFields(clone);
    return textOf(clone.innerText || clone.textContent || '');
  };
  const labelTextSegments = (label) => {
    const segments = [];
    for (const node of Array.from(label.childNodes)) {
      let segment = '';
      if (node.nodeType === Node.TEXT_NODE) {
        segment = textOf(node.textContent || '');
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        segment = safeNodeText(node);
      }
      if (segment) segments.push(segment);
    }
    return segments;
  };
  const visibleContextText = (el) => {
    if (!el) return '';
    const clone = el.cloneNode(true);
    const sourceNodes = Array.from(el.querySelectorAll('*'));
    const cloneNodes = Array.from(clone.querySelectorAll('*'));
    for (let index = sourceNodes.length - 1; index >= 0; index -= 1) {
      const sourceNode = sourceNodes[index];
      const cloneNode = cloneNodes[index];
      if (
        ['script', 'style', 'noscript'].includes(tagOf(sourceNode))
        || sourceNode.hidden
        || attr(sourceNode, 'aria-hidden') === 'true'
        || isHiddenByStyle(sourceNode)
      ) {
        cloneNode.remove();
      }
    }
    scrubValueBearingFields(clone);
    return textOf(clone.innerText || clone.textContent || '');
  };
  const labelledByText = (el) => elementsFromIds(attr(el, 'aria-labelledby'))
    .map((node) => safeNodeText(node))
    .filter(Boolean)
    .join(' ');
  const describedByText = (el) => elementsFromIds(attr(el, 'aria-describedby'))
    .map((node) => safeNodeText(node))
    .filter(Boolean)
    .join(' ');
  const explicitLabelsFor = (el) => {
    const id = attr(el, 'id');
    return id ? Array.from(document.querySelectorAll(`label[for="${cssEscape(id)}"]`)) : [];
  };
  const explicitLabelText = (el) => {
    return explicitLabelsFor(el)
      .map((label) => safeNodeText(label))
      .filter(Boolean)
      .join(' ');
  };
  const wrappingLabelFor = (el) => el.closest('label');
  const wrappingLabelText = (el) => {
    const label = wrappingLabelFor(el);
    return label ? safeNodeText(label) : '';
  };
  const ownText = (el, options = {}) => {
    if (!options.includeControlValue && isValueBearingFormControl(el)) {
      return textOf(attr(el, 'alt') || attr(el, 'title') || '');
    }
    return textOf(el.innerText || el.textContent || el.value || attr(el, 'alt') || '');
  };
  const approximateAccessibleName = (el, options = {}) => {
    return textOf(
      attr(el, 'aria-label')
      || labelledByText(el)
      || explicitLabelText(el)
      || wrappingLabelText(el)
      || attr(el, 'alt')
      || attr(el, 'title')
      || ownText(el, options)
    );
  };
  const elementIdFor = (el, kind = '') => {
    const seed = [
      stateId,
      xpathOf(el),
      tagOf(el),
      roleOf(el),
      approximateAccessibleName(el) || ownText(el)
    ].join('|');
    return `e_${stableHash(seed)}`;
  };
  const landmarkSelector = 'header, nav, main, aside, footer, section, form, search, [role="banner"], [role="navigation"], [role="main"], [role="complementary"], [role="contentinfo"], [role="region"], [role="form"], [role="search"]';
  const headingSelector = 'h1, h2, h3, h4, h5, h6';
  const headingScopeSchemaVersion = 'heading_scope_v1';
  const headingScopeStrategy = 'within_nearest_scope_root_until_next_same_or_higher_heading';
  const headingScopeItemLimit = 8;
  const headingScopeItemTextLength = 160;
  const headingScopeRootSelector = 'dialog, [role="dialog"], section, article, main, aside, nav, form, li';
  const headingScopeTraversalSelector = [
    headingSelector,
    'p',
    'li',
    'button',
    'input:not([type="hidden"])',
    'textarea',
    'select',
    '[role="button"]',
    'a[href]',
    '[role="link"]',
    'label',
    'legend',
    'figcaption',
    'blockquote',
    'article',
    '[role="article"]',
    'summary'
  ].join(',');
  const headingScopeCountKeys = {
    paragraph: 'paragraphs',
    list_item: 'list_items',
    button: 'buttons',
    link: 'links',
    form_control: 'form_controls',
    label: 'labels',
    legend: 'legends',
    figcaption: 'figcaptions',
    blockquote: 'blockquotes',
    card: 'cards',
    other_text_block: 'other_text_blocks'
  };
  const nearestLandmark = (el) => {
    const landmark = el.closest(landmarkSelector);
    if (!landmark || landmark === el) return {};
    return {
      element_id: elementIdFor(landmark, 'landmark'),
      tag: tagOf(landmark),
      role: roleOf(landmark),
      accessible_name: maybeText(approximateAccessibleName(landmark)),
      selector: selectorOf(landmark)
    };
  };
  const nearestHeading = (el) => {
    const nearest = nearestHeadingElement(el);
    if (!nearest || nearest === el) return {};
    return {
      element_id: elementIdFor(nearest, 'heading'),
      tag: tagOf(nearest),
      text: textOf(nearest.innerText || nearest.textContent),
      selector: selectorOf(nearest)
    };
  };
  const ancestorRoles = (el) => {
    const roles = [];
    let current = el.parentElement;
    while (current) {
      const role = roleOf(current);
      if (role) roles.push(role);
      current = current.parentElement;
    }
    return roles;
  };
  function nearestHeadingElement(el) {
    const headings = Array.from(document.querySelectorAll(headingSelector))
      .filter((heading) => isVisible(heading));
    let nearest = null;
    for (const heading of headings) {
      const position = heading.compareDocumentPosition(el);
      if (position & Node.DOCUMENT_POSITION_FOLLOWING) nearest = heading;
    }
    return nearest;
  }
  const sectionHeading = (el) => {
    const section = el.closest('section, article, main, aside, nav, header, footer, form');
    const heading = section ? section.querySelector(headingSelector) : null;
    if (heading) return textOf(heading.innerText || heading.textContent);
    const nearest = nearestHeading(el);
    return nearest && nearest.text ? nearest.text : '';
  };
  const nearbyText = (el) => [
    el.previousElementSibling && isVisible(el.previousElementSibling) ? visibleContextText(el.previousElementSibling) : '',
    el.nextElementSibling && isVisible(el.nextElementSibling) ? visibleContextText(el.nextElementSibling) : ''
  ].map((value) => textOf(value, 250)).filter(Boolean).join(' ');
  const headingLevelOf = (el) => Number((el.tagName || 'H0').slice(1)) || Number(attr(el, 'aria-level')) || (attr(el, 'role') === 'heading' ? 2 : null);
  const isHeadingElement = (el) => !!(el && el.matches && el.matches(headingSelector));
  const headingScopeCounts = () => ({
    paragraphs: 0,
    list_items: 0,
    buttons: 0,
    links: 0,
    form_controls: 0,
    labels: 0,
    legends: 0,
    figcaptions: 0,
    blockquotes: 0,
    cards: 0,
    other_text_blocks: 0,
    sampled_items: 0,
    omitted_items: 0
  });
  const isVisibleInHeadingScope = (el, root) => {
    if (!isVisible(el)) return false;
    let current = el.parentElement;
    while (current && current !== root.parentElement) {
      if (current.hidden || attr(current, 'aria-hidden') === 'true' || isHiddenByStyle(current)) {
        return false;
      }
      if (current === root) break;
      current = current.parentElement;
    }
    return true;
  };
  const headingScopeRootFor = (heading) => heading.closest(headingScopeRootSelector)
    || document.body
    || document.documentElement;
  const headingScopeKindFor = (el) => {
    const tag = tagOf(el);
    const role = roleOf(el);
    if (tag === 'p') return 'paragraph';
    if (tag === 'button' || role === 'button' || (tag === 'input' && buttonLikeInputTypes.has(inputTypeOf(el)))) return 'button';
    if (tag === 'a' || role === 'link') return 'link';
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || role === 'textbox' || role === 'combobox' || role === 'checkbox' || role === 'radio' || role === 'switch' || role === 'slider') return 'form_control';
    if (tag === 'label') return 'label';
    if (tag === 'legend') return 'legend';
    if (tag === 'figcaption') return 'figcaption';
    if (tag === 'blockquote') return 'blockquote';
    if (tag === 'li') return 'list_item';
    if ((tag === 'article' || role === 'article') && !el.querySelector('p, li, button, a[href], input, textarea, select, label, legend, figcaption, blockquote')) {
      return 'card';
    }
    if (tag === 'summary') return 'other_text_block';
    return null;
  };
  const headingScopeTextFor = (el, kind) => {
    if (kind === 'form_control') {
      return textOf(
        [
          approximateAccessibleName(el),
          attr(el, 'placeholder'),
          attr(el, 'type'),
          attr(el, 'autocomplete')
        ].filter(Boolean).join(' '),
        headingScopeItemTextLength
      );
    }
    return textOf(
      approximateAccessibleName(el, { includeControlValue: kind === 'button' })
      || visibleContextText(el),
      headingScopeItemTextLength
    );
  };
  const headingScopeItemFor = (el, kind) => {
    const text = headingScopeTextFor(el, kind);
    if (!text) return null;
    return {
      kind,
      element_id: elementIdFor(el, kind),
      tag: tagOf(el),
      role: roleOf(el) || null,
      selector: selectorOf(el),
      text
    };
  };
  const headingScopeFor = (heading) => {
    const root = headingScopeRootFor(heading);
    const currentLevel = headingLevelOf(heading);
    const counts = headingScopeCounts();
    const sampledItems = [];
    const excerptParts = [];
    let seenHeading = false;
    const elements = Array.from(root.querySelectorAll(headingScopeTraversalSelector));

    for (const el of elements) {
      if (el === heading) {
        seenHeading = true;
        continue;
      }
      if (!seenHeading || !isVisibleInHeadingScope(el, root)) {
        continue;
      }
      if (isHeadingElement(el)) {
        const nextLevel = headingLevelOf(el);
        if (currentLevel && nextLevel && nextLevel <= currentLevel) {
          break;
        }
        continue;
      }
      const kind = headingScopeKindFor(el);
      if (!kind) continue;
      const item = headingScopeItemFor(el, kind);
      if (!item) continue;
      const countKey = headingScopeCountKeys[kind];
      if (countKey) counts[countKey] += 1;
      if (sampledItems.length < headingScopeItemLimit) {
        sampledItems.push(item);
        excerptParts.push(item.text);
      } else {
        counts.omitted_items += 1;
      }
    }

    counts.sampled_items = sampledItems.length;
    const fullExcerpt = excerptParts.join(' ');
    const textExcerpt = textOf(fullExcerpt);
    return {
      schema_version: headingScopeSchemaVersion,
      strategy: headingScopeStrategy,
      text_excerpt: textExcerpt,
      truncated: counts.omitted_items > 0 || fullExcerpt.length > textExcerpt.length,
      content_counts: counts,
      sampled_items: sampledItems
    };
  };
  const formSummary = (form) => form ? {
    element_id: elementIdFor(form, 'form'),
    selector: selectorOf(form),
    accessible_name: maybeText(approximateAccessibleName(form))
  } : null;
  // W4A dev round 2: WCAG's "programmatically determined context" (2.4.4; ACT 5effbb): the enclosing sentence or
  // paragraph, list item, or table cell with its associated header cells, and text referenced by aria-describedby.
  // Text that is only nearby (a heading, another cell) is kept apart in `context.nearby_text`/`section_heading`.
  const tableHeadersFor = (cell) => {
    const byIds = elementsFromIds(attr(cell, 'headers')).map((node) => safeNodeText(node)).filter(Boolean);
    if (byIds.length) return byIds.slice(0, 4);
    const row = cell.parentElement;
    const table = cell.closest('table');
    if (!row || !table || !row.cells) return [];
    const columnOf = (r, target) => {
      let col = 0;
      for (const c of r.cells) { if (c === target) return col; col += c.colSpan || 1; }
      return -1;
    };
    const cellAt = (r, col) => {
      let start = 0;
      for (const c of r.cells) { const end = start + (c.colSpan || 1); if (col >= start && col < end) return c; start = end; }
      return null;
    };
    const out = [];
    const col = columnOf(row, cell);
    for (const r of Array.from(table.rows)) {
      if (r === row) break;
      const h = cellAt(r, col);
      if (h && h.tagName === 'TH' && (attr(h, 'scope') || 'col') !== 'row') out.push(safeNodeText(h));
    }
    for (const c of Array.from(row.cells)) {
      if (c !== cell && c.tagName === 'TH' && attr(c, 'scope') !== 'col') out.push(safeNodeText(c));
    }
    return out.filter(Boolean).slice(0, 4);
  };
  // W4A phase 3: a link in a nested list also takes its context from the parent list item under which the list is
  // nested (WCAG technique H81): that item's own visible text, without its nested lists.
  const listItemOwnText = (li) => {
    const parts = [];
    const walker = document.createTreeWalker(li, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const parent = node.parentElement;
      if (!parent) continue;
      const list = parent.closest('ul, ol, menu');
      if (list && list !== li && li.contains(list)) continue;
      if (!isVisible(parent)) continue;
      parts.push(node.nodeValue || '');
    }
    return textOf(parts.join(' ')).slice(0, 200);
  };
  const parentListItems = (item) => {
    const out = [];
    for (let li = item.parentElement ? item.parentElement.closest('li') : null; li && out.length < 3;
         li = li.parentElement ? li.parentElement.closest('li') : null) {
      const text = listItemOwnText(li);
      if (text) out.push(text);
    }
    return out;
  };
  const programmaticContext = (el) => {
    const container = el.parentElement ? el.parentElement.closest('p, li, td, th, dd, dt, caption, figcaption') : null;
    const kind = container ? tagOf(container) : null;
    const describedBy = describedByText(el);
    if (!container && !describedBy) return null;
    const parents = kind === 'li' ? parentListItems(container) : [];
    return {
      kind,
      text: container ? textOf(safeNodeText(container)).slice(0, 300) : '',
      table_headers: container && (kind === 'td' || kind === 'th') ? tableHeadersFor(container) : [],
      described_by: describedBy ? textOf(describedBy).slice(0, 200) : '',
      ...(parents.length ? { parent_list_items: parents } : {})
    };
  };
  const baseElement = (el, kind, options = {}) => {
    const parent = el.parentElement;
    const text = ownText(el, { includeControlValue: options.includeControlValue === true });
    return {
      element_id: elementIdFor(el, kind),
      kind,
      tag: tagOf(el),
      role: roleOf(el) || null,
      selector: selectorOf(el),
      xpath: xpathOf(el),
      text,
      accessible_name: maybeText(approximateAccessibleName(el, { includeControlValue: options.includeControlValue === true })),
      aria_label: attrText(el, 'aria-label'),
      aria_labelledby: attrText(el, 'aria-labelledby'),
      aria_describedby: attrText(el, 'aria-describedby'),
      title: attrText(el, 'title'),
      visible: isVisible(el),
      bounding_box: boundingBox(el),
      computed_style: computedStyle(el),
      structure: {
        parent_tag: parent ? tagOf(parent) : null,
        parent_role: parent ? (roleOf(parent) || null) : null,
        nearest_landmark: nearestLandmark(el),
        nearest_heading: nearestHeading(el),
        ancestor_roles: ancestorRoles(el),
        parent_form: el.closest('form') && el.closest('form') !== el ? formSummary(el.closest('form')) : null
      },
      context: {
        nearby_text: textOf(nearbyText(el)),
        parent_text: textOf(visibleContextText(parent)),
        section_heading: textOf(sectionHeading(el)),
        ...(programmaticContext(el) ? { programmatic_context: programmaticContext(el) } : {})
      },
      raw_html: safeRawHtml(el)
    };
  };

  const truncation = {};
  const capped = (category, items, limitKey) => {
    const limit = limits[limitKey];
    if (!Number.isFinite(limit) || items.length <= limit) return items;
    truncation[category] = {
      limit,
      original_count: items.length,
      omitted_count: items.length - limit
    };
    return items.slice(0, limit);
  };
  const referencedById = new Map();
  const relationshipByKey = new Map();
  const addReferenced = (el, referenceType) => {
    if (!el) return null;
    const item = {
      ...baseElement(el, 'referenced'),
      reference_type: referenceType
    };
    if (tagOf(el) === 'label') {
      const textSegments = labelTextSegments(el);
      if (textSegments.length) item.text_segments = textSegments;
    }
    referencedById.set(item.element_id, item);
    return item;
  };
  const addRelationship = (type, fromEl, toEl, method) => {
    if (!fromEl || !toEl) return;
    const fromId = elementIdFor(fromEl, fromEl.matches('label') ? 'referenced' : '');
    const toId = elementIdFor(toEl, '');
    const key = `${type}|${fromId}|${toId}|${method}`;
    relationshipByKey.set(key, {
      type,
      from_element_id: fromId,
      to_element_id: toId,
      method
    });
  };
  const registerStructuralRelationshipsFor = (el, options = {}) => {
    const form = el.closest('form');
    if (options.formContains && form && form !== el) {
      addRelationship('form_contains', form, el, 'descendant');
    }
    const landmark = el.closest(landmarkSelector);
    if (options.landmarkContains !== false && landmark && landmark !== el) {
      addRelationship('landmark_contains', landmark, el, 'nearest');
    }
    const heading = nearestHeadingElement(el);
    if (options.headingContext && heading && heading !== el) {
      addRelationship('heading_context', heading, el, 'nearest_preceding');
    }
  };
  const registerReferencesFor = (el) => {
    for (const ref of elementsFromIds(attr(el, 'aria-labelledby'))) {
      addReferenced(ref, 'aria-labelledby');
      addRelationship('labelledby', ref, el, 'aria-labelledby');
    }
    for (const ref of elementsFromIds(attr(el, 'aria-describedby'))) {
      addReferenced(ref, 'aria-describedby');
      addRelationship('describes', ref, el, 'aria-describedby');
    }
    const explicitLabels = explicitLabelsFor(el);
    for (const explicitLabel of explicitLabels) {
      addReferenced(explicitLabel, 'label[for]');
      addRelationship('labels', explicitLabel, el, 'for');
    }
    const wrappingLabel = wrappingLabelFor(el);
    if (wrappingLabel && !explicitLabels.includes(wrappingLabel)) {
      addReferenced(wrappingLabel, 'label-wrapper');
      addRelationship('labels', wrappingLabel, el, 'wrapper');
    }
    for (const ref of elementsFromIds(attr(el, 'aria-controls'))) {
      addReferenced(ref, 'aria-controls');
      addRelationship('controls', el, ref, 'aria-controls');
    }
    for (const ref of elementsFromIds(attr(el, 'aria-owns'))) {
      addReferenced(ref, 'aria-owns');
      addRelationship('owns', el, ref, 'aria-owns');
    }
  };
  const scopedRoots = (() => {
    const roots = [document];
    const queue = [document];
    while (queue.length && roots.length < 300) {
      const root = queue.shift();
      for (const el of root.querySelectorAll('*')) {
        let inner = null;
        if (el.shadowRoot) inner = el.shadowRoot;
        else if (el.tagName === 'IFRAME') { try { inner = el.contentDocument; } catch (e) { inner = null; } }
        if (!inner || rootPrefix.has(inner)) continue;
        rootPrefix.set(inner, xpathOf(el) + '>>');
        roots.push(inner);
        queue.push(inner);
        if (roots.length >= 300) break;
      }
    }
    return roots;
  })();
  const deepQueryAll = (selector) => scopedRoots.flatMap((root) => {
    try { return Array.from(root.querySelectorAll(selector)); } catch (e) { return []; }
  });
  const visibleMatches = (selector) => deepQueryAll(selector).filter((el) => isVisible(el));

  const imageElements = visibleMatches('img, [role="img"], input[type="image"]');  // W4A round 3: image buttons too
  const images = imageElements.map((el) => {
    registerStructuralRelationshipsFor(el, { headingContext: true });
    return {
      ...baseElement(el, 'image'),
      src: el.currentSrc || attr(el, 'src') || '',
      alt: attrText(el, 'alt')
    };
  });

  // W4A round 4 (WCAG 1.1.1, failures F3 and F38/F39 by analogy): images a sighted user sees but assistive technologies
  // do not get: inside aria-hidden, alt="", role none/presentation, svg/canvas without an image role or name, CSS
  // background images on elements without text. Only images of a meaningful size (>= 40 x 40 CSS px); the judge decides
  // whether they carry information.
  const renderedAtSize = (el) => {
    const rect = el.getBoundingClientRect();
    return rect.width >= 40 && rect.height >= 40 && !el.hidden && !isHiddenByStyle(el);
  };
  const hiddenImageReason = (el) => {
    const tag = el.tagName.toLowerCase();
    const role = (attr(el, 'role') || '').trim().toLowerCase();
    const named = !!((attr(el, 'aria-label') || '').trim() || (attr(el, 'aria-labelledby') || '').trim());
    if (el.closest('[aria-hidden="true"]')) return 'aria-hidden';
    if (role === 'none' || role === 'presentation') return `role-${role}`;
    if (tag === 'img' && el.hasAttribute('alt') && !(attr(el, 'alt') || '').trim() && !named && !(attr(el, 'title') || '').trim()) return 'empty-alt';
    // W4A round 5: a canvas has no role, so its aria-label is not exposed without an image role; an svg whose
    // content is exposed through named parts (role img or graphics-symbol with a name) is not hidden
    const imageRole = ['img', 'image', 'graphics-document', 'graphics-symbol'].includes(role);
    const namedParts = tag === 'svg' && el.querySelector('[role="img"][aria-label], [role="img"][aria-labelledby], [role="graphics-symbol"][aria-label], [role="graphics-symbol"][aria-labelledby]');
    if (tag === 'canvas' && !imageRole) return 'canvas-without-image-role';
    if (tag === 'svg' && role !== 'img' && !named && !el.querySelector('title') && !namedParts) return 'svg-without-image-role';
    return '';
  };
  const hiddenImagePairs = [];
  for (const el of deepQueryAll('img, svg, canvas, [role="img"]')) {
    if (hiddenImagePairs.length >= 20) break;
    if (el.parentElement && el.parentElement.closest('svg')) continue;
    if (!renderedAtSize(el)) continue;
    const reason = hiddenImageReason(el);
    if (reason) hiddenImagePairs.push([el, reason, '']);
  }
  let backgroundChecks = 0;
  for (const el of deepQueryAll('body *')) {
    if (hiddenImagePairs.length >= 20 || backgroundChecks >= 4000) break;
    if (['IMG', 'SVG', 'CANVAS', 'VIDEO', 'SCRIPT', 'STYLE', 'HTML', 'BODY'].includes(el.tagName.toUpperCase())) continue;
    backgroundChecks += 1;
    const image = window.getComputedStyle(el).backgroundImage || '';
    if (!/url\(/i.test(image)) continue;
    if ((el.innerText || '').trim() || (attr(el, 'aria-label') || '').trim() || (attr(el, 'role') || '') === 'img') continue;
    if (!renderedAtSize(el)) continue;
    hiddenImagePairs.push([el, 'css-background', image.slice(0, 300)]);
  }
  // W4A round 5: small CSS background icons (8 to 40 px) placed next to text can carry meaning on their own (a
  // required-field mark, a rating or spice-level icon); those outside links and buttons whose parent has text are
  // recorded too (at most 10); the judge decides whether they carry information
  let smallIcons = 0;
  for (const el of deepQueryAll('body *')) {
    if (smallIcons >= 10 || backgroundChecks >= 8000) break;
    if (['IMG', 'SVG', 'CANVAS', 'VIDEO', 'SCRIPT', 'STYLE', 'HTML', 'BODY'].includes(el.tagName.toUpperCase())) continue;
    backgroundChecks += 1;
    const image = window.getComputedStyle(el).backgroundImage || '';
    if (!/url\(/i.test(image)) continue;
    if ((el.innerText || '').trim() || (attr(el, 'aria-label') || '').trim() || (attr(el, 'role') || '') === 'img') continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8 || (rect.width >= 40 && rect.height >= 40) || el.hidden || isHiddenByStyle(el)) continue;
    if (el.closest('a[href], button, [role="button"], [role="link"]')) continue;
    if (!el.parentElement || !(el.parentElement.innerText || '').trim()) continue;
    hiddenImagePairs.push([el, 'css-background-icon', image.slice(0, 300)]);
    smallIcons += 1;
  }
  const hiddenImages = hiddenImagePairs.map(([el, reason, background]) => {
    registerStructuralRelationshipsFor(el, { headingContext: true });
    const control = el.closest('a[href], button, [role="button"], [role="link"], input[type="image"]');
    const controlName = control ? maybeText(approximateAccessibleName(control, {})) : null;
    return {
      ...baseElement(el, 'hidden_image'),
      src: el.currentSrc || attr(el, 'src') || attr(el, 'href') || background || '',
      alt: attrText(el, 'alt'),
      hidden_reason: reason,
      inside_control: !!control,
      control_name: controlName
    };
  });

  // W4A round 5 (WCAG 1.1.1, Understanding: characters used for their visual shape are non-text content): words
  // that mix Latin letters with look-alike Greek or Cyrillic letters (e.g. a Cyrillic 'Р' in 'РayРal'); assistive
  // technologies read the foreign letters, not the word sighted users see
  const lookalikeText = [];
  {
    const latin = /[A-Za-z]/;
    const foreign = /[\u0370-\u03FF\u0400-\u04FF]/;
    const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
    while (walker.nextNode() && lookalikeText.length < 10) {
      const value = walker.currentNode.nodeValue || '';
      if (!foreign.test(value) || !latin.test(value)) continue;
      const words = (value.match(/[\p{L}\p{M}]+/gu) || []).filter((w) => latin.test(w) && foreign.test(w));
      const host = walker.currentNode.parentElement;
      if (!words.length || !host || !isVisible(host)) continue;
      registerStructuralRelationshipsFor(host, { headingContext: true });
      lookalikeText.push({ ...baseElement(host, 'lookalike_text'), words: words.slice(0, 5) });
    }
  }

  // W4A round 5 (WCAG 2.4.4 with 4.1.2; ACT 'Link has non-empty accessible name'): a link hidden from assistive
  // technologies (aria-hidden) that keyboard users can still focus reaches screen-reader users without a name
  const hiddenFocusableLinks = deepQueryAll('a[href], [role="link"]').filter((el) => {
    if (!el.closest('[aria-hidden="true"]') || el.hidden || isHiddenByStyle(el) || el.closest('[inert]')) return false;
    const rect = el.getBoundingClientRect();
    return !!(rect.width || rect.height) && el.tabIndex >= 0;
  }).slice(0, 10).map((el) => {
    registerStructuralRelationshipsFor(el, { headingContext: true });
    return { ...baseElement(el, 'link'), href: attr(el, 'href') || '', hidden_from_assistive_technology: true,
             keyboard_focusable: true };
  });

  const nearbyTranscriptText = (el) => {
    const transcriptSiblings = [
      el.nextElementSibling,
      el.parentElement ? Array.from(el.parentElement.children).find((child) => child !== el && /transcript/i.test(`${attr(child, 'aria-label') || ''} ${child.innerText || child.textContent || ''}`)) : null
    ].filter(Boolean);
    const match = transcriptSiblings.find((node) => /transcript/i.test(`${attr(node, 'aria-label') || ''} ${node.innerText || node.textContent || ''}`));
    return match ? maybeText(match.innerText || match.textContent) : null;
  };

  const textTrackReadyState = (track) => {
    const states = ['none', 'loading', 'loaded', 'error'];
    return states[track.readyState] || 'unknown';
  };
  const loadTextTrackEvidence = async (trackElements) => {
    const originalModes = new Map();
    for (const trackElement of trackElements) {
      const textTrack = trackElement.track;
      if (!textTrack) continue;
      originalModes.set(trackElement, textTrack.mode || 'disabled');
      if (textTrack.mode === 'disabled') textTrack.mode = 'hidden';
    }

    try {
      const timeoutMs = Number.isFinite(limits.max_media_track_wait_ms)
        ? Math.max(0, limits.max_media_track_wait_ms)
        : 0;
      const deadline = performance.now() + timeoutMs;
      while (
        trackElements.some((track) => track.readyState === 0 || track.readyState === 1)
        && performance.now() < deadline
      ) {
        await new Promise((resolve) => window.setTimeout(resolve, 50));
      }

      const evidence = new Map();
      const cueLimit = Number.isFinite(limits.max_media_cues_per_track)
        ? Math.max(0, limits.max_media_cues_per_track)
        : 0;
      for (const trackElement of trackElements) {
        const textTrack = trackElement.track;
        const originalMode = originalModes.get(trackElement) || (textTrack ? textTrack.mode : 'disabled');
        const rawCues = textTrack && textTrack.cues ? Array.from(textTrack.cues) : [];
        const readyState = textTrackReadyState(trackElement);
        const cueStatus = readyState === 'loaded'
          ? 'loaded'
          : readyState === 'error'
            ? 'error'
            : timeoutMs > 0
              ? 'timeout'
              : 'unavailable';
        evidence.set(trackElement, {
          element_id: elementIdFor(trackElement, 'media_track'),
          selector: selectorOf(trackElement),
          xpath: xpathOf(trackElement),
          kind: attr(trackElement, 'kind') || '',
          src: attr(trackElement, 'src') || '',
          current_src: trackElement.src || '',
          srclang: attr(trackElement, 'srclang') || '',
          label: attr(trackElement, 'label') || '',
          default: !!trackElement.default,
          mode: originalMode,
          ready_state: readyState,
          cue_status: cueStatus,
          cue_count: rawCues.length,
          cues_truncated: rawCues.length > cueLimit,
          cues: rawCues.slice(0, cueLimit).map((cue, index) => ({
            index,
            start_time: Number(cue.startTime),
            end_time: Number(cue.endTime),
            text: textOf(cue.text)
          }))
        });
      }
      return evidence;
    } finally {
      for (const [trackElement, originalMode] of originalModes.entries()) {
        if (trackElement.track) trackElement.track.mode = originalMode;
      }
    }
  };

  const videoElements = visibleMatches('video');
  const videoTrackElements = videoElements.flatMap((video) => Array.from(video.querySelectorAll('track')));
  const loadedTextTrackEvidence = await loadTextTrackEvidence(videoTrackElements);
  const videos = videoElements.map((el) => {
    registerStructuralRelationshipsFor(el, { headingContext: true });
    return {
      ...baseElement(el, 'video'),
      src: el.currentSrc || attr(el, 'src') || '',
      current_src: el.currentSrc || '',
      source_src: attr(el, 'src') || '',
      sources: Array.from(el.querySelectorAll('source')).map((source) => ({
        src: attr(source, 'src') || '',
        current_src: source.src || '',
        type: attr(source, 'type') || '',
        media: attr(source, 'media') || ''
      })),
      poster: attrText(el, 'poster'),
      controls: !!el.controls,
      preload: attr(el, 'preload') || '',
      autoplay: !!el.autoplay,
      muted: !!el.muted,
      loop: !!el.loop,
      duration: Number.isFinite(el.duration) ? Number(el.duration) : null,
      ready_state: Number(el.readyState),
      nearby_transcript_text: nearbyTranscriptText(el),
      tracks: Array.from(el.querySelectorAll('track'))
        .map((track) => loadedTextTrackEvidence.get(track))
        .filter(Boolean)
    };
  });

  const linkElements = visibleMatches('a[href], [role="link"]');
  const links = linkElements.map((el) => {
    registerReferencesFor(el);
    registerStructuralRelationshipsFor(el, { headingContext: true });
    return {
      ...baseElement(el, 'link'),
      href: attr(el, 'href') || '',
      target: attrText(el, 'target')
    };
  });

  const buttonElements = visibleMatches('button, input[type="button"], input[type="submit"], input[type="reset"], [role="button"]');
  const buttons = buttonElements.map((el) => {
    registerReferencesFor(el);
    registerStructuralRelationshipsFor(el, { formContains: true, headingContext: true });
    return {
      ...baseElement(el, 'button', { includeControlValue: true }),
      type: attr(el, 'type') || '',
      value: textOf(el.value),
      disabled: !!el.disabled || attr(el, 'aria-disabled') === 'true',
      aria_controls: attrText(el, 'aria-controls'),
      aria_expanded: attrText(el, 'aria-expanded'),
      aria_selected: attrText(el, 'aria-selected'),
      aria_checked: attrText(el, 'aria-checked'),
      aria_pressed: attrText(el, 'aria-pressed')
    };
  });

  const formElements = visibleMatches('form');
  const forms = formElements.map((el) => {
    registerReferencesFor(el);
    registerStructuralRelationshipsFor(el, { headingContext: true });
    return {
      ...baseElement(el, 'form'),
      method: attrText(el, 'method'),
      action: attr(el, 'action') || '',
      name: attrText(el, 'name')
    };
  });

  const controlSelector = 'input:not([type="hidden"]), textarea, select, [role="textbox"], [role="combobox"], [role="checkbox"], [role="radio"], [role="switch"], [role="slider"]';
  const controlElements = visibleMatches(controlSelector);
  const hasControlValue = (el) => {
    const tag = tagOf(el);
    if (tag === 'input' && ['checkbox', 'radio'].includes(inputTypeOf(el))) return !!el.checked;
    if ('value' in el) return String(el.value || '').length > 0;
    return false;
  };
  const nativeValidity = (el) => {
    if (!el.validity) return null;
    return {
      valid: !!el.validity.valid,
      value_missing: !!el.validity.valueMissing,
      type_mismatch: !!el.validity.typeMismatch,
      pattern_mismatch: !!el.validity.patternMismatch,
      too_long: !!el.validity.tooLong,
      too_short: !!el.validity.tooShort,
      range_underflow: !!el.validity.rangeUnderflow,
      range_overflow: !!el.validity.rangeOverflow,
      step_mismatch: !!el.validity.stepMismatch,
      bad_input: !!el.validity.badInput,
      custom_error: !!el.validity.customError
    };
  };
  // W4A round 4 (WCAG 3.3.1, F81): signs that a field is shown in error only visually (error/flag class on the field,
  // its wrapper, label or legend; a warning icon next to it; a red border), so the judge can ask whether the error
  // is also described in text.
  const ERROR_TOKEN = /(^|[-_\s])(error|errors|invalid|has-error|is-invalid|danger|warn|warning|flag|flagged|alert|attention)([-_\s]|$)/i;
  const ERROR_ICON = /warn|error|alert|exclam|invalid|attention/i;
  const visualErrorSignals = (el) => {
    const signals = [];
    const tokens = (node) => node ? `${node.getAttribute('class') || ''} ${node.id || ''}` : '';
    const wrappers = [el, el.parentElement, el.parentElement && el.parentElement.parentElement].filter(Boolean);
    for (const node of wrappers) if (ERROR_TOKEN.test(tokens(node))) { signals.push(`error class on ${node === el ? 'field' : 'wrapper'}`); break; }
    const label = (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) || el.closest('label');
    if (label && ERROR_TOKEN.test(tokens(label))) signals.push('error class on label');
    const fieldset = el.closest('fieldset');
    const legend = fieldset && fieldset.querySelector('legend');
    if (legend && ERROR_TOKEN.test(tokens(legend))) signals.push('error class on group legend');
    else if (fieldset && ERROR_TOKEN.test(tokens(fieldset))) signals.push('error class on group');
    const parent = el.parentElement;
    if (parent) {
      for (const icon of parent.querySelectorAll('img, svg, i, span[class]')) {
        if (icon === el || icon.contains(el)) continue;
        const cue = `${icon.getAttribute('class') || ''} ${icon.getAttribute('alt') || ''} ${icon.getAttribute('src') || ''} ${icon.getAttribute('aria-label') || ''}`;
        if (ERROR_ICON.test(cue.slice(0, 400)) && isVisible(icon)) { signals.push('warning icon next to field'); break; }
      }
    }
    const border = (window.getComputedStyle(el).borderTopColor || '').match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (border && Number(border[1]) >= 170 && Number(border[2]) <= 90 && Number(border[3]) <= 90) signals.push('red border');
    return signals;
  };
  const formControls = controlElements.map((el) => {
    registerReferencesFor(el);
    registerStructuralRelationshipsFor(el, { formContains: true, headingContext: true });
    const ariaInvalid = attrText(el, 'aria-invalid');
    const native = nativeValidity(el);
    return {
      ...baseElement(el, 'form_control'),
      type: attr(el, 'type') || '',
      name: attrText(el, 'name'),
      id: attrText(el, 'id'),
      label: maybeText(explicitLabelText(el)),
      wrapping_label: maybeText(wrappingLabelText(el)),
      placeholder: attrText(el, 'placeholder'),
      autocomplete: attrText(el, 'autocomplete'),
      required: !!el.required || attr(el, 'aria-required') === 'true',
      disabled: !!el.disabled || attr(el, 'aria-disabled') === 'true',
      readonly: !!el.readOnly || attr(el, 'readonly') !== null || attr(el, 'aria-readonly') === 'true',
      aria_invalid: ariaInvalid,
      invalid: ariaInvalid === 'true' || (native ? native.valid === false : false),
      visual_error_signals: visualErrorSignals(el),
      // W4A round 4: the control's current value, so a button's result can be checked against the fields it changed
      // (never for password fields)
      current_value: (() => {
        const type = (attr(el, 'type') || '').toLowerCase();
        if (type === 'password') return null;
        if (el.tagName === 'SELECT') return textOf(Array.from(el.selectedOptions || []).map((o) => o.text).join(', '), 120);
        if (type === 'checkbox' || type === 'radio') return el.checked ? 'checked' : 'not checked';
        return 'value' in el ? textOf(el.value, 120) : null;
      })(),
      native_validity: native,
      parent_form: formSummary(el.closest('form')),
      has_value: hasControlValue(el),
      checked: 'checked' in el ? !!el.checked : null,
      selected: 'selected' in el ? !!el.selected : null,
      aria_controls: attrText(el, 'aria-controls'),
      aria_expanded: attrText(el, 'aria-expanded'),
      aria_selected: attrText(el, 'aria-selected'),
      aria_checked: attrText(el, 'aria-checked'),
      aria_pressed: attrText(el, 'aria-pressed')
    };
  });

  const headingElements = visibleMatches(headingSelector + ', [role="heading"]');  // W4A dev round 2: ARIA headings too
  const headings = headingElements.map((el) => ({
    ...baseElement(el, 'heading'),
    level: headingLevelOf(el),
    heading_scope: headingScopeFor(el)
  }));

  const landmarkElements = visibleMatches(landmarkSelector);
  const landmarks = landmarkElements.map((el) => {
    registerReferencesFor(el);
    return {
      ...baseElement(el, 'landmark'),
      text_sample: textOf(el.innerText || el.textContent)
    };
  });

  const tableElements = visibleMatches('table, [role="table"], [role="grid"]');
  const tables = tableElements.map((el) => {
    registerReferencesFor(el);
    registerStructuralRelationshipsFor(el, { headingContext: true });
    const tableHeaders = Array.from(el.querySelectorAll('th, [role="columnheader"], [role="rowheader"]'));
    const headersById = new Map();
    const compactHeader = (header) => {
      const row = header.closest('tr, [role="row"]');
      const cells = row ? Array.from(row.children).filter((cell) => ['th', 'td'].includes(tagOf(cell)) || /^(cell|gridcell|columnheader|rowheader)$/.test(roleOf(cell))) : [];
      const headerId = attr(header, 'id') || '';
      const item = {
        id: headerId,
        element_id: elementIdFor(header, 'table_header'),
        selector: selectorOf(header),
        tag: tagOf(header),
        role: roleOf(header) || null,
        text: textOf(header.innerText || header.textContent),
        scope: attr(header, 'scope') || '',
        row_index: row ? Array.from(el.querySelectorAll('tr, [role="row"]')).indexOf(row) : -1,
        column_index: cells.indexOf(header)
      };
      if (headerId) headersById.set(headerId, item);
      return item;
    };
    const headers = tableHeaders.map(compactHeader);
    const dataCells = Array.from(el.querySelectorAll('td[headers], [role="cell"][headers], [role="gridcell"][headers]')).map((cell) => {
      const row = cell.closest('tr, [role="row"]');
      const cells = row ? Array.from(row.children).filter((item) => ['th', 'td'].includes(tagOf(item)) || /^(cell|gridcell|columnheader|rowheader)$/.test(roleOf(item))) : [];
      const headerIds = String(attr(cell, 'headers') || '').split(/\s+/).filter(Boolean);
      const associatedHeaders = headerIds.map((id) => headersById.get(id)).filter(Boolean);
      return {
        element_id: elementIdFor(cell, 'table_cell'),
        selector: selectorOf(cell),
        tag: tagOf(cell),
        role: roleOf(cell) || null,
        text: textOf(cell.innerText || cell.textContent),
        header_ids: headerIds,
        headers_all_resolved: headerIds.length > 0 && associatedHeaders.length === headerIds.length,
        associated_headers: associatedHeaders,
        row_index: row ? Array.from(el.querySelectorAll('tr, [role="row"]')).indexOf(row) : -1,
        column_index: cells.indexOf(cell)
      };
    });
    return {
      ...baseElement(el, 'table'),
      caption: maybeText((el.querySelector('caption') || {}).innerText || ''),
      header_count: headers.length,
      data_cell_count: Array.from(el.querySelectorAll('td, [role="cell"], [role="gridcell"]')).length,
      headers,
      data_cells: dataCells
    };
  });

  const focusSelector = [
    'a[href]',
    'button',
    'input:not([type="hidden"])',
    'textarea',
    'select',
    'summary',
    '[contenteditable]:not([contenteditable="false"])',
    '[tabindex]'
  ].join(',');
  const focusableElements = visibleMatches(focusSelector)
    .filter((el) => attr(el, 'tabindex') !== '-1' || ['a', 'button', 'input', 'textarea', 'select', 'summary'].includes(tagOf(el)));
  const focusables = focusableElements.map((el, index) => {
    registerReferencesFor(el);
    registerStructuralRelationshipsFor(el, { formContains: ['button', 'input', 'textarea', 'select'].includes(tagOf(el)), headingContext: true });
    const tabindexRaw = attrText(el, 'tabindex');
    const parsedTabindex = tabindexRaw === null ? null : Number.parseInt(tabindexRaw, 10);
    return {
      ...baseElement(el, 'focusable'),
      href: attr(el, 'href') || '',
      type: attr(el, 'type') || '',
      tabindex: tabindexRaw,
      tabindex_raw: tabindexRaw,
      tabindex_value: Number.isFinite(parsedTabindex) ? parsedTabindex : null,
      disabled: !!el.disabled || attr(el, 'aria-disabled') === 'true',
      dom_order_index: index,
      checked: 'checked' in el ? !!el.checked : null,
      selected: 'selected' in el ? !!el.selected : null,
      aria_controls: attrText(el, 'aria-controls'),
      aria_expanded: attrText(el, 'aria-expanded'),
      aria_selected: attrText(el, 'aria-selected'),
      aria_checked: attrText(el, 'aria-checked'),
      aria_pressed: attrText(el, 'aria-pressed')
    };
  });

  const cappedFocusables = capped('focusables', focusables, 'max_focusables_per_state');
  const focusOrder = cappedFocusables.map((item, index) => ({
    order: index + 1,
    element_id: item.element_id
  }));
  const rootLang = document.documentElement.getAttribute('lang')
    || document.documentElement.getAttribute('xml:lang')
    || '';
  const bodyLang = document.body
    ? (document.body.getAttribute('lang') || document.body.getAttribute('xml:lang') || '')
    : '';
  const pageLang = rootLang || bodyLang;
  const isPageLanguageScopeElement = (el) => el === document.documentElement || el === document.body;
  const nearestAncestorLang = (el) => {
    let current = el.parentElement;
    while (current && current !== document.documentElement && current !== document.body) {
      const value = current.getAttribute('lang') || current.getAttribute('xml:lang') || '';
      if (value) return value;
      current = current.parentElement;
    }
    return '';
  };
  // W4A round 4 (ACT ucwvc8 / off6ek): text alternatives (alt, aria-label, aria-labelledby names) are text in the
  // language of the element they name, inherited from its nearest [lang] ancestor, not of the element they come from.
  const nameFromAttributes = (el) => {
    const labelledby = (attr(el, 'aria-labelledby') || '').trim();
    if (labelledby) {
      const text = labelledby.split(/\s+/).map((id) => document.getElementById(id)).filter(Boolean)
        .map((n) => (n.textContent || '').replace(/\s+/g, ' ').trim()).join(' ').trim();
      if (text) return text;
    }
    const label = (attr(el, 'aria-label') || '').trim();
    if (label) return label;
    if (el.matches('img, area, input[type="image"]')) return (attr(el, 'alt') || '').trim();
    return '';
  };
  const textAlternativesInheriting = (root, inherits) => {
    const out = [];
    if (!root) return out;
    for (const el of root.querySelectorAll('img, area, input[type="image"], svg, [role="img"], [aria-label], [aria-labelledby]')) {
      if (out.length >= 12) break;
      if (el.closest('[aria-hidden="true"]') || !isVisible(el)) continue;
      if (!inherits(el.closest('[lang]'))) continue;
      const name = nameFromAttributes(el);
      if (name) out.push(name);
    }
    return out;
  };
  const languageSampleSelector = [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'li', 'blockquote', 'q', 'figcaption',
    'td', 'th', 'label', 'legend',
    '[lang]', '[xml\\:lang]'
  ].join(',');
  const languageSamples = visibleMatches(languageSampleSelector)
    .filter((el) => !isPageLanguageScopeElement(el))
    .map((el) => {
      const ownLang = attr(el, 'lang') || attr(el, 'xml:lang') || '';
      const alternatives = ownLang ? textAlternativesInheriting(el, (host) => host === el) : [];
      const languageText = textOf([el.innerText || el.textContent || '', ...alternatives].join(' ').trim());
      const localLang = ownLang;
      const ancestorLang = nearestAncestorLang(el);
      return {
        ...baseElement(el, 'language_sample'),
        language_text: languageText,
        word_count: languageText ? languageText.split(/\s+/).filter(Boolean).length : 0,
        root_lang: rootLang,
        body_lang: bodyLang,
        page_lang: pageLang,
        local_lang: localLang,
        ancestor_lang: ancestorLang,
        effective_lang: localLang || ancestorLang || pageLang
      };
    })
    .filter((item) => item.language_text && item.word_count >= 2);

  const visualCueSelector = [
    '[role="status"]',
    '[role="alert"]',
    '[aria-current]',
    '[aria-selected]',
    '[aria-invalid]',
    '[aria-expanded]',
    '[aria-checked]',
    '[aria-pressed]',
    '[data-state]',
    '[data-status]',
    'output',
    'meter',
    'progress',
    'legend',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'li', 'span', 'div', 'button', 'a', 'label', 'strong', 'em', 'small'
  ].join(',');
  const visualCues = visibleMatches(visualCueSelector)
    .map((el) => {
      registerReferencesFor(el);
      registerStructuralRelationshipsFor(el, { headingContext: true });
      const text = textOf(el.innerText || el.textContent || '');
      const inlineStyle = attr(el, 'style') || '';
      const identity = `${attr(el, 'id') || ''} ${attr(el, 'class') || ''}`;
      const hasInlineColor = /\b(color|background(?:-color)?|border(?:-color)?)\s*:/i.test(inlineStyle);
      const hasStateAttribute = [
        'role', 'aria-current', 'aria-selected', 'aria-invalid', 'aria-expanded', 'aria-checked', 'aria-pressed', 'data-state', 'data-status'
      ].some((name) => el.hasAttribute(name));
      const hasCueIdentity = /(status|error|warning|success|invalid|valid|selected|active|inactive|required|legend)/i.test(identity);
      if (!text || text.length > 180 || (!hasInlineColor && !hasStateAttribute && !hasCueIdentity)) {
        return null;
      }
      const parent = el.parentElement;
      return {
        ...baseElement(el, 'visual_cue'),
        inline_style: textOf(inlineStyle, 300),
        has_inline_color: hasInlineColor,
        parent_computed_style: parent ? computedStyle(parent) : {},
        cue_attributes: {
          role: attr(el, 'role') || '',
          aria_current: attr(el, 'aria-current') || '',
          aria_selected: attr(el, 'aria-selected') || '',
          aria_invalid: attr(el, 'aria-invalid') || '',
          aria_expanded: attr(el, 'aria-expanded') || '',
          aria_checked: attr(el, 'aria-checked') || '',
          aria_pressed: attr(el, 'aria-pressed') || '',
          data_state: attr(el, 'data-state') || '',
          data_status: attr(el, 'data-status') || ''
        }
      };
    })
    .filter(Boolean);
  const referencedElements = Array.from(referencedById.values());
  const relationships = Array.from(relationshipByKey.values());
  const bodyText = textOf(document.body ? document.body.innerText : '', 1000000);

  // W4A dev round 2: 3.1.1 compares the page language with the text that has no language of its own.
  const textWithoutOwnLang = (() => {
    if (!document.body) return '';
    const parts = [];
    let total = 0;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node && total < 600; node = walker.nextNode()) {
      const parent = node.parentElement;
      if (!parent || parent.closest('script, style, noscript, template')) continue;
      const langHost = parent.closest('[lang]');
      if (langHost && langHost !== document.body && langHost !== document.documentElement) continue;
      if (!isVisible(parent) || parent.closest('[aria-hidden="true"], [hidden]')) continue;  // visible text only
      const text = (node.textContent || '').replace(/\s+/g, ' ').trim();
      if (!text) continue;
      parts.push(text);
      total += text.length + 1;
    }
    const pageScope = (host) => !host || host === document.body || host === document.documentElement;
    parts.push(...textAlternativesInheriting(document.body, pageScope));
    return textOf(parts.join(' ')).slice(0, 500);
  })();
  // W4A dev round 2: error texts on the page (alerts, live regions, elements named "error"/"invalid"), whether a
  // field references them (aria-describedby / aria-errormessage), and whether they are hidden from assistive tech.
  const errorTexts = (() => {
    const rx = /(^|[-_\s])(error|errors|invalid|err|validation|alert)([-_\s]|$)/i;
    const referenced = [];
    for (const control of document.querySelectorAll('[aria-describedby], [aria-errormessage]')) {
      for (const ref of elementsFromIds(`${attr(control, 'aria-describedby') || ''} ${attr(control, 'aria-errormessage') || ''}`)) referenced.push(ref);
    }
    const shown = (el) => { const r = el.getBoundingClientRect(); return !!(r.width || r.height) && !el.hidden && !isHiddenByStyle(el); };
    const out = [];
    for (const el of document.querySelectorAll('[role="alert"], [aria-live], [id], [class]')) {
      if (el.matches('input, select, textarea, button, form, body, html, main, header, footer, nav')) continue;
      const name = `${el.id || ''} ${typeof el.className === 'string' ? el.className : ''}`;
      if (!(attr(el, 'role') === 'alert' || el.hasAttribute('aria-live') || rx.test(name))) continue;
      const text = textOf(el.innerText || el.textContent || '');
      if (!text || text.length > 300 || !shown(el)) continue;
      if (out.some((o) => o.node.contains(el))) continue;
      out.push({
        node: el,
        text,
        role: attr(el, 'role') || null,
        aria_live: attr(el, 'aria-live'),
        hidden_from_assistive_technology: !!el.closest('[aria-hidden="true"]'),
        referenced_by_a_field: referenced.some((ref) => ref === el || ref.contains(el) || el.contains(ref)),
        xpath: xpathOf(el),
        form_xpath: el.closest('form') ? xpathOf(el.closest('form')) : null
      });
      if (out.length >= 10) break;
    }
    return out.map(({ node, ...rest }) => rest);
  })();

  // W4A round 5 (WCAG 3.3.1): an error message that a field or its submit control references (aria-describedby,
  // aria-errormessage) but that is not shown, recorded with the form's current values; the judge decides whether a
  // filled-in value fails the requirement the hidden message states (the error exists but is never shown)
  const hiddenErrorTexts = (() => {
    const out = [];
    const shown = (el) => { const r = el.getBoundingClientRect(); return !!(r.width || r.height) && !el.hidden && !isHiddenByStyle(el); };
    const selector = ['input', 'select', 'textarea', 'button'].map((t) => `${t}[aria-describedby], ${t}[aria-errormessage]`).join(', ');
    for (const control of document.querySelectorAll(selector)) {
      const form = control.closest('form');
      if (!form) continue;
      for (const ref of elementsFromIds(`${attr(control, 'aria-describedby') || ''} ${attr(control, 'aria-errormessage') || ''}`)) {
        if (shown(ref) || out.some((o) => o.node === ref)) continue;
        const text = textOf(ref.textContent || '');
        if (!text || text.length > 300) continue;
        const values = Array.from(form.querySelectorAll('input, select, textarea'))
          .filter((f) => !['hidden', 'password', 'submit', 'button', 'reset', 'image'].includes((f.type || '').toLowerCase()))
          .slice(0, 12)
          .map((f) => ({
            xpath: xpathOf(f),
            name: maybeText(approximateAccessibleName(f, {})),
            value: f.tagName === 'SELECT' ? ((f.selectedOptions[0] || {}).text || '')
              : (['checkbox', 'radio'].includes((f.type || '').toLowerCase()) ? (f.checked ? 'checked' : 'not checked') : (f.value || ''))
          }));
        out.push({ node: ref, text, xpath: xpathOf(ref), referenced_by: xpathOf(control), form_xpath: xpathOf(form), form_values: values });
        if (out.length >= 10) break;
      }
      if (out.length >= 10) break;
    }
    return out.map(({ node, ...rest }) => rest);
  })();

  return {
    schema_version: schemaVersion,
    state_id: stateId,
    state_context: stateContext,
    page: {
      url: document.location.href,
      title: document.title,
      document_lang: document.documentElement.lang || pageLang || '',
      html_lang: document.documentElement.getAttribute('lang'),
      body_lang: bodyLang || null,
      page_lang: pageLang,
      body_text_sample: textOf(bodyText),
      body_text_length: bodyText.length,
      text_without_own_lang: textWithoutOwnLang,
      error_texts: errorTexts,
      hidden_error_texts: hiddenErrorTexts
    },
    referenced_elements: capped('referenced_elements', referencedElements, 'max_referenced_elements_per_state'),
    images: capped('images', images, 'max_images_per_state'),
    hidden_images: capped('hidden_images', hiddenImages, 'max_images_per_state'),
    lookalike_text: lookalikeText,
    hidden_focusable_links: hiddenFocusableLinks,
    videos: capped('videos', videos, 'max_videos_per_state'),
    links: capped('links', links, 'max_links_per_state'),
    buttons: capped('buttons', buttons, 'max_buttons_per_state'),
    forms: capped('forms', forms, 'max_forms_per_state'),
    form_controls: capped('form_controls', formControls, 'max_form_controls_per_state'),
    headings: capped('headings', headings, 'max_headings_per_state'),
    landmarks: capped('landmarks', landmarks, 'max_landmarks_per_state'),
    tables: capped('tables', tables, 'max_tables_per_state'),
    language_samples: capped('language_samples', languageSamples, 'max_language_samples_per_state'),
    visual_cues: capped('visual_cues', visualCues, 'max_visual_cues_per_state'),
    focusables: cappedFocusables,
    focus_order: focusOrder,
    focus_traversal: [],
    relationships: capped('relationships', relationships, 'max_relationships_per_state'),
    extraction_metadata: {
      status: 'success',
      screenshot_path: screenshotPath,
      truncated: Object.keys(truncation).length > 0,
      truncation,
      limits
    }
  };
};
